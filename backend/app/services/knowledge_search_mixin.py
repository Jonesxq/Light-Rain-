"""知识库检索与重排逻辑模块"""

import asyncio
from http import HTTPStatus
from typing import List, Optional, Tuple

from dashscope import TextReRank

from app.core.config.settings import settings
from app.core.logger import logger_manager
from app.services.knowledge_types import ChunkCandidate, SearchItem
from app.services.query_rewrite import query_rewrite_service

logger = logger_manager.get_logger(__name__)


class KnowledgeSearchMixin:
    """检索与重排Mixin：提供BM25、语义检索、RRF融合和重排功能"""

    async def _items_from_documents(
        self,
        docs,
        raw_lookup: Optional[dict[str, ChunkCandidate]] = None,
    ) -> List[SearchItem]:
        """从向量检索结果中构建SearchItem列表
        
        Args:
            docs: 向量检索结果文档列表
            raw_lookup: 原始分片查找表
            
        Returns:
            SearchItem列表
        """
        items: List[SearchItem] = []
        vector_ids: List[str] = []
        item_vector_ids: List[Optional[str]] = []

        for doc in docs or []:
            content = getattr(doc, "page_content", None)
            meta = getattr(doc, "metadata", None) or {}
            if not content:
                continue

            pk = meta.get("pk") or meta.get("id")
            pk_str = str(pk) if pk is not None else None
            if pk_str:
                vector_ids.append(pk_str)
            item_vector_ids.append(pk_str)
            items.append(SearchItem(content=content, meta=meta))

        if not items:
            return []

        meta_map = await self._load_structured_meta_by_vector_ids(vector_ids)
        raw_lookup = raw_lookup or {}
        enriched: List[SearchItem] = []
        for item, pk_str in zip(items, item_vector_ids):
            structured_meta = meta_map.get(pk_str) if pk_str else None
            merged_meta = structured_meta or item.meta or {}
            parent_id = self._extract_parent_id_from_meta(merged_meta)

            if parent_id and parent_id in raw_lookup:
                enriched.append(SearchItem(content=raw_lookup[parent_id].content, meta=merged_meta))
                continue

            if parent_id:
                logger.warning(f"Raw chunk not found for parent_id={parent_id}, fallback to summary text.")
            enriched.append(SearchItem(content=item.content, meta=merged_meta))

        return enriched

    async def _gte_rerank_items(self, query: str, items: List[SearchItem], top_k: int) -> List[SearchItem]:
        """使用GTE rerank模型重排（失败则回退原顺序）
        
        Args:
            query: 查询文本
            items: 待重排的SearchItem列表
            top_k: 返回结果数量
            
        Returns:
            重排后的SearchItem列表
        """
        if not items or top_k <= 0:
            return []

        documents = [item.content for item in items]
        top_n = min(top_k, len(documents))
        try:
            response = await asyncio.to_thread(
                TextReRank.call,
                model=settings.llm.RERANK_MODEL,
                query=query,
                documents=documents,
                top_n=top_n,
                api_key=settings.llm.QWEN_API_KEY,
                return_documents=False,
            )
            if response and response.status_code == HTTPStatus.OK:
                results = getattr(response.output, "results", []) or []
                ranked = sorted(results, key=lambda r: r.relevance_score, reverse=True)
                reranked = [items[r.index] for r in ranked if 0 <= r.index < len(items)]
                if reranked:
                    return reranked[:top_n]
        except Exception as e:
            logger.warning(f"GTE rerank failed, fallback to fusion order: {e}")

        return items[:top_n]

    def _build_sources(self, items: List[SearchItem], max_sources: int = 5) -> List[dict]:
        """构建来源列表（去重 + 限量）
        
        Args:
            items: SearchItem列表
            max_sources: 最大来源数量
            
        Returns:
            来源信息字典列表
        """
        sources: List[dict] = []
        seen = set()

        for item in items:
            meta = item.meta or {}
            doc_meta = meta.get("doc", {}) if isinstance(meta.get("doc"), dict) else {}
            source_meta = meta.get("source", {}) if isinstance(meta.get("source"), dict) else {}
            loc_meta = meta.get("loc", {}) if isinstance(meta.get("loc"), dict) else {}
            chunk_meta = meta.get("chunk", {}) if isinstance(meta.get("chunk"), dict) else {}

            source = {
                "doc_id": doc_meta.get("doc_id"),
                "file_name": doc_meta.get("file_name") or source_meta.get("file_name"),
                "file_type": doc_meta.get("file_type") or source_meta.get("file_type"),
                "pages": loc_meta.get("pages"),
                "slides": loc_meta.get("slides"),
                "paragraphs": loc_meta.get("paragraphs"),
                "tables": loc_meta.get("tables"),
                "md_headings": loc_meta.get("md_headings"),
                "chunk_id": chunk_meta.get("id"),
                "chunk_index": chunk_meta.get("index"),
            }

            source = {k: v for k, v in source.items() if v not in (None, "", [], {})}
            if not source:
                continue

            key = (
                source.get("chunk_id"),
                source.get("doc_id"),
                source.get("chunk_index"),
                source.get("file_name"),
                tuple(source.get("pages", []) or []),
                source.get("md_headings"),
            )
            if key in seen:
                continue
            seen.add(key)
            sources.append(source)

            if len(sources) >= max_sources:
                break

        return sources

    async def search_knowledge(
        self,
        kb_id: int,
        query: str,
        top_k: int = 3,
        rewritten_query: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> Tuple[str, List[dict]]:
        """检索知识库：BM25优先，语义兜底，RRF融合后重排
        
        Args:
            kb_id: 知识库ID
            query: 查询文本
            top_k: 返回结果数量
            rewritten_query: 重写后的查询（可选）
            user_id: 用户ID（可选）
            
        Returns:
            元组(上下文文本, 来源信息列表)
        """
        try:
            if rewritten_query is None:
                rewritten_query = await query_rewrite_service.rewrite_query(query, user_id=user_id, kb_id=kb_id)
            effective_query = rewritten_query or query

            candidates, bm25 = await self._get_bm25_index(kb_id)
            raw_lookup = self._build_raw_lookup(candidates)
            if not candidates or bm25 is None:
                semantic_docs = await self._semantic_search_global(
                    kb_id=kb_id,
                    query=effective_query,
                    top_k=max(settings.llm.RAG_SEMANTIC_TOP_K, top_k),
                )
                semantic_items = await self._items_from_documents(semantic_docs, raw_lookup=raw_lookup)
                if not semantic_items:
                    return "", []
                reranked_items = await self._gte_rerank_items(effective_query, semantic_items, top_k)
                context = "\n\n".join([item.content for item in reranked_items])
                sources = self._build_sources(reranked_items, max_sources=top_k)
                return context, sources

            bm25_k = max(settings.llm.RAG_BM25_TOP_K, top_k)
            bm25_candidates = self._bm25_search(effective_query, candidates, bm25, bm25_k)
            if not bm25_candidates:
                semantic_docs = await self._semantic_search_global(
                    kb_id=kb_id,
                    query=effective_query,
                    top_k=max(settings.llm.RAG_SEMANTIC_TOP_K, top_k),
                )
                semantic_items = await self._items_from_documents(semantic_docs, raw_lookup=raw_lookup)
                if not semantic_items:
                    return "", []
                reranked_items = await self._gte_rerank_items(effective_query, semantic_items, top_k)
                context = "\n\n".join([item.content for item in reranked_items])
                sources = self._build_sources(reranked_items, max_sources=top_k)
                return context, sources

            semantic_global_k = max(settings.llm.RAG_SEMANTIC_TOP_K, top_k)
            semantic_docs = await self._semantic_search_global(
                kb_id=kb_id,
                query=effective_query,
                top_k=semantic_global_k,
            )

            bm25_items = self._items_from_bm25(bm25_candidates)
            semantic_items = await self._items_from_documents(semantic_docs, raw_lookup=raw_lookup)

            fused_items = self._rrf_fusion_items([bm25_items, semantic_items])
            if not fused_items:
                return "", []

            reranked_items = await self._gte_rerank_items(effective_query, fused_items, top_k)
            if not reranked_items:
                return "", []

            context = "\n\n".join([item.content for item in reranked_items])
            sources = self._build_sources(reranked_items, max_sources=top_k)
            return context, sources
        except Exception as e:
            logger.error(f"Search knowledge error: {e}")
            return "", []
