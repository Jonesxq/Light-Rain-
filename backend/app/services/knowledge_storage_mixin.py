"""知识库 sidecar 文件与原始分片读写。"""

import asyncio
import json
import os
from typing import List, Optional

from app.core.database import mysql_manager
from app.core.logger import logger_manager
from app.crud.knowledge import kb_crud
from app.models.knowledge import Document
from app.services.knowledge_types import ChunkCandidate

logger = logger_manager.get_logger(__name__)

_SIDECAR_SUFFIX = ".chunks.jsonl"


class KnowledgeStorageMixin:
    """Sidecar 文件读写与原始分片加载。"""

    def _get_sidecar_path(self, file_path: str) -> str:
        """根据文档路径拼出 sidecar 路径。"""
        return f"{file_path}{_SIDECAR_SUFFIX}" if file_path else ""

    def _remove_sidecar_file(self, file_path: str) -> None:
        """删除 sidecar 文件（失败仅记录日志）。"""
        sidecar_path = self._get_sidecar_path(file_path)
        if not sidecar_path:
            return
        try:
            if os.path.exists(sidecar_path):
                os.remove(sidecar_path)
        except Exception as e:
            logger.warning(f"Remove sidecar failed for {sidecar_path}: {e}")

    def _write_sidecar_atomic(self, sidecar_path: str, rows: List[dict]) -> None:
        """原子写入 sidecar（先写临时文件，再替换）。"""
        dir_path = os.path.dirname(sidecar_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        # 使用临时文件 + os.replace 保证写入原子性
        tmp_path = f"{sidecar_path}.tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                for row in rows:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
            os.replace(tmp_path, sidecar_path)
        except Exception:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
            raise

    def _read_sidecar_candidates(self, sidecar_path: str) -> List[ChunkCandidate]:
        """从 sidecar 读取原始分片候选列表。"""
        if not sidecar_path or not os.path.exists(sidecar_path):
            return []

        candidates: List[ChunkCandidate] = []
        try:
            with open(sidecar_path, "r", encoding="utf-8") as f:
                for line_no, line in enumerate(f, start=1):
                    raw = line.strip()
                    if not raw:
                        continue
                    try:
                        item = json.loads(raw)
                    except Exception:
                        logger.warning(f"Invalid json line in sidecar {sidecar_path}:{line_no}")
                        continue

                    parent_id = str(item.get("parent_id") or "").strip()
                    content = (item.get("content") or "").strip()
                    if not parent_id or not content:
                        continue

                    # 兜底 structured_meta，确保 parent_id 存在
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
        except Exception as e:
            logger.warning(f"Read sidecar failed for {sidecar_path}: {e}")

        return candidates

    def get_raw_chunk_preview(self, doc: Document, chunk_index: int) -> Optional[dict]:
        """从 sidecar 读取单个原始分片预览。"""
        if not doc or not doc.file_path:
            return None
        sidecar_path = self._get_sidecar_path(doc.file_path)
        if not sidecar_path or not os.path.exists(sidecar_path):
            return None

        target_parent_id = f"{doc.id}:{chunk_index}"
        try:
            with open(sidecar_path, "r", encoding="utf-8") as f:
                for line in f:
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
                    content = (item.get("content") or "").strip()
                    structured_meta = item.get("structured_meta")
                    if not isinstance(structured_meta, dict):
                        structured_meta = {}
                    if "parent_id" not in structured_meta:
                        structured_meta["parent_id"] = target_parent_id
                    return {
                        "content": content,
                        "structured_meta": structured_meta,
                    }
        except Exception as e:
            logger.warning(f"Read sidecar preview failed for {sidecar_path}: {e}")

        return None

    async def _load_raw_candidates_from_storage(self, kb_id: int) -> List[ChunkCandidate]:
        """从存储与 sidecar 加载原始分片候选。"""
        async with mysql_manager.async_session_maker() as db:
            docs = await kb_crud.get_completed_documents(db, kb_id)

        if not docs:
            return []

        candidates: List[ChunkCandidate] = []
        for doc in docs:
            if not doc.file_path:
                continue
            sidecar_path = self._get_sidecar_path(doc.file_path)
            doc_candidates = await asyncio.to_thread(self._read_sidecar_candidates, sidecar_path)
            if not doc_candidates:
                logger.warning(f"No raw chunks loaded from sidecar: {sidecar_path}")
                continue
            candidates.extend(doc_candidates)

        return candidates
