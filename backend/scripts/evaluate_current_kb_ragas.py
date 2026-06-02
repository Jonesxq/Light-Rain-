"""对当前知识库 RAG 流程运行 RAGas 评估。

该脚本适配当前项目结构：直接复用 kb_service 的 BM25、向量检索、RRF 融合和重排逻辑，
再用项目的 RAG 评估回答提示词生成答案，最后交给 RAGas 计算指标。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any

os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")
os.environ.setdefault("DO_NOT_TRACK", "true")

import pandas as pd
import pytz
from datasets import Dataset
from langchain_core.messages import HumanMessage, SystemMessage
from ragas import aevaluate
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper

warnings.filterwarnings("ignore", message=r"Importing .* from 'ragas.metrics' is deprecated.*")
from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness

from app.constant.prompts import RAG_EVAL_ANSWER_PROMPT_TEMPLATE
from app.core.config.settings import settings
from app.core.database import db_manager, mysql_manager
from app.core.logger import logger_manager
from app.core.redis import redis_manager
from app.services.knowledge import kb_service
from app.services.shared.query_rewrite import query_rewrite_service
from app.utils.llm_factory import build_chat_llm, build_embeddings

logger = logger_manager.get_logger(__name__)

logging.getLogger().setLevel(logging.WARNING)
for _logger_name in (
    "sqlalchemy.engine",
    "httpcore",
    "httpx",
    "openai",
    "dashscope",
    "urllib3",
    "pymilvus",
    "grpc",
):
    logging.getLogger(_logger_name).setLevel(logging.WARNING)


def _load_dataset(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    """读取 scripts 目录同款 JSON QA 数据集。"""
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, list):
        raise ValueError("dataset must be a JSON array")

    records: list[dict[str, Any]] = []
    for index, item in enumerate(data):
        question = (item.get("question") or "").strip()
        reference = (item.get("ground_truth") or item.get("reference") or "").strip()
        if not question or not reference:
            logger.warning(f"跳过第 {index + 1} 条：缺少 question 或 ground_truth/reference")
            continue
        records.append(
            {
                "doc": item.get("doc") or "",
                "question": question,
                "reference": reference,
            }
        )

    return records[:limit] if limit else records


async def _retrieve_contexts(
    *,
    kb_id: int,
    question: str,
    top_k: int,
    user_id: int | None,
    use_query_rewrite: bool,
) -> tuple[list[str], list[dict[str, Any]], str]:
    """复用当前检索链路，返回 RAGas 需要的 contexts 列表。"""
    rewritten_query = question
    if use_query_rewrite:
        async with mysql_manager.async_session_maker() as db:
            rewritten_query = await query_rewrite_service.rewrite_query(
                question,
                user_id=user_id,
                kb_id=kb_id,
                db=db,
            )

    candidates, bm25 = await kb_service._get_bm25_index(kb_id)
    raw_lookup = kb_service._build_raw_lookup(candidates)

    ranked_lists = []
    if candidates and bm25 is not None:
        bm25_k = max(settings.llm.RAG_BM25_TOP_K, top_k)
        bm25_candidates = kb_service._bm25_search(rewritten_query, candidates, bm25, bm25_k)
        ranked_lists.append(kb_service._items_from_bm25(bm25_candidates))

    semantic_docs = await kb_service._semantic_search_global(
        kb_id=kb_id,
        query=rewritten_query,
        top_k=max(settings.llm.RAG_SEMANTIC_TOP_K, top_k),
    )
    semantic_items = await kb_service._items_from_documents(semantic_docs, raw_lookup=raw_lookup)
    ranked_lists.append(semantic_items)

    fused_items = kb_service._rrf_fusion_items(ranked_lists)
    reranked_items = await kb_service._gte_rerank_items(rewritten_query, fused_items, top_k)

    contexts = [item.content for item in reranked_items if item.content]
    sources = kb_service._build_sources(reranked_items, max_sources=top_k)
    return contexts, sources, rewritten_query


async def _answer_question(question: str, contexts: list[str], model_name: str | None) -> str:
    """用当前项目的 RAG 评估提示词生成答案。"""
    context_text = "\n\n".join(contexts).strip() or "未找到相关参考资料。"
    llm = build_chat_llm(model=model_name, temperature=0.0, streaming=False)
    response = await llm.ainvoke(
        [
            SystemMessage(content=RAG_EVAL_ANSWER_PROMPT_TEMPLATE.format(context=context_text)),
            HumanMessage(content=question),
        ]
    )
    return (getattr(response, "content", "") or "").strip()


def _json_default(value: Any) -> Any:
    if pd.isna(value):
        return None
    return float(value)


async def run_evaluation(args: argparse.Namespace) -> dict[str, Any]:
    settings.database.ECHO = False
    dataset_path = Path(args.dataset).resolve()
    records = _load_dataset(dataset_path, args.limit)
    if not records:
        raise ValueError("没有可评估的数据")

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(pytz.timezone("Asia/Shanghai")).strftime("%Y%m%d_%H%M%S")
    answers_path = output_dir / f"ragas_answers_kb{args.kb_id}_{timestamp}.json"
    report_path = output_dir / f"ragas_report_kb{args.kb_id}_{timestamp}.json"
    summary_path = output_dir / f"ragas_summary_kb{args.kb_id}_{timestamp}.json"

    await db_manager.initialize()
    await redis_manager.initialize_async()

    try:
        eval_rows: list[dict[str, Any]] = []
        raw_rows: list[dict[str, Any]] = []
        for index, record in enumerate(records, start=1):
            question = record["question"]
            logger.info(f"[{index}/{len(records)}] 检索并回答：{question}")
            contexts, sources, rewritten_query = await _retrieve_contexts(
                kb_id=args.kb_id,
                question=question,
                top_k=args.top_k,
                user_id=args.user_id,
                use_query_rewrite=args.use_query_rewrite,
            )
            answer = await _answer_question(question, contexts, args.answer_model)

            eval_rows.append(
                {
                    "user_input": question,
                    "response": answer,
                    "retrieved_contexts": contexts,
                    "reference": record["reference"],
                }
            )
            raw_rows.append(
                {
                    "doc": record["doc"],
                    "question": question,
                    "rewritten_query": rewritten_query,
                    "answer": answer,
                    "reference": record["reference"],
                    "sources": sources,
                    "contexts": contexts,
                }
            )

        answers_path.write_text(json.dumps(raw_rows, ensure_ascii=False, indent=2), encoding="utf-8")

        evaluator_llm = LangchainLLMWrapper(
            build_chat_llm(model=args.judge_model, temperature=0.0, streaming=False)
        )
        evaluator_embeddings = LangchainEmbeddingsWrapper(build_embeddings())
        # Qwen thinking mode requires n=1; RAGas answer_relevancy defaults to 3 generations.
        answer_relevancy.strictness = 1
        metrics = [faithfulness, answer_relevancy, context_precision, context_recall]

        logger.info(f"开始 RAGas 打分：rows={len(eval_rows)}, metrics={[metric.name for metric in metrics]}")
        result = await aevaluate(
            dataset=Dataset.from_list(eval_rows),
            metrics=metrics,
            llm=evaluator_llm,
            embeddings=evaluator_embeddings,
            show_progress=True,
            raise_exceptions=False,
        )

        df = result.to_pandas()
        report_rows = json.loads(df.to_json(orient="records", force_ascii=False))
        report_path.write_text(json.dumps(report_rows, ensure_ascii=False, indent=2), encoding="utf-8")

        metric_names = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]
        summary = {
            name: _json_default(pd.to_numeric(df.get(name), errors="coerce").mean())
            for name in metric_names
            if name in df.columns
        }
        payload = {
            "kb_id": args.kb_id,
            "dataset": str(dataset_path),
            "rows": len(eval_rows),
            "top_k": args.top_k,
            "use_query_rewrite": args.use_query_rewrite,
            "answer_model": args.answer_model or settings.llm.DEFAULT_MODEL,
            "judge_model": args.judge_model or settings.llm.DEFAULT_MODEL,
            "summary": summary,
            "answers_path": str(answers_path),
            "report_path": str(report_path),
        }
        summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        print("RAGAS_SUMMARY=" + json.dumps(summary, ensure_ascii=False))
        print(f"ANSWERS_PATH={answers_path}")
        print(f"REPORT_PATH={report_path}")
        print(f"SUMMARY_PATH={summary_path}")
        return payload
    finally:
        await redis_manager.close()
        await db_manager.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="评估当前知识库 RAG 流程的 RAGas 脚本")
    parser.add_argument("--kb-id", type=int, required=True, help="知识库 ID")
    parser.add_argument("--dataset", required=True, help="QA JSON 数据集路径")
    parser.add_argument("--limit", type=int, default=None, help="只评估前 N 条")
    parser.add_argument("--top-k", type=int, default=4, help="最终给答案模型的上下文数量")
    parser.add_argument("--user-id", type=int, default=1, help="用于查询改写用量记录的用户 ID")
    parser.add_argument("--answer-model", default=None, help="答案生成模型，默认读取项目配置")
    parser.add_argument("--judge-model", default=None, help="RAGas 裁判模型，默认读取项目配置")
    parser.add_argument("--output-dir", default="scripts/ragas_reports", help="报告输出目录")
    parser.add_argument(
        "--use-query-rewrite",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="是否使用当前系统的查询改写链路",
    )
    return parser


if __name__ == "__main__":
    parsed_args = build_parser().parse_args()
    asyncio.run(run_evaluation(parsed_args))
