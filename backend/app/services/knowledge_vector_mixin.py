"""知识库向量检索与元数据解析模块"""

from typing import List, Optional

from sqlmodel import select

from app.core.database import mysql_manager
from app.core.logger import logger_manager
from app.models.knowledge import DocumentChunk

logger = logger_manager.get_logger(__name__)


class KnowledgeVectorMixin:
    """向量检索与元数据解析Mixin：提供向量检索和元数据处理功能"""

    async def _semantic_search_global(self, kb_id: int, query: str, top_k: int):
        """全局向量检索（失败则返回空列表）
        
        Args:
            kb_id: 知识库ID
            query: 查询文本
            top_k: 返回结果数量
            
        Returns:
            向量检索结果文档列表（失败返回空列表）
        """
        if top_k <= 0:
            return []
        try:
            vector_db = self._get_vector_store(kb_id)
            return await vector_db.asimilarity_search(query, k=top_k)
        except Exception as e:
            logger.warning(f"Global semantic search failed: {e}")
            return []

    def _extract_parent_id_from_meta(self, meta: Optional[dict]) -> Optional[str]:
        """从元数据中解析parent_id（含多级兜底策略）
        
        Args:
            meta: 元数据字典
            
        Returns:
            解析出的parent_id字符串，或None
        """
        if not isinstance(meta, dict):
            return None

        parent_id = meta.get("parent_id")
        if parent_id not in (None, ""):
            return str(parent_id)

        doc_meta = meta.get("doc", {}) if isinstance(meta.get("doc"), dict) else {}
        chunk_meta = meta.get("chunk", {}) if isinstance(meta.get("chunk"), dict) else {}
        doc_id = doc_meta.get("doc_id")
        chunk_index = chunk_meta.get("index")
        if doc_id is not None and chunk_index is not None:
            return f"{doc_id}:{chunk_index}"
        return None

    async def _load_structured_meta_by_vector_ids(self, vector_ids: List[str]) -> dict[str, dict]:
        """批量加载向量ID对应的结构化元数据
        
        Args:
            vector_ids: 向量ID列表
            
        Returns:
            向量ID到结构化元数据的字典映射
        """
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
            structured_meta = chunk.structured_meta if isinstance(chunk.structured_meta, dict) else {}
            merged_meta = dict(structured_meta)

            chunk_meta = merged_meta.get("chunk")
            if isinstance(chunk_meta, dict):
                chunk_meta = dict(chunk_meta)
            else:
                chunk_meta = {}
            if chunk.id is not None and chunk_meta.get("id") in (None, ""):
                chunk_meta["id"] = chunk.id
            if chunk_meta.get("index") is None:
                chunk_meta["index"] = chunk.chunk_index
            merged_meta["chunk"] = chunk_meta

            doc_meta = merged_meta.get("doc")
            if isinstance(doc_meta, dict):
                doc_meta = dict(doc_meta)
            else:
                doc_meta = {}
            if doc_meta.get("doc_id") is None:
                doc_meta["doc_id"] = chunk.doc_id
            merged_meta["doc"] = doc_meta

            if merged_meta.get("parent_id") in (None, "") and chunk.parent_id:
                merged_meta["parent_id"] = chunk.parent_id
            meta_map[str(chunk.vector_id)] = merged_meta
        return meta_map
