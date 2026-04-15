"""知识库检索组件：负责 BM25、向量检索、融合重排与来源构建。"""

from __future__ import annotations

import asyncio
import json
import time
from http import HTTPStatus
from typing import List, Optional, Tuple

from dashscope import TextReRank
from sqlmodel import select

from app.core.config.settings import settings
from app.core.database import mysql_manager
from app.core.logger import logger_manager
from app.core.redis import redis_manager
from app.models.knowledge import DocumentChunk
from app.services.knowledge.types import ChunkCandidate, SearchItem
from app.services.shared.bm25 import BM25Index, _tokenize
from app.services.shared.query_rewrite import query_rewrite_service

logger = logger_manager.get_logger(__name__)


class KnowledgeRetrieval:
    """封装知识库查询主流程，输出检索上下文与来源信息。"""

    def __init__(self, service):
        """保存门面服务引用，复用跨组件能力。"""
        self.service = service

    def _invalidate_bm25_cache(self, kb_id: int) -> None:
        """清理内存与 Redis 的 BM25 相关缓存。"""
        self.service._bm25_cache.pop(kb_id, None)
        try:
            asyncio.create_task(
                redis_manager.delete_async(
                    f"kb:raw_chunks:{kb_id}",
                    f"kb:chunks:{kb_id}",
                )
            )
        except Exception:
            pass

    async def _get_bm25_index(self, kb_id: int) -> Tuple[List[ChunkCandidate], Optional[BM25Index]]:
        """获取知识库 BM25 索引，优先命中内存与 Redis 缓存。"""
        now = time.time()
        cached = self.service._bm25_cache.get(kb_id)
        if cached and (now - cached[0]) < settings.llm.RAG_BM25_CACHE_TTL:
            return cached[1], cached[2]

        redis_key = f"kb:raw_chunks:{kb_id}"
        try:
            cached_chunks = await redis_manager.get_async(redis_key)
            if cached_chunks:
                data = json.loads(cached_chunks)
                candidates = [
                    ChunkCandidate(
                        parent_id=str(item.get("parent_id") or "").strip(),
                        content=(item.get("content") or "").strip(),
                        structured_meta=item.get("structured_meta")
                        if isinstance(item.get("structured_meta"), dict)
                        else {},
                    )
                    for item in data
                    if item.get("parent_id") and item.get("content")
                ]
                if candidates:
                    bm25 = BM25Index([_tokenize(candidate.content) for candidate in candidates])
                    self.service._bm25_cache[kb_id] = (now, candidates, bm25)
                    return candidates, bm25
        except Exception:
            pass

        candidates = await self.service._load_raw_candidates_from_storage(kb_id)
        if not candidates:
            return [], None

        bm25 = BM25Index([_tokenize(candidate.content) for candidate in candidates])

        try:
            payload = json.dumps(
                [
                    {
                        "parent_id": candidate.parent_id,
                        "content": candidate.content,
                        "structured_meta": candidate.structured_meta,
                    }
                    for candidate in candidates
                ],
                ensure_ascii=False,
            )
            await redis_manager.set_async(redis_key, payload, ex=settings.llm.RAG_BM25_CACHE_TTL)
        except Exception:
            pass

        self.service._bm25_cache[kb_id] = (now, candidates, bm25)
        return candidates, bm25

    async def get_raw_chunk_candidates(self, kb_id: int) -> List[ChunkCandidate]:
        """对外提供原始分块候选列表。"""
        candidates, _ = await self.service._get_bm25_index(kb_id)
        return candidates

    def _build_raw_lookup(self, candidates: List[ChunkCandidate]) -> dict[str, ChunkCandidate]:
        """按 parent_id 构建候选分块快速索引。"""
        return {candidate.parent_id: candidate for candidate in candidates if candidate.parent_id}

    def _bm25_search(
        self,
        query: str,
        candidates: List[ChunkCandidate],
        bm25: BM25Index,
        top_k: int,
    ) -> List[ChunkCandidate]:
        """执行 BM25 检索并返回 top-k 候选分块。"""
        if not candidates or bm25 is None:
            return []

        scores = bm25.get_scores(_tokenize(query))
        if not scores:
            return []

        ranked_indices = sorted(range(len(scores)), key=lambda index: scores[index], reverse=True)
        results: List[ChunkCandidate] = []
        for index in ranked_indices:
            if len(results) >= top_k:
                break
            if scores[index] <= 0:
                continue
            results.append(candidates[index])

        if not results:
            results = [candidates[index] for index in ranked_indices[:top_k]]
        return results

    def _candidate_key(self, item: SearchItem) -> str:
        """为候选条目生成去重键，用于融合排序。"""
        meta = item.meta or {}
        parent_id = self.service._extract_parent_id_from_meta(meta)
        if parent_id:
            return parent_id

        source_meta = meta.get("source", {}) if isinstance(meta.get("source"), dict) else {}
        file_name = source_meta.get("file_name")
        loc_meta = meta.get("loc", {}) if isinstance(meta.get("loc"), dict) else {}
        if file_name and loc_meta:
            return f"{file_name}:{loc_meta}"
        return item.content

    def _items_from_bm25(self, candidates: List[ChunkCandidate]) -> List[SearchItem]:
        """将 BM25 候选转换为统一的 SearchItem 结构。"""
        return [SearchItem(content=candidate.content, meta=candidate.structured_meta) for candidate in candidates]

    def _rrf_fusion_items(self, ranked_lists: List[List[SearchItem]], rrf_k: int = 60) -> List[SearchItem]:
        """使用 RRF 融合多路排序结果，降低单路检索偏差。"""
        if not ranked_lists:
            return []

        scores: dict[str, float] = {}
        picked: dict[str, SearchItem] = {}
        for ranked in ranked_lists:
            for rank, item in enumerate(ranked, start=1):
                if not item or not item.content:
                    continue
                key = self.service._candidate_key(item)
                scores[key] = scores.get(key, 0.0) + 1.0 / (rrf_k + rank)
                if key not in picked or (not picked[key].meta and item.meta):
                    picked[key] = item

        if not scores:
            return []
        fused = sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
        return [picked[key] for key, _ in fused]

    async def _semantic_search_global(self, kb_id: int, query: str, top_k: int):
        """执行全局向量语义检索。"""
        if top_k <= 0:
            return []
        try:
            vector_db = self.service._get_vector_store(kb_id)
            return await vector_db.asimilarity_search(query, k=top_k)
        except Exception as exc:
            logger.warning(f"Global semantic search failed: {exc}")
            return []

    def _extract_parent_id_from_meta(self, meta: Optional[dict]) -> Optional[str]:
        """从结构化元数据中提取 parent_id。"""
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
        """根据向量主键批量回填数据库中的结构化元数据。"""
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
            chunk_meta = dict(chunk_meta) if isinstance(chunk_meta, dict) else {}
            if chunk.id is not None and chunk_meta.get("id") in (None, ""):
                chunk_meta["id"] = chunk.id
            if chunk_meta.get("index") is None:
                chunk_meta["index"] = chunk.chunk_index
            merged_meta["chunk"] = chunk_meta

            doc_meta = merged_meta.get("doc")
            doc_meta = dict(doc_meta) if isinstance(doc_meta, dict) else {}
            if doc_meta.get("doc_id") is None:
                doc_meta["doc_id"] = chunk.doc_id
            merged_meta["doc"] = doc_meta

            if merged_meta.get("parent_id") in (None, "") and chunk.parent_id:
                merged_meta["parent_id"] = chunk.parent_id
            meta_map[str(chunk.vector_id)] = merged_meta
        return meta_map

    async def _items_from_documents(
        self,
        docs,
        raw_lookup: Optional[dict[str, ChunkCandidate]] = None,
    ) -> List[SearchItem]:
        """将向量检索文档转换为 SearchItem，并尽量回填原始分块文本。"""
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

        meta_map = await self.service._load_structured_meta_by_vector_ids(vector_ids)
        raw_lookup = raw_lookup or {}
        enriched: List[SearchItem] = []
        for item, pk_str in zip(items, item_vector_ids):
            structured_meta = meta_map.get(pk_str) if pk_str else None
            merged_meta = structured_meta or item.meta or {}
            parent_id = self.service._extract_parent_id_from_meta(merged_meta)

            if parent_id and parent_id in raw_lookup:
                enriched.append(SearchItem(content=raw_lookup[parent_id].content, meta=merged_meta))
                continue

            if parent_id:
                logger.warning(f"Raw chunk not found for parent_id={parent_id}, fallback to summary text.")
            enriched.append(SearchItem(content=item.content, meta=merged_meta))

        return enriched

    async def _gte_rerank_items(self, query: str, items: List[SearchItem], top_k: int) -> List[SearchItem]:
        """调用重排模型按相关度筛选最终候选。"""
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
                ranked = [
                    result
                    for result in results
                    if getattr(result, "relevance_score", 0) >= settings.llm.RAG_RELEVANCE_THRESHOLD
                ]
                ranked.sort(key=lambda result: result.relevance_score, reverse=True)
                reranked = [items[result.index] for result in ranked if 0 <= result.index < len(items)]
                return reranked[:top_n]
            logger.warning(f"GTE rerank response error: {response.status_code if response else 'No response'}")
        except Exception as exc:
            logger.warning(f"GTE rerank failed with exception, fallback to fusion order: {exc}")

        return items[:top_n]

    def _build_sources(self, items: List[SearchItem], max_sources: Optional[int] = None) -> List[dict]:
        """从候选条目中提取可展示的来源信息并去重。"""
        if max_sources is None:
            max_sources = settings.llm.RAG_FINAL_TOP_K

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
            source = {key: value for key, value in source.items() if value not in (None, "", [], {})}
            if not source:
                continue

            dedupe_key = (
                source.get("chunk_id"),
                source.get("doc_id"),
                source.get("chunk_index"),
                source.get("file_name"),
                tuple(source.get("pages", []) or []),
                source.get("md_headings"),
            )
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            sources.append(source)

            if len(sources) >= max_sources:
                break

        return sources

    async def search_knowledge(
        self,
        kb_id: int,
        query: str,
        top_k: Optional[int] = None,
        rewritten_query: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> Tuple[str, List[dict]]:
        """执行完整知识库检索流程并返回上下文文本与来源列表。"""
        if top_k is None:
            top_k = settings.llm.RAG_FINAL_TOP_K

        try:
            if rewritten_query is None:
                rewritten_query = await query_rewrite_service.rewrite_query(query, user_id=user_id, kb_id=kb_id)
            effective_query = rewritten_query or query

            candidates, bm25 = await self.service._get_bm25_index(kb_id)
            raw_lookup = self.service._build_raw_lookup(candidates)
            if not candidates or bm25 is None:
                semantic_docs = await self.service._semantic_search_global(
                    kb_id=kb_id,
                    query=effective_query,
                    top_k=max(settings.llm.RAG_SEMANTIC_TOP_K, top_k),
                )
                semantic_items = await self.service._items_from_documents(semantic_docs, raw_lookup=raw_lookup)
                if not semantic_items:
                    return "", []
                reranked_items = await self.service._gte_rerank_items(effective_query, semantic_items, top_k)
                context = "\n\n".join(item.content for item in reranked_items)
                sources = self.service._build_sources(reranked_items, max_sources=top_k)
                return context, sources

            bm25_k = max(settings.llm.RAG_BM25_TOP_K, top_k)
            bm25_candidates = self.service._bm25_search(effective_query, candidates, bm25, bm25_k)
            if not bm25_candidates:
                semantic_docs = await self.service._semantic_search_global(
                    kb_id=kb_id,
                    query=effective_query,
                    top_k=max(settings.llm.RAG_SEMANTIC_TOP_K, top_k),
                )
                semantic_items = await self.service._items_from_documents(semantic_docs, raw_lookup=raw_lookup)
                if not semantic_items:
                    return "", []
                reranked_items = await self.service._gte_rerank_items(effective_query, semantic_items, top_k)
                context = "\n\n".join(item.content for item in reranked_items)
                sources = self.service._build_sources(reranked_items, max_sources=top_k)
                return context, sources

            semantic_docs = await self.service._semantic_search_global(
                kb_id=kb_id,
                query=effective_query,
                top_k=max(settings.llm.RAG_SEMANTIC_TOP_K, top_k),
            )
            bm25_items = self.service._items_from_bm25(bm25_candidates)
            semantic_items = await self.service._items_from_documents(semantic_docs, raw_lookup=raw_lookup)

            fused_items = self.service._rrf_fusion_items([bm25_items, semantic_items])
            if not fused_items:
                return "", []

            reranked_items = await self.service._gte_rerank_items(effective_query, fused_items, top_k)
            if not reranked_items:
                return "", []

            context = "\n\n".join(item.content for item in reranked_items)
            sources = self.service._build_sources(reranked_items, max_sources=top_k)
            return context, sources
        except Exception as exc:
            logger.error(f"Search knowledge error: {exc}")
            return "", []
