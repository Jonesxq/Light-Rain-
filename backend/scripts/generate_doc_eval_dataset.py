"""Generate a per-document QA dataset for RAGas evaluation.

The script logs in to the local API, samples source chunks from completed PDF
documents, and asks the configured chat model to create grounded Chinese QA
pairs from those chunks.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import pytz
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.config.settings import settings
from app.utils.llm_factory import build_chat_llm


SYSTEM_PROMPT = """你是RAG测评集构造专家。
你会收到若干文档chunk，每个chunk都有chunk_index和原文。
请为每个chunk生成1条中文问题和1条中文标准答案。

要求：
1. 问题必须能仅凭对应chunk回答，不要依赖外部知识。
2. 标准答案必须忠实于chunk，不要编造。
3. 问题要覆盖定义、机制、步骤、风险、指标、结论、对比、用途等类型。
4. 输出必须是JSON数组，不要Markdown，不要解释。
5. 每个对象字段：chunk_index, question, ground_truth。
"""


def _extract_json_array(text: str) -> list[dict[str, Any]]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)

    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\[[\s\S]*\]", stripped)
        if not match:
            raise
        payload = json.loads(match.group(0))

    if not isinstance(payload, list):
        raise ValueError("model output must be a JSON array")
    return payload


def _sample_indices(total: int, count: int) -> list[int]:
    if total <= 0:
        return []
    if total <= count:
        return list(range(total))
    # Avoid overly front-loaded title/TOC chunks while still covering the document.
    start = min(total - 1, max(0, total // 20))
    end = total - 1
    if count == 1:
        return [start]
    return sorted({round(start + i * (end - start) / (count - 1)) for i in range(count)})


async def _generate_batch(
    *,
    model_name: str | None,
    doc_name: str,
    chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    llm = build_chat_llm(model=model_name, temperature=0.0, streaming=False)
    chunk_payload = [
        {
            "chunk_index": item["chunk_index"],
            "content": item["content"][:2200],
        }
        for item in chunks
    ]
    prompt = {
        "doc": doc_name,
        "chunks": chunk_payload,
    }
    response = await llm.ainvoke(
        [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=json.dumps(prompt, ensure_ascii=False)),
        ]
    )
    records = _extract_json_array((getattr(response, "content", "") or "").strip())
    return records


def _login(client: httpx.Client, base_url: str, username: str, password: str) -> dict[str, str]:
    response = client.post(
        f"{base_url}/auth/login",
        json={"username": username, "password": password},
    )
    response.raise_for_status()
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _fetch_chunk(
    client: httpx.Client,
    base_url: str,
    headers: dict[str, str],
    doc_id: int,
    chunk_index: int,
) -> dict[str, Any] | None:
    response = client.get(
        f"{base_url}/knowledge/documents/{doc_id}/chunks/{chunk_index}",
        headers=headers,
    )
    if response.status_code != 200:
        return None
    payload = response.json()
    content = (payload.get("content") or "").strip()
    if len(content) < 80:
        return None
    return {
        "chunk_index": chunk_index,
        "content": content,
    }


async def run(args: argparse.Namespace) -> Path:
    username = args.username or os.getenv("LR_USERNAME")
    password = args.password or os.getenv("LR_PASSWORD")
    if not username or not password:
        raise ValueError("username/password are required via args or LR_USERNAME/LR_PASSWORD")

    base_url = args.base_url.rstrip("/")
    output = Path(args.output).resolve() if args.output else None
    if output is None:
        timestamp = datetime.now(pytz.timezone("Asia/Shanghai")).strftime("%Y%m%d_%H%M%S")
        output = Path.cwd() / f"ragas_doc10_qa_dataset_{timestamp}.json"

    records: list[dict[str, Any]] = []
    with httpx.Client(timeout=args.timeout) as client:
        headers = _login(client, base_url, username, password)
        docs_response = client.get(f"{base_url}/knowledge/{args.kb_id}/documents", headers=headers)
        docs_response.raise_for_status()
        docs = [
            doc
            for doc in docs_response.json()
            if str(doc.get("file_name", "")).lower().endswith(".pdf")
            and doc.get("status") == "completed"
        ]
        docs.sort(key=lambda item: item["file_name"])
        if len(docs) < args.expected_docs:
            raise ValueError(f"expected {args.expected_docs} completed PDFs, found {len(docs)}")

        for doc_pos, doc in enumerate(docs[: args.expected_docs], start=1):
            doc_id = int(doc["id"])
            doc_name = doc["file_name"]
            chunk_count = int(doc.get("chunk_count") or 0)
            indices = _sample_indices(chunk_count, args.questions_per_doc * 3)

            chunks: list[dict[str, Any]] = []
            for idx in indices:
                chunk = _fetch_chunk(client, base_url, headers, doc_id, idx)
                if chunk:
                    chunks.append(chunk)
                if len(chunks) >= args.questions_per_doc:
                    break

            if len(chunks) < args.questions_per_doc:
                raise ValueError(
                    f"{doc_name} only yielded {len(chunks)} usable chunks, "
                    f"need {args.questions_per_doc}"
                )

            print(
                f"[{doc_pos}/{args.expected_docs}] generate QA: "
                f"doc_id={doc_id}, doc={doc_name}, chunks={len(chunks)}",
                flush=True,
            )

            doc_records: list[dict[str, Any]] = []
            for start in range(0, len(chunks), args.batch_size):
                batch = chunks[start : start + args.batch_size]
                generated = await _generate_batch(
                    model_name=args.model,
                    doc_name=doc_name,
                    chunks=batch,
                )
                by_index = {int(item["chunk_index"]): item for item in generated}
                for chunk in batch:
                    item = by_index.get(int(chunk["chunk_index"]))
                    if not item:
                        continue
                    question = (item.get("question") or "").strip()
                    ground_truth = (item.get("ground_truth") or "").strip()
                    if not question or not ground_truth:
                        continue
                    doc_records.append(
                        {
                            "doc": doc_name,
                            "doc_id": doc_id,
                            "chunk_index": int(chunk["chunk_index"]),
                            "question": question,
                            "ground_truth": ground_truth,
                            "source_excerpt": chunk["content"][:500],
                        }
                    )

            if len(doc_records) < args.questions_per_doc:
                raise ValueError(
                    f"{doc_name} generated {len(doc_records)} QA pairs, "
                    f"need {args.questions_per_doc}"
                )
            records.extend(doc_records[: args.questions_per_doc])

    output.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"DATASET_PATH={output}")
    print(f"DATASET_ROWS={len(records)}")
    print(f"MODEL={args.model or settings.llm.DEFAULT_MODEL}")
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate doc-level QA dataset for RAGas")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--kb-id", type=int, required=True)
    parser.add_argument("--username", default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--expected-docs", type=int, default=10)
    parser.add_argument("--questions-per-doc", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--model", default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--timeout", type=float, default=180.0)
    return parser


if __name__ == "__main__":
    asyncio.run(run(build_parser().parse_args()))
