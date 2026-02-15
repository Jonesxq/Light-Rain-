"""知识库 BM25 缓存与 RRF 融合逻辑。"""

import asyncio
import json
import time
from typing import List, Optional, Tuple

from app.core.config.settings import settings
from app.core.redis import redis_manager
from app.services.knowledge_types import BM25Index, ChunkCandidate, SearchItem, _tokenize


class KnowledgeBM25Mixin:
    """BM25 缓存与候选融合能力。"""

    def _invalidate_bm25_cache(self, kb_id: int) -> None:
        """清理 BM25 本地缓存并尝试清空 redis 缓存。"""
        self._bm25_cache.pop(kb_id, None)
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
        """获取/构建 BM25 索引（优先缓存，其次 redis，最后回退本地加载）。"""
        now = time.time()
        cached = self._bm25_cache.get(kb_id)
        if cached and (now - cached[0]) < settings.llm.RAG_BM25_CACHE_TTL:
            return cached[1], cached[2]

        redis_key = f"kb:raw_chunks:{kb_id}"
        # 先尝试从 redis 读取预计算候选
        try:
            cached_chunks = await redis_manager.get_async(redis_key)
            if cached_chunks:
                data = json.loads(cached_chunks)
                candidates = [
                    ChunkCandidate(
                        parent_id=str(item.get("parent_id") or "").strip(),
                        content=(item.get("content") or "").strip(),
                        structured_meta=item.get("structured_meta") if isinstance(item.get("structured_meta"), dict) else {},
                    )
                    for item in data
                    if item.get("parent_id") and item.get("content")
                ]
                if candidates:
                    tokenized = [_tokenize(c.content) for c in candidates]
                    bm25 = BM25Index(tokenized)
                    self._bm25_cache[kb_id] = (now, candidates, bm25)
                    return candidates, bm25
        except Exception:
            pass

        # 兜底：从存储加载原始分片并构建索引
        candidates = await self._load_raw_candidates_from_storage(kb_id)
        if not candidates:
            return [], None

        tokenized = [_tokenize(c.content) for c in candidates]
        bm25 = BM25Index(tokenized)

        # 写回 redis，减少下次冷启动成本
        try:
            payload = json.dumps(
                [
                    {
                        "parent_id": c.parent_id,
                        "content": c.content,
                        "structured_meta": c.structured_meta,
                    }
                    for c in candidates
                ],
                ensure_ascii=False,
            )
            await redis_manager.set_async(redis_key, payload, ex=settings.llm.RAG_BM25_CACHE_TTL)
        except Exception:
            pass

        self._bm25_cache[kb_id] = (now, candidates, bm25)
        return candidates, bm25

    async def get_raw_chunk_candidates(self, kb_id: int) -> List[ChunkCandidate]:
        """返回 raw chunk 候选列表（用于评估或调试）。"""
        candidates, _ = await self._get_bm25_index(kb_id)
        return candidates

    def _build_raw_lookup(self, candidates: List[ChunkCandidate]) -> dict[str, ChunkCandidate]:
        """构建 parent_id -> 原始分片 的映射。"""
        return {c.parent_id: c for c in candidates if c.parent_id}

    def _bm25_search(
        self,
        query: str,
        candidates: List[ChunkCandidate],
        bm25: BM25Index,
        top_k: int
    ) -> List[ChunkCandidate]:
        """使用 BM25 在候选中检索并返回 top_k。"""
        if not candidates or bm25 is None:
            return []

        # BM25 打分并按分数排序
        scores = bm25.get_scores(_tokenize(query))
        if not scores:
            return []

        ranked_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        results: List[ChunkCandidate] = []
        for idx in ranked_indices:
            if len(results) >= top_k:
                break
            if scores[idx] <= 0:
                continue
            results.append(candidates[idx])

        if not results:
            # 全部为 0 时退化为 top_k 截断
            results = [candidates[i] for i in ranked_indices[:top_k]]

        return results

    def _candidate_key(self, item: SearchItem) -> str:
        """生成去重 key（优先 parent_id，其次来源信息，最后内容本身）。"""
        meta = item.meta or {}
        parent_id = self._extract_parent_id_from_meta(meta)
        if parent_id:
            return parent_id

        source_meta = meta.get("source", {}) if isinstance(meta.get("source"), dict) else {}
        file_name = source_meta.get("file_name")
        loc_meta = meta.get("loc", {}) if isinstance(meta.get("loc"), dict) else {}
        if file_name and loc_meta:
            return f"{file_name}:{loc_meta}"

        # 兜底：使用内容本身
        return item.content

    def _items_from_bm25(self, candidates: List[ChunkCandidate]) -> List[SearchItem]:
        """将 BM25 候选转换为 SearchItem 列表。"""
        return [SearchItem(content=c.content, meta=c.structured_meta) for c in candidates]

    def _rrf_fusion_items(self, ranked_lists: List[List[SearchItem]], rrf_k: int = 60) -> List[SearchItem]:
        """RRF 融合：将多路排序结果按排名倒数加权融合。"""
        if not ranked_lists:
            return []

        # 使用倒数融合分数，兼顾多路结果
        scores = {}
        picked: dict[str, SearchItem] = {}

        for ranked in ranked_lists:
            for rank, item in enumerate(ranked, start=1):
                if not item or not item.content:
                    continue
                key = self._candidate_key(item)
                scores[key] = scores.get(key, 0.0) + 1.0 / (rrf_k + rank)
                # 优先保留包含元数据的 item
                if key not in picked or (not picked[key].meta and item.meta):
                    picked[key] = item

        if not scores:
            return []

        # 按分数降序排序
        fused = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [picked[key] for key, _ in fused]
