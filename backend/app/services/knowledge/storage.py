"""知识库原始分块存储组件：处理 sidecar 读写与候选片段加载。"""

from __future__ import annotations

import asyncio
import json
import os
from typing import List, Optional

from app.core.database import mysql_manager
from app.core.logger import logger_manager
from app.crud.knowledge import kb_crud
from app.models.knowledge import Document
from app.services.knowledge.types import ChunkCandidate
from app.services.shared.rag_text_cleaning import clean_rag_text, is_artifact_only_text

logger = logger_manager.get_logger(__name__)

_SIDECAR_SUFFIX = ".chunks.jsonl"


class KnowledgeStorage:
    """负责文档 sidecar 文件的原子写入、读取与预览。"""

    def __init__(self, service):
        """保存门面服务引用，便于复用统一路径与模型方法。"""
        self.service = service

    def _get_sidecar_path(self, file_path: str) -> str:
        """根据原文件路径生成 sidecar 路径。"""
        return f"{file_path}{_SIDECAR_SUFFIX}" if file_path else ""

    def _remove_sidecar_file(self, file_path: str) -> None:
        """删除指定文档对应的 sidecar 文件。"""
        sidecar_path = self.service._get_sidecar_path(file_path)
        if not sidecar_path:
            return
        try:
            if os.path.exists(sidecar_path):
                os.remove(sidecar_path)
        except Exception as exc:
            logger.warning(f"Remove sidecar failed for {sidecar_path}: {exc}")

    def _write_sidecar_atomic(self, sidecar_path: str, rows: List[dict]) -> None:
        """以临时文件替换方式原子写入 sidecar，避免半写入状态。"""
        dir_path = os.path.dirname(sidecar_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        tmp_path = f"{sidecar_path}.tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            os.replace(tmp_path, sidecar_path)
        except Exception:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
            raise

    def _read_sidecar_candidates(self, sidecar_path: str) -> List[ChunkCandidate]:
        """读取 sidecar 并转换为可检索的候选分块列表。"""
        if not sidecar_path or not os.path.exists(sidecar_path):
            return []

        candidates: List[ChunkCandidate] = []
        try:
            with open(sidecar_path, "r", encoding="utf-8") as handle:
                for line_no, line in enumerate(handle, start=1):
                    raw = line.strip()
                    if not raw:
                        continue
                    try:
                        item = json.loads(raw)
                    except Exception:
                        logger.warning(f"Invalid json line in sidecar {sidecar_path}:{line_no}")
                        continue

                    parent_id = str(item.get("parent_id") or "").strip()
                    content = clean_rag_text(item.get("content"))
                    if not parent_id or is_artifact_only_text(content):
                        continue

                    structured_meta = item.get("structured_meta")
                    if not isinstance(structured_meta, dict):
                        structured_meta = {}
                    if "parent_id" not in structured_meta:
                        structured_meta["parent_id"] = parent_id

                    candidates.append(
                        ChunkCandidate(
                            parent_id=parent_id,
                            content=content,
                            structured_meta=structured_meta,
                        )
                    )
        except Exception as exc:
            logger.warning(f"Read sidecar failed for {sidecar_path}: {exc}")

        return candidates

    def _read_sidecar_preview_by_parent_id(self, sidecar_path: str, target_parent_id: str) -> Optional[dict]:
        """按 parent_id 从 sidecar 中读取单条原始分块预览。"""
        if not sidecar_path or not os.path.exists(sidecar_path) or not target_parent_id:
            return None
        try:
            with open(sidecar_path, "r", encoding="utf-8") as handle:
                for line in handle:
                    raw = line.strip()
                    if not raw:
                        continue
                    try:
                        item = json.loads(raw)
                    except Exception:
                        continue
                    parent_id = str(item.get("parent_id") or "").strip()
                    if parent_id != target_parent_id:
                        continue
                    content = clean_rag_text(item.get("content"))
                    if is_artifact_only_text(content):
                        return None
                    structured_meta = item.get("structured_meta")
                    if not isinstance(structured_meta, dict):
                        structured_meta = {}
                    if "parent_id" not in structured_meta:
                        structured_meta["parent_id"] = target_parent_id
                    return {"content": content, "structured_meta": structured_meta}
        except Exception as exc:
            logger.warning(f"Read sidecar preview failed for {sidecar_path}: {exc}")
        return None

    def get_raw_chunk_preview_by_parent_id(self, doc: Document, parent_id: str) -> Optional[dict]:
        """根据 parent_id 获取文档原始分块预览。"""
        if not doc or not doc.file_path:
            return None
        sidecar_path = self.service._get_sidecar_path(doc.file_path)
        return self.service._read_sidecar_preview_by_parent_id(sidecar_path, str(parent_id or "").strip())

    def get_raw_chunk_preview(self, doc: Document, chunk_index: int) -> Optional[dict]:
        """根据 chunk 下标获取文档原始分块预览。"""
        if not doc or not doc.file_path:
            return None
        sidecar_path = self.service._get_sidecar_path(doc.file_path)
        target_parent_id = f"{doc.id}:{chunk_index}"
        return self.service._read_sidecar_preview_by_parent_id(sidecar_path, target_parent_id)

    async def _load_raw_candidates_from_storage(self, kb_id: int) -> List[ChunkCandidate]:
        """从数据库与 sidecar 联合加载并补全结构化元数据。"""
        async with mysql_manager.async_session_maker() as db:
            docs = await kb_crud.get_completed_documents(db, kb_id)
            chunk_rows = await kb_crud.get_kb_chunks(db, kb_id)

        if not docs:
            return []

        chunk_lookup = {str(chunk.parent_id): chunk for chunk in chunk_rows if chunk.parent_id}
        candidates: List[ChunkCandidate] = []
        for doc in docs:
            if not doc.file_path:
                continue
            sidecar_path = self.service._get_sidecar_path(doc.file_path)
            doc_candidates = await asyncio.to_thread(self.service._read_sidecar_candidates, sidecar_path)
            if not doc_candidates:
                logger.warning(f"No raw chunks loaded from sidecar: {sidecar_path}")
                continue
            for candidate in doc_candidates:
                row = chunk_lookup.get(candidate.parent_id)
                if not row:
                    continue
                structured_meta = (
                    dict(candidate.structured_meta)
                    if isinstance(candidate.structured_meta, dict)
                    else {}
                )

                chunk_meta = structured_meta.get("chunk")
                chunk_meta = dict(chunk_meta) if isinstance(chunk_meta, dict) else {}
                if row.id is not None and chunk_meta.get("id") in (None, ""):
                    chunk_meta["id"] = row.id
                if chunk_meta.get("index") is None:
                    chunk_meta["index"] = row.chunk_index
                structured_meta["chunk"] = chunk_meta

                doc_meta = structured_meta.get("doc")
                doc_meta = dict(doc_meta) if isinstance(doc_meta, dict) else {}
                if doc_meta.get("doc_id") is None:
                    doc_meta["doc_id"] = row.doc_id
                structured_meta["doc"] = doc_meta

                if structured_meta.get("parent_id") in (None, ""):
                    structured_meta["parent_id"] = row.parent_id
                candidate.structured_meta = structured_meta
            candidates.extend(doc_candidates)

        return candidates
