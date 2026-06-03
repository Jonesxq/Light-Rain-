"""Reindex completed PDF documents in a knowledge base."""

from __future__ import annotations

import argparse
import asyncio
import json
from contextlib import contextmanager
from typing import Any

from app.core.config.settings import settings
from app.core.database import db_manager, mysql_manager
from app.core.redis import redis_manager
from app.crud.knowledge import kb_crud
from app.models.knowledge import DocStatus
from app.services.knowledge import kb_service


def _status_value(status: Any) -> str:
    if isinstance(status, DocStatus):
        value = status.value
    else:
        value = str(status or "")
    if "." in value:
        value = value.rsplit(".", 1)[-1]
    return value.upper()


@contextmanager
def _summary_skip_override(skip_summaries: bool):
    original = settings.llm.RAG_SUMMARY_MAX_CHUNKS
    if skip_summaries:
        settings.llm.RAG_SUMMARY_MAX_CHUNKS = 0
    try:
        yield
    finally:
        settings.llm.RAG_SUMMARY_MAX_CHUNKS = original


async def _load_documents(kb_id: int, file_type: str, statuses: set[str]) -> list[Any]:
    async with mysql_manager.async_session_maker() as db:
        docs = await kb_crud.get_kb_documents(db, kb_id)
    normalized_type = file_type.lower().strip()
    return [
        doc
        for doc in docs
        if str(doc.file_type or "").lower() == normalized_type
        and _status_value(doc.status) in statuses
    ]


async def _get_document_snapshot(doc_id: int) -> dict[str, Any] | None:
    async with mysql_manager.async_session_maker() as db:
        doc = await kb_crud.get_document(db, doc_id)
    if not doc:
        return None
    return {
        "doc_id": doc.id,
        "file_name": doc.file_name,
        "file_type": doc.file_type,
        "status": doc.status.value if isinstance(doc.status, DocStatus) else str(doc.status),
        "chunk_count": doc.chunk_count,
        "error_msg": doc.error_msg,
    }


async def run(args: argparse.Namespace) -> dict[str, Any]:
    await db_manager.initialize()
    await redis_manager.initialize_async()
    results: list[dict[str, Any]] = []
    try:
        statuses = {
            status.strip().upper()
            for status in args.statuses.split(",")
            if status.strip()
        }
        docs = await _load_documents(args.kb_id, args.file_type, statuses)
        docs.sort(key=lambda doc: str(doc.file_name or ""))

        with _summary_skip_override(args.skip_summaries):
            for index, doc in enumerate(docs, start=1):
                before = {
                    "doc_id": doc.id,
                    "file_name": doc.file_name,
                    "status": _status_value(doc.status),
                    "chunk_count": doc.chunk_count,
                }
                print(f"[{index}/{len(docs)}] reindex doc_id={doc.id} file={doc.file_name}", flush=True)
                ok = await kb_service.reindex_document(int(doc.id))
                await redis_manager.delete_async(
                    f"kb:raw_chunks:{args.kb_id}",
                    f"kb:chunks:{args.kb_id}",
                )
                after = await _get_document_snapshot(int(doc.id))
                results.append({"ok": ok, "before": before, "after": after})

        await redis_manager.delete_async(
            f"kb:raw_chunks:{args.kb_id}",
            f"kb:chunks:{args.kb_id}",
        )

        payload = {
            "kb_id": args.kb_id,
            "file_type": args.file_type,
            "statuses": sorted(statuses),
            "skip_summaries": args.skip_summaries,
            "documents": len(results),
            "results": results,
        }
        print("REINDEX_SUMMARY=" + json.dumps(payload, ensure_ascii=False))
        return payload
    finally:
        await redis_manager.close()
        await db_manager.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reindex completed PDF documents in a knowledge base")
    parser.add_argument("--kb-id", type=int, required=True)
    parser.add_argument("--file-type", default=".pdf")
    parser.add_argument("--statuses", default="COMPLETED", help="Comma-separated document statuses to reindex")
    parser.add_argument("--skip-summaries", action="store_true", help="Use cleaned raw chunks as vector text")
    return parser


if __name__ == "__main__":
    asyncio.run(run(build_parser().parse_args()))
