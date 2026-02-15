"""知识库导入/重建/删除流程。"""

import asyncio
import os
import re
from typing import List, Tuple

from langchain_core.documents import Document as LangChainDocument
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.constant.prompts import CHUNK_SUMMARY_SYSTEM_PROMPT
from app.core.config.settings import settings
from app.core.database import mysql_manager
from app.core.logger import logger_manager
from app.crud.knowledge import kb_crud
from app.models.knowledge import DocStatus, Document
from app.services.usage import usage_service, UsageTimer

logger = logger_manager.get_logger(__name__)


class KnowledgeIngestMixin:
    """知识库文档处理与清理能力。"""

    def _normalize_milvus_delete_ids(self, vector_ids: List[str]) -> Tuple[List[int], int]:
        """规范化 Milvus 删除 ID，返回有效 ID 与跳过数量。"""
        normalized_ids: List[int] = []
        seen: set[int] = set()
        skipped = 0
        for raw_id in vector_ids:
            if raw_id is None:
                continue
            raw_str = str(raw_id).strip()
            if not raw_str:
                continue
            if not re.fullmatch(r"-?\d+", raw_str):
                skipped += 1
                continue
            value = int(raw_str)
            if value in seen:
                continue
            seen.add(value)
            normalized_ids.append(value)
        return normalized_ids, skipped

    async def _summarize_chunk(self, llm: ChatOpenAI, raw_text: str, max_chars: int) -> tuple[str, dict]:
        """单个分片摘要（失败回退原文）。"""
        if not raw_text:
            return "", {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None, "token_missing": True}
        try:
            messages = [
                SystemMessage(content=CHUNK_SUMMARY_SYSTEM_PROMPT.format(max_chars=max_chars)),
                HumanMessage(content=raw_text),
            ]
            response = await llm.ainvoke(messages)
            summary = (getattr(response, "content", "") or "").strip()
            usage = usage_service.extract_usage(response)
            if not summary:
                return raw_text, usage
            if len(summary) > max_chars:
                return summary[:max_chars], usage
            return summary, usage
        except Exception as e:
            logger.warning(f"Chunk summary failed, fallback to raw chunk: {e}")
            return raw_text, {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None, "token_missing": True}

    async def _summarize_chunks(self, raw_chunks: List[str]) -> tuple[List[str], dict]:
        """并发摘要多个分片并聚合 token 统计。"""
        if not raw_chunks:
            return [], {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "token_missing": 0}

        # 控制并发，避免摘要过载
        llm = self._get_summary_llm()
        max_chars = max(50, int(settings.llm.RAG_SUMMARY_MAX_CHARS))
        concurrency = max(1, int(settings.llm.RAG_SUMMARY_CONCURRENCY))
        semaphore = asyncio.Semaphore(concurrency)
        summaries = [""] * len(raw_chunks)
        usage_rows: list[dict] = [{} for _ in raw_chunks]

        async def worker(idx: int, text: str) -> None:
            """摘要并发任务（受信号量控制）。"""
            async with semaphore:
                summary, usage = await self._summarize_chunk(llm, text, max_chars)
                summaries[idx] = summary
                usage_rows[idx] = usage

        await asyncio.gather(*(worker(i, text) for i, text in enumerate(raw_chunks)))

        agg = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "token_missing": 0}
        for usage in usage_rows:
            if not usage or usage.get("token_missing"):
                agg["token_missing"] += 1
                continue
            prompt_tokens = usage.get("prompt_tokens") or 0
            completion_tokens = usage.get("completion_tokens") or 0
            total_tokens = usage.get("total_tokens")
            if total_tokens is None:
                total_tokens = prompt_tokens + completion_tokens
            agg["prompt_tokens"] += prompt_tokens
            agg["completion_tokens"] += completion_tokens
            agg["total_tokens"] += total_tokens or 0

        return summaries, agg

    async def ingest_document(self, doc_id: int):
        """导入文档：分块 -> 摘要 -> sidecar -> 向量入库。"""
        async with mysql_manager.async_session_maker() as db:
            doc = await db.get(Document, doc_id)
            if not doc:
                logger.error(f"Ingest Error: Document {doc_id} not found.")
                return

            kb_owner_id = None
            try:
                kb_row = await kb_crud.get_kb(db, doc.kb_id)
                if kb_row:
                    kb_owner_id = kb_row.user_id
            except Exception:
                kb_owner_id = None

            try:
                logger.info(f"Starting to process document: {doc.file_name}")
                if not doc.file_path or not os.path.exists(doc.file_path):
                    raise FileNotFoundError(f"Document file not found: {doc.file_path}")

                base_meta = {
                    "doc": {
                        "doc_id": doc.id,
                        "kb_id": doc.kb_id,
                        "file_name": doc.file_name,
                        "file_type": doc.file_type,
                        "file_size": doc.file_size,
                    }
                }
                # 先做文档分块（包含基础元信息）
                chunks = self.chunker.load_and_split(
                    doc.file_path,
                    doc.file_type,
                    base_meta=base_meta,
                )
                if not chunks:
                    raise ValueError("Document chunking produced empty result.")

                # 组织原始分片与结构化元数据
                prepared_rows: List[dict] = []
                for chunk in chunks:
                    raw_content = (chunk.page_content or "").strip()
                    if not raw_content:
                        continue

                    chunk_index = len(prepared_rows)
                    parent_id = f"{doc.id}:{chunk_index}"
                    structured_meta = dict(chunk.metadata or {})
                    chunk_meta = structured_meta.get("chunk")
                    if isinstance(chunk_meta, dict):
                        chunk_meta["index"] = chunk_index
                    else:
                        structured_meta["chunk"] = {
                            "index": chunk_index,
                            "char_len": len(raw_content),
                        }
                    structured_meta["parent_id"] = parent_id

                    prepared_rows.append(
                        {
                            "parent_id": parent_id,
                            "chunk_index": chunk_index,
                            "raw_content": raw_content,
                            "structured_meta": structured_meta,
                        }
                    )

                if not prepared_rows:
                    raise ValueError("Document chunking produced empty content.")

                await kb_crud.update_document_status(
                    db,
                    doc_id=doc.id,
                    status=DocStatus.PROCESSING,
                    chunk_count=len(prepared_rows),
                    error_msg="",
                )

                # 生成摘要（用于向量检索）
                raw_contents = [row["raw_content"] for row in prepared_rows]
                summary_timer = UsageTimer()
                summaries, summary_usage = await self._summarize_chunks(raw_contents)
                summary_latency_ms = summary_timer.stop_ms()

                if kb_owner_id is not None:
                    cost_usd = usage_service.compute_cost(
                        settings.llm.DEFAULT_MODEL,
                        summary_usage.get("prompt_tokens"),
                        summary_usage.get("completion_tokens"),
                    )
                    await usage_service.record_event(
                        db,
                        user_id=kb_owner_id,
                        event_type="kb_summary",
                        model_name=settings.llm.DEFAULT_MODEL,
                        prompt_tokens=summary_usage.get("prompt_tokens"),
                        completion_tokens=summary_usage.get("completion_tokens"),
                        total_tokens=summary_usage.get("total_tokens"),
                        token_missing=summary_usage.get("token_missing", 0) > 0,
                        latency_ms=summary_latency_ms,
                        cost_usd=cost_usd,
                        success=True,
                        metadata={
                            "kb_id": doc.kb_id,
                            "doc_id": doc.id,
                            "chunk_count": len(prepared_rows),
                        },
                    )
                if len(summaries) != len(prepared_rows):
                    raise ValueError("Chunk summary count mismatch.")

                # 写 sidecar（保存原始分片，便于预览与回填）
                sidecar_path = self._get_sidecar_path(doc.file_path)
                sidecar_rows = [
                    {
                        "parent_id": row["parent_id"],
                        "content": row["raw_content"],
                        "structured_meta": row["structured_meta"],
                        "token_count": 0,
                    }
                    for row in prepared_rows
                ]
                await asyncio.to_thread(self._write_sidecar_atomic, sidecar_path, sidecar_rows)

                # 摘要入向量库
                milvus_docs = [
                    LangChainDocument(
                        page_content=summary,
                        metadata={
                            # 仅保留字符串字段，兼容已有 schema（避免 dict 写入 VARCHAR）
                            "source": str(doc.file_name or doc.file_path or "")
                        },
                    )
                    for summary in summaries
                ]
                vector_db = self._get_vector_store(doc.kb_id)
                ids = await asyncio.to_thread(vector_db.add_documents, milvus_docs)
                if not ids or len(ids) != len(prepared_rows):
                    raise ValueError("Milvus returned invalid ids for summary chunks.")

                # 写入数据库分片表，保存向量 ID
                for row, summary, v_id in zip(prepared_rows, summaries, ids):
                    await kb_crud.create_chunk(
                        db,
                        doc_id=doc.id,
                        parent_id=row["parent_id"],
                        content=summary,
                        vector_id=str(v_id),
                        chunk_index=row["chunk_index"],
                        token_count=0,
                        structured_meta=row["structured_meta"],
                    )

                # 更新文档状态并清理缓存
                await kb_crud.update_document_status(
                    db,
                    doc_id=doc.id,
                    status=DocStatus.COMPLETED,
                    chunk_count=len(prepared_rows),
                )
                self._invalidate_bm25_cache(doc.kb_id)
                logger.info(
                    f"Successfully processed: {doc.file_name}, created {len(prepared_rows)} summary chunks."
                )

            except Exception as e:
                if kb_owner_id is not None:
                    try:
                        await usage_service.record_event(
                            db,
                            user_id=kb_owner_id,
                            event_type="kb_summary",
                            model_name=settings.llm.DEFAULT_MODEL,
                            prompt_tokens=None,
                            completion_tokens=None,
                            total_tokens=None,
                            token_missing=True,
                            latency_ms=None,
                            cost_usd=0.0,
                            success=False,
                            error_message=str(e),
                            metadata={"kb_id": doc.kb_id, "doc_id": doc.id, "chunk_count": len(prepared_rows)},
                        )
                    except Exception:
                        pass
                logger.error(f"Failed to ingest document {doc.id}: {str(e)}")
                # 失败时清理 sidecar，避免脏数据
                self._remove_sidecar_file(doc.file_path)
                await kb_crud.update_document_status(
                    db,
                    doc_id=doc.id,
                    status=DocStatus.FAILED,
                    error_msg=str(e),
                )

    async def reindex_document(self, doc_id: int) -> bool:
        """重建文档索引（删除旧向量与分片后再导入）。"""
        async with mysql_manager.async_session_maker() as db:
            doc = await db.get(Document, doc_id)
            if not doc:
                return False

            # 删除已有向量
            chunks = await kb_crud.get_document_chunks(db, doc_id)
            vector_ids = [c.vector_id for c in chunks if c.vector_id]
            if vector_ids:
                delete_ids, skipped = self._normalize_milvus_delete_ids(vector_ids)
                if skipped:
                    logger.warning(f"Skip {skipped} non-numeric Milvus ids for doc {doc_id}.")
                try:
                    if delete_ids:
                        vector_db = self._get_vector_store(doc.kb_id)
                        await asyncio.to_thread(vector_db.delete, ids=delete_ids)
                except Exception as e:
                    logger.warning(f"Milvus delete failed for doc {doc_id}: {e}")

            # 清理旧分片与 sidecar
            await kb_crud.delete_document_chunks(db, doc_id)
            self._remove_sidecar_file(doc.file_path)

            await kb_crud.update_document_status(
                db,
                doc_id=doc_id,
                status=DocStatus.PROCESSING,
                chunk_count=0,
                error_msg="",
            )

        await self.ingest_document(doc_id)
        return True

    async def delete_document(self, kb_id: int, doc_id: int) -> bool:
        """删除单个文档（包含向量与文件清理）。"""
        async with mysql_manager.async_session_maker() as db:
            doc = await kb_crud.get_document(db, doc_id)
            if not doc or doc.kb_id != kb_id:
                return False

            # 删除向量数据
            chunks = await kb_crud.get_document_chunks(db, doc_id)
            vector_ids = [c.vector_id for c in chunks if c.vector_id]
            if vector_ids:
                delete_ids, skipped = self._normalize_milvus_delete_ids(vector_ids)
                if skipped:
                    logger.warning(f"Skip {skipped} non-numeric Milvus ids for doc {doc_id}.")
                try:
                    if delete_ids:
                        vector_db = self._get_vector_store(kb_id)
                        await asyncio.to_thread(vector_db.delete, ids=delete_ids)
                except Exception as e:
                    logger.warning(f"Milvus delete failed for doc {doc_id}: {e}")

            # 删除 sidecar 与原文件
            self._remove_sidecar_file(doc.file_path)
            if doc.file_path and os.path.exists(doc.file_path):
                try:
                    os.remove(doc.file_path)
                except Exception as e:
                    logger.warning(f"Remove file failed for doc {doc_id}: {e}")

            success = await kb_crud.delete_document(db, doc_id)
            if success:
                self._invalidate_bm25_cache(kb_id)
            return success

    async def delete_kb(self, kb_id: int) -> bool:
        """删除知识库（包含所有文档/向量/sidecar）。"""
        async with mysql_manager.async_session_maker() as db:
            kb = await kb_crud.get_kb(db, kb_id)
            if not kb:
                return False

            # 汇总所有向量 ID 并清理文件
            docs = await kb_crud.get_kb_documents(db, kb_id)
            vector_ids: List[str] = []
            for doc in docs:
                chunks = await kb_crud.get_document_chunks(db, doc.id)
                vector_ids.extend([c.vector_id for c in chunks if c.vector_id])
                self._remove_sidecar_file(doc.file_path)
                if doc.file_path and os.path.exists(doc.file_path):
                    try:
                        os.remove(doc.file_path)
                    except Exception as e:
                        logger.warning(f"Remove file failed for doc {doc.id}: {e}")

            if vector_ids:
                delete_ids, skipped = self._normalize_milvus_delete_ids(vector_ids)
                if skipped:
                    logger.warning(f"Skip {skipped} non-numeric Milvus ids for kb {kb_id}.")
                try:
                    if delete_ids:
                        vector_db = self._get_vector_store(kb_id)
                        await asyncio.to_thread(vector_db.delete, ids=delete_ids)
                except Exception as e:
                    logger.warning(f"Milvus delete failed for kb {kb_id}: {e}")

            success = await kb_crud.delete_kb(db, kb_id)
            if success:
                self._invalidate_bm25_cache(kb_id)
            return success
