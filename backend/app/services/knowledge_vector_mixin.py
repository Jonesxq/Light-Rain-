"""知识库向量检索与元数据解析。"""

from typing import List, Optional

from sqlmodel import select

from app.core.database import mysql_manager
from app.core.logger import logger_manager
from app.models.knowledge import DocumentChunk

logger = logger_manager.get_logger(__name__)


class KnowledgeVectorMixin:
    """向量检索与元数据解析能力。"""

    async def _semantic_search_global(self, kb_id: int, query: str, top_k: int):
        """全局向量检索（失败则返回空）。"""
        if top_k <= 0:
            return []
        try:
            vector_db = self._get_vector_store(kb_id)
            return await vector_db.asimilarity_search(query, k=top_k)
        except Exception as e:
            logger.warning(f"Global semantic search failed: {e}")
            return []

    def _extract_parent_id_from_meta(self, meta: Optional[dict]) -> Optional[str]:
        """从元数据中解析 parent_id（含多级兜底）。"""
        if not isinstance(meta, dict):
            return None

        # 优先使用显式 parent_id
        parent_id = meta.get("parent_id")
        if parent_id not in (None, ""):
            return str(parent_id)

        # 兜底：尝试从 doc/ chunk 信息拼出 parent_id
        doc_meta = meta.get("doc", {}) if isinstance(meta.get("doc"), dict) else {}
        chunk_meta = meta.get("chunk", {}) if isinstance(meta.get("chunk"), dict) else {}
        doc_id = doc_meta.get("doc_id")
        chunk_index = chunk_meta.get("index")
        if doc_id is not None and chunk_index is not None:
            return f"{doc_id}:{chunk_index}"
        return None

    async def _load_structured_meta_by_vector_ids(self, vector_ids: List[str]) -> dict[str, dict]:
        """批量加载向量 ID 对应的结构化元数据。"""
        if not vector_ids:
            return {}

        async with mysql_manager.async_session_maker() as db:
            statement = select(DocumentChunk).where(DocumentChunk.vector_id.in_(vector_ids))
            result = await db.execute(statement)
            chunks = list(result.scalars().all())

        meta_map: dict[str, dict] = {}
        for chunk in chunks:
            if not chunk.vector_id:
                continue
            meta_map[str(chunk.vector_id)] = chunk.structured_meta or {}
        return meta_map
