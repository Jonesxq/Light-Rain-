"""知识库Sidecar文件与原始分片读写模块"""

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
    """Sidecar文件读写与原始分片加载Mixin：提供文档分片的持久化和加载功能"""

    def _get_sidecar_path(self, file_path: str) -> str:
        """根据文档路径拼接出sidecar文件路径
        
        Args:
            file_path: 原始文档路径
            
        Returns:
            Sidecar文件路径
        """
        return f"{file_path}{_SIDECAR_SUFFIX}" if file_path else ""

    def _remove_sidecar_file(self, file_path: str) -> None:
        """删除sidecar文件（失败仅记录警告日志）
        
        Args:
            file_path: 原始文档路径
        """
        sidecar_path = self._get_sidecar_path(file_path)
        if not sidecar_path:
            return
        try:
            if os.path.exists(sidecar_path):
                os.remove(sidecar_path)
        except Exception as e:
            logger.warning(f"Remove sidecar failed for {sidecar_path}: {e}")

    def _write_sidecar_atomic(self, sidecar_path: str, rows: List[dict]) -> None:
        """原子写入sidecar文件（先写临时文件，再替换）
        
        Args:
            sidecar_path: Sidecar文件路径
            rows: 要写入的行数据列表
        """
        dir_path = os.path.dirname(sidecar_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
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
        """从sidecar文件读取原始分片候选列表
        
        Args:
            sidecar_path: Sidecar文件路径
            
        Returns:
            候选分片列表
        """
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

    def _read_sidecar_preview_by_parent_id(self, sidecar_path: str, target_parent_id: str) -> Optional[dict]:
        """按parent_id从sidecar读取单个原始分片
        
        Args:
            sidecar_path: Sidecar文件路径
            target_parent_id: 目标parent_id
            
        Returns:
            包含content和structured_meta的字典，或None
        """
        if not sidecar_path or not os.path.exists(sidecar_path):
            return None
        if not target_parent_id:
            return None
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

    def get_raw_chunk_preview_by_parent_id(self, doc: Document, parent_id: str) -> Optional[dict]:
        """按parent_id读取单个原始分片预览
        
        Args:
            doc: 文档对象
            parent_id: 父分片ID
            
        Returns:
            包含content和structured_meta的字典，或None
        """
        if not doc or not doc.file_path:
            return None
        sidecar_path = self._get_sidecar_path(doc.file_path)
        return self._read_sidecar_preview_by_parent_id(sidecar_path, str(parent_id or "").strip())

    def get_raw_chunk_preview(self, doc: Document, chunk_index: int) -> Optional[dict]:
        """从sidecar读取单个原始分片预览（按chunk_index）
        
        Args:
            doc: 文档对象
            chunk_index: 分片索引
            
        Returns:
            包含content和structured_meta的字典，或None
        """
        if not doc or not doc.file_path:
            return None
        sidecar_path = self._get_sidecar_path(doc.file_path)
        target_parent_id = f"{doc.id}:{chunk_index}"
        return self._read_sidecar_preview_by_parent_id(sidecar_path, target_parent_id)

    async def _load_raw_candidates_from_storage(self, kb_id: int) -> List[ChunkCandidate]:
        """从存储与sidecar加载原始分片候选
        
        Args:
            kb_id: 知识库ID
            
        Returns:
            候选分片列表
        """
        async with mysql_manager.async_session_maker() as db:
            docs = await kb_crud.get_completed_documents(db, kb_id)
            chunk_rows = await kb_crud.get_kb_chunks(db, kb_id)

        if not docs:
            return []

        chunk_lookup = {str(c.parent_id): c for c in chunk_rows if c.parent_id}
        candidates: List[ChunkCandidate] = []
        for doc in docs:
            if not doc.file_path:
                continue
            sidecar_path = self._get_sidecar_path(doc.file_path)
            doc_candidates = await asyncio.to_thread(self._read_sidecar_candidates, sidecar_path)
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
                if isinstance(chunk_meta, dict):
                    chunk_meta = dict(chunk_meta)
                else:
                    chunk_meta = {}
                if row.id is not None and chunk_meta.get("id") in (None, ""):
                    chunk_meta["id"] = row.id
                if chunk_meta.get("index") is None:
                    chunk_meta["index"] = row.chunk_index
                structured_meta["chunk"] = chunk_meta

                doc_meta = structured_meta.get("doc")
                if isinstance(doc_meta, dict):
                    doc_meta = dict(doc_meta)
                else:
                    doc_meta = {}
                if doc_meta.get("doc_id") is None:
                    doc_meta["doc_id"] = row.doc_id
                structured_meta["doc"] = doc_meta

                if structured_meta.get("parent_id") in (None, ""):
                    structured_meta["parent_id"] = row.parent_id
                candidate.structured_meta = structured_meta
            candidates.extend(doc_candidates)

        return candidates
