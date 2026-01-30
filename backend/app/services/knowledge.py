"""知识库服务：文档入库、检索、重排、删除等业务逻辑"""
import asyncio
import json
import math
import os
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from http import HTTPStatus
from typing import List, Optional, Tuple

try:
    import jieba
except Exception:
    # 没有安装 jieba 时，退化为简单字符切分
    jieba = None

from dashscope import TextReRank

# LangChain 相关导入
from langchain_milvus import Milvus
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_core.documents import Document as LangChainDocument
from app.services.document_chunking import DocumentChunkingService
from app.services.query_rewrite import query_rewrite_service

# 项目内部模块导入
from app.core.config.settings import settings
from app.core.database import mysql_manager
from app.core.redis import redis_manager
from app.crud.knowledge import kb_crud
from app.models.knowledge import Document, DocStatus, DocumentChunk
from sqlmodel import select
from app.core.logger import logger_manager

logger = logger_manager.get_logger(__name__)


# 轻量分词：优先使用 jieba，否则退化为中英文字符切分
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]")


def _tokenize(text: str) -> List[str]:
    """文本分词（BM25 使用）"""
    if not text:
        return []
    if jieba:
        # jieba 对中文更友好，兼容英文/数字
        return [t.strip().lower() for t in jieba.cut(text) if t.strip()]
    return [t.lower() for t in _TOKEN_PATTERN.findall(text)]


class BM25Index:
    """极简 BM25 实现（本地内存索引，适用于中小规模知识库）"""
    def __init__(self, tokenized_corpus: List[List[str]], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_freqs: List[Counter] = []
        self.doc_len: List[int] = []
        self.idf: dict[str, float] = {}
        self.avgdl: float = 0.0

        if not tokenized_corpus:
            return

        # 统计 DF + 文档长度
        df = defaultdict(int)
        total_len = 0
        for doc_tokens in tokenized_corpus:
            freqs = Counter(doc_tokens)
            self.doc_freqs.append(freqs)
            self.doc_len.append(len(doc_tokens))
            total_len += len(doc_tokens)
            for term in freqs:
                df[term] += 1

        doc_count = len(tokenized_corpus)
        self.avgdl = (total_len / doc_count) if doc_count else 0.0
        # 标准 BM25 idf
        self.idf = {
            term: math.log(1 + (doc_count - freq + 0.5) / (freq + 0.5))
            for term, freq in df.items()
        }

    def get_scores(self, query_tokens: List[str]) -> List[float]:
        """计算查询与所有文档的 BM25 分数"""
        if not self.doc_freqs or not query_tokens:
            return []

        scores = [0.0] * len(self.doc_freqs)
        avgdl = self.avgdl if self.avgdl > 0 else 1.0

        for term in query_tokens:
            idf = self.idf.get(term)
            if idf is None:
                continue
            for i, freqs in enumerate(self.doc_freqs):
                f = freqs.get(term, 0)
                if not f:
                    continue
                # BM25 打分
                denom = f + self.k1 * (1 - self.b + self.b * (self.doc_len[i] / avgdl))
                scores[i] += idf * (f * (self.k1 + 1)) / (denom + 1e-9)

        return scores


@dataclass(frozen=True)
class ChunkCandidate:
    """BM25 阶段候选切片"""
    chunk_id: int
    vector_id: str
    content: str
    structured_meta: Optional[dict] = None


@dataclass(frozen=True)
class SearchItem:
    """统一的检索结果结构（用于重排与返回来源）"""
    content: str
    meta: Optional[dict] = None


class KnowledgeService:
    """知识库业务入口：入库、检索与删除"""
    def __init__(self):
        # 1) 初始化嵌入模型
        self.embeddings = DashScopeEmbeddings(
            model=settings.llm.EMBEDDING_MODEL,
            dashscope_api_key=settings.llm.QWEN_API_KEY
        )
        # 2) 本地 BM25 缓存：KB -> (时间戳, 候选列表, BM25 索引)
        self._bm25_cache: dict[int, Tuple[float, List[ChunkCandidate], BM25Index]] = {}
        # 3) 文档分块服务（按类型配置 chunk）
        self.chunker = DocumentChunkingService(
            default_chunk_size=settings.llm.RAG_CHUNK_SIZE_DEFAULT,
            default_chunk_overlap=settings.llm.RAG_CHUNK_OVERLAP_DEFAULT,
            per_type={
                ".pdf": (settings.llm.RAG_CHUNK_SIZE_PDF, settings.llm.RAG_CHUNK_OVERLAP_PDF),
                ".docx": (settings.llm.RAG_CHUNK_SIZE_DOCX, settings.llm.RAG_CHUNK_OVERLAP_DOCX),
                ".md": (settings.llm.RAG_CHUNK_SIZE_MD, settings.llm.RAG_CHUNK_OVERLAP_MD),
                ".txt": (settings.llm.RAG_CHUNK_SIZE_TXT, settings.llm.RAG_CHUNK_OVERLAP_TXT),
                ".pptx": (settings.llm.RAG_CHUNK_SIZE_PPTX, settings.llm.RAG_CHUNK_OVERLAP_PPTX),
                ".ppt": (settings.llm.RAG_CHUNK_SIZE_PPTX, settings.llm.RAG_CHUNK_OVERLAP_PPTX),
            },
        )

    def _get_vector_store(self, kb_id: int):
        """为每个知识库获取或创建一个 Milvus 实例"""
        collection_name = f"{settings.llm.MILVUS_COLLECTION_PREFIX}{kb_id}"

        return Milvus(
            embedding_function=self.embeddings,
            connection_args={"uri": settings.llm.MILVUS_URI},
            collection_name=collection_name,
            auto_id=True,
            drop_old=False
        )

    def _invalidate_bm25_cache(self, kb_id: int) -> None:
        """文档更新后失效缓存，避免使用旧索引"""
        self._bm25_cache.pop(kb_id, None)
        # 同时失效 Redis 缓存（跨进程一致）
        try:
            asyncio.create_task(redis_manager.delete_async(f"kb:chunks:{kb_id}"))
        except Exception:
            pass

    async def _get_bm25_index(self, kb_id: int) -> Tuple[List[ChunkCandidate], Optional[BM25Index]]:
        """按知识库构建/读取 BM25 索引（带简单 TTL 缓存）"""
        now = time.time()
        cached = self._bm25_cache.get(kb_id)
        if cached and (now - cached[0]) < settings.llm.RAG_BM25_CACHE_TTL:
            return cached[1], cached[2]

        # 先尝试从 Redis 读取切片内容，降低 MySQL 压力
        redis_key = f"kb:chunks:{kb_id}"
        try:
            cached_chunks = await redis_manager.get_async(redis_key)
            if cached_chunks:
                data = json.loads(cached_chunks)
                candidates = [
                    ChunkCandidate(
                        chunk_id=item.get("chunk_id", 0),
                        vector_id=item.get("vector_id", ""),
                        content=item.get("content", ""),
                        structured_meta=item.get("structured_meta")
                    )
                    for item in data
                    if item.get("content")
                ]
                if candidates:
                    tokenized = [_tokenize(c.content) for c in candidates]
                    bm25 = BM25Index(tokenized)
                    self._bm25_cache[kb_id] = (now, candidates, bm25)
                    return candidates, bm25
        except Exception:
            pass

        # Redis 未命中则回源 MySQL
        async with mysql_manager.async_session_maker() as db:
            chunks = await kb_crud.get_kb_chunks(db, kb_id)

        if not chunks:
            return [], None

        # 只保留检索需要的字段
        candidates = [
            ChunkCandidate(
                chunk_id=chunk.id or 0,
                vector_id=chunk.vector_id,
                content=chunk.content,
                structured_meta=chunk.structured_meta
            )
            for chunk in chunks
        ]
        tokenized = [_tokenize(c.content) for c in candidates]
        bm25 = BM25Index(tokenized)

        # 写入 Redis，减少后续 MySQL 读取
        try:
            payload = json.dumps(
                [
                    {
                        "chunk_id": c.chunk_id,
                        "vector_id": c.vector_id,
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

    def _bm25_search(
        self,
        query: str,
        candidates: List[ChunkCandidate],
        bm25: BM25Index,
        top_k: int
    ) -> List[ChunkCandidate]:
        """BM25 召回候选"""
        if not candidates or bm25 is None:
            return []

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

    def _build_pk_expr(self, vector_ids: List[int]) -> Optional[str]:
        """Milvus 主键过滤表达式"""
        if not vector_ids:
            return None
        ids = ",".join(str(v_id) for v_id in vector_ids)
        return f"pk in [{ids}]"

    async def _semantic_search_within_candidates(
        self,
        kb_id: int,
        query: str,
        candidates: List[ChunkCandidate],
        top_k: int
    ):
        """在 BM25 候选集内做向量检索"""
        if not candidates or top_k <= 0:
            return []

        vector_ids: List[int] = []
        for candidate in candidates:
            try:
                vector_ids.append(int(candidate.vector_id))
            except (TypeError, ValueError):
                continue

        expr = self._build_pk_expr(vector_ids)
        if not expr:
            return []

        vector_db = self._get_vector_store(kb_id)
        # embed_query 是同步方法，放到线程池避免阻塞事件循环
        query_embedding = await asyncio.to_thread(self.embeddings.embed_query, query)
        return await vector_db.asimilarity_search_by_vector(
            query_embedding,
            k=min(top_k, len(vector_ids)),
            expr=expr
        )

    async def _semantic_search_global(self, kb_id: int, query: str, top_k: int):
        """全库语义检索（不受 BM25 候选限制）"""
        if top_k <= 0:
            return []
        try:
            vector_db = self._get_vector_store(kb_id)
            return await vector_db.asimilarity_search(query, k=top_k)
        except Exception as e:
            logger.warning(f"Global semantic search failed: {e}")
            return []

    def _extract_texts(self, items) -> List[str]:
        """统一提取不同对象的文本内容"""
        texts: List[str] = []
        for item in items:
            content = getattr(item, "page_content", None) or getattr(item, "content", None)
            if content:
                texts.append(content)
        return texts

    def _candidate_key(self, item: SearchItem) -> str:
        """生成候选的唯一键（用于去重与融合）"""
        meta = item.meta or {}
        doc_meta = meta.get("doc", {}) if isinstance(meta.get("doc"), dict) else {}
        chunk_meta = meta.get("chunk", {}) if isinstance(meta.get("chunk"), dict) else {}

        doc_id = doc_meta.get("doc_id")
        chunk_index = chunk_meta.get("index")
        if doc_id is not None and chunk_index is not None:
            return f"{doc_id}:{chunk_index}"

        source_meta = meta.get("source", {}) if isinstance(meta.get("source"), dict) else {}
        file_name = source_meta.get("file_name")
        loc_meta = meta.get("loc", {}) if isinstance(meta.get("loc"), dict) else {}
        if file_name and loc_meta:
            return f"{file_name}:{loc_meta}"

        # 兜底：使用内容本身
        return item.content

    def _items_from_bm25(self, candidates: List[ChunkCandidate]) -> List[SearchItem]:
        """将 BM25 候选转为统一 SearchItem 结构"""
        return [SearchItem(content=c.content, meta=c.structured_meta) for c in candidates]

    async def _load_structured_meta_by_vector_ids(self, vector_ids: List[str]) -> dict[str, dict]:
        """批量加载向量 ID 对应的结构化元数据（来自 MySQL）"""
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

    async def _items_from_documents(self, docs) -> List[SearchItem]:
        """将向量检索结果转为统一 SearchItem，并补齐结构化元数据"""
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

        # 用向量 ID 回查结构化元数据
        meta_map = await self._load_structured_meta_by_vector_ids(vector_ids)
        enriched: List[SearchItem] = []
        for item, pk_str in zip(items, item_vector_ids):
            structured_meta = meta_map.get(pk_str) if pk_str else None
            enriched.append(SearchItem(content=item.content, meta=structured_meta or item.meta))

        return enriched

    def _rrf_fusion_items(self, ranked_lists: List[List[SearchItem]], rrf_k: int = 60) -> List[SearchItem]:
        """使用 RRF 融合多个有序列表（保留元数据）"""
        if not ranked_lists:
            return []

        scores = defaultdict(float)
        picked: dict[str, SearchItem] = {}

        for ranked in ranked_lists:
            for rank, item in enumerate(ranked, start=1):
                if not item or not item.content:
                    continue
                key = self._candidate_key(item)
                scores[key] += 1.0 / (rrf_k + rank)
                # 优先保留包含元数据的 item
                if key not in picked or (not picked[key].meta and item.meta):
                    picked[key] = item

        if not scores:
            return []

        # 按分数降序排序
        fused = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [picked[key] for key, _ in fused]

    async def _gte_rerank_items(self, query: str, items: List[SearchItem], top_k: int) -> List[SearchItem]:
        """调用 DashScope gte-rerank-v2 进行重排（保留元数据）"""
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
            # 重排失败时不影响主流程
            logger.warning(f"GTE rerank failed, fallback to fusion order: {e}")

        return items[:top_n]

    def _build_sources(self, items: List[SearchItem], max_sources: int = 5) -> List[dict]:
        """从检索结果中提取结构化来源信息"""
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
                "chunk_index": chunk_meta.get("index"),
            }

            # 过滤空值
            source = {k: v for k, v in source.items() if v not in (None, "", [], {})}
            if not source:
                continue

            key = (
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

    async def ingest_document(self, doc_id: int):
        """后台任务：解析文档 -> 分块 -> 向量化 -> 写入 Milvus 与 MySQL"""
        async with mysql_manager.async_session_maker() as db:
            # 获取文档记录
            doc = await db.get(Document, doc_id)
            if not doc:
                logger.error(f"Ingest Error: Document {doc_id} not found.")
                return

            try:
                logger.info(f"Starting to process document: {doc.file_name}")
                # 文件不存在时直接标记失败
                if not doc.file_path or not os.path.exists(doc.file_path):
                    raise FileNotFoundError(f"Document file not found: {doc.file_path}")

                # 1) 加载并切片（注入结构化文档元数据）
                base_meta = {
                    "doc": {
                        "doc_id": doc.id,
                        "kb_id": doc.kb_id,
                        "file_name": doc.file_name,
                        "file_type": doc.file_type,
                        "file_size": doc.file_size,
                    }
                }
                chunks = self.chunker.load_and_split(
                    doc.file_path,
                    doc.file_type,
                    base_meta=base_meta
                )
                if not chunks:
                    raise ValueError("Document chunking produced empty result.")

                # 2) 生成写入 Milvus 的最小元数据（避免字段类型冲突）
                # 说明：Milvus 集合已有 source 字段为 VARCHAR，不能写入 dict
                milvus_docs = []
                for chunk in chunks:
                    milvus_docs.append(
                        LangChainDocument(
                            page_content=chunk.page_content,
                            metadata={
                                # 仅保留字符串字段，兼容已有 schema（避免 dict 写入 VARCHAR）
                                "source": str(doc.file_name or doc.file_path or "")
                            },
                        ),
                    )

                # 3) 写入 Milvus（内部自动 embedding）
                vector_db = self._get_vector_store(doc.kb_id)
                # Milvus 写入是同步接口，放入线程池避免阻塞事件循环
                ids = await asyncio.to_thread(vector_db.add_documents, milvus_docs)

                # 4) 回填切片记录到 MySQL
                for idx, (chunk, v_id) in enumerate(zip(chunks, ids)):
                    # 统一补充 chunk_index（以库中序号为准）
                    if isinstance(chunk.metadata.get("chunk"), dict):
                        chunk.metadata["chunk"]["index"] = idx
                    await kb_crud.create_chunk(
                        db,
                        doc_id=doc.id,
                        content=chunk.page_content,
                        vector_id=str(v_id),
                        chunk_index=idx,
                        structured_meta=chunk.metadata
                    )

                # 5) 更新文档状态
                await kb_crud.update_document_status(
                    db,
                    doc_id=doc.id,
                    status=DocStatus.COMPLETED,
                    chunk_count=len(chunks)
                )
                self._invalidate_bm25_cache(doc.kb_id)
                logger.info(f"Successfully processed: {doc.file_name}, created {len(chunks)} chunks.")

            except Exception as e:
                logger.error(f"Failed to ingest document {doc.id}: {str(e)}")
                # 记录失败状态到数据库
                await kb_crud.update_document_status(
                    db,
                    doc_id=doc.id,
                    status=DocStatus.FAILED,
                    error_msg=str(e)
                )

    async def reindex_document(self, doc_id: int) -> bool:
        """重建文档索引：清空旧切片 -> 重新解析入库"""
        async with mysql_manager.async_session_maker() as db:
            doc = await db.get(Document, doc_id)
            if not doc:
                return False

            # 1) 删除向量数据
            chunks = await kb_crud.get_document_chunks(db, doc_id)
            vector_ids = [c.vector_id for c in chunks if c.vector_id]
            if vector_ids:
                try:
                    vector_db = self._get_vector_store(doc.kb_id)
                    await asyncio.to_thread(vector_db.delete, ids=vector_ids)
                except Exception as e:
                    logger.warning(f"Milvus delete failed for doc {doc_id}: {e}")

            # 2) 删除 DB 中旧切片
            await kb_crud.delete_document_chunks(db, doc_id)

            # 3) 重置文档状态
            await kb_crud.update_document_status(
                db,
                doc_id=doc_id,
                status=DocStatus.PROCESSING,
                chunk_count=0,
                error_msg=""
            )

        # 4) 重新解析入库（会写入新的结构化元数据）
        await self.ingest_document(doc_id)
        return True
    async def search_knowledge(
        self,
        kb_id: int,
        query: str,
        top_k: int = 3,
        rewritten_query: Optional[str] = None
    ) -> Tuple[str, List[dict]]:
        """RAG 检索：BM25 + 语义召回 -> RRF 融合 -> 重排"""
        try:
            # 0) 查询改写：提升检索质量（失败则回退原问题）
            if rewritten_query is None:
                rewritten_query = await query_rewrite_service.rewrite_query(query)
            effective_query = rewritten_query or query

            candidates, bm25 = await self._get_bm25_index(kb_id)
            if not candidates or bm25 is None:
                # BM25 为空时，直接走全库语义检索兜底
                semantic_docs = await self._semantic_search_global(
                    kb_id=kb_id,
                    query=effective_query,
                    top_k=max(settings.llm.RAG_SEMANTIC_TOP_K, top_k)
                )
                semantic_items = await self._items_from_documents(semantic_docs)
                if not semantic_items:
                    return "", []
                reranked_items = await self._gte_rerank_items(effective_query, semantic_items, top_k)
                context = "\n\n".join([item.content for item in reranked_items])
                sources = self._build_sources(reranked_items, max_sources=top_k)
                return context, sources

            # 1) BM25 召回
            bm25_k = max(settings.llm.RAG_BM25_TOP_K, top_k)
            bm25_candidates = self._bm25_search(effective_query, candidates, bm25, bm25_k)
            if not bm25_candidates:
                # BM25 没召回，回退全库语义检索
                semantic_docs = await self._semantic_search_global(
                    kb_id=kb_id,
                    query=effective_query,
                    top_k=max(settings.llm.RAG_SEMANTIC_TOP_K, top_k)
                )
                semantic_items = await self._items_from_documents(semantic_docs)
                if not semantic_items:
                    return "", []
                reranked_items = await self._gte_rerank_items(effective_query, semantic_items, top_k)
                context = "\n\n".join([item.content for item in reranked_items])
                sources = self._build_sources(reranked_items, max_sources=top_k)
                return context, sources

            # 2) 全库语义检索（扩大召回，补充 BM25 覆盖不足的情况）
            semantic_global_k = max(settings.llm.RAG_SEMANTIC_TOP_K, top_k)
            semantic_docs = await self._semantic_search_global(
                kb_id=kb_id,
                query=effective_query,
                top_k=semantic_global_k
            )

            # 3) 取结果列表（BM25 与语义各自保序）
            bm25_items = self._items_from_bm25(bm25_candidates)
            semantic_items = await self._items_from_documents(semantic_docs)

            # 4) RRF 融合排序（混合检索优化）
            fused_items = self._rrf_fusion_items([bm25_items, semantic_items])
            if not fused_items:
                return "", []

            # 5) gte-rerank-v2 重排
            reranked_items = await self._gte_rerank_items(effective_query, fused_items, top_k)
            if not reranked_items:
                return "", []

            context = "\n\n".join([item.content for item in reranked_items])
            sources = self._build_sources(reranked_items, max_sources=top_k)
            return context, sources
        except Exception as e:
            logger.error(f"Search knowledge error: {e}")
            return "", []

    async def delete_document(self, kb_id: int, doc_id: int) -> bool:
        """删除文档：清理 Milvus 向量 + 本地文件 + DB 记录"""
        async with mysql_manager.async_session_maker() as db:
            doc = await kb_crud.get_document(db, doc_id)
            if not doc or doc.kb_id != kb_id:
                return False

            # 1) 删除向量数据
            chunks = await kb_crud.get_document_chunks(db, doc_id)
            vector_ids = [c.vector_id for c in chunks if c.vector_id]
            if vector_ids:
                try:
                    vector_db = self._get_vector_store(kb_id)
                    await asyncio.to_thread(vector_db.delete, ids=vector_ids)
                except Exception as e:
                    logger.warning(f"Milvus delete failed for doc {doc_id}: {e}")

            # 2) 删除本地文件
            if doc.file_path and os.path.exists(doc.file_path):
                try:
                    os.remove(doc.file_path)
                except Exception as e:
                    logger.warning(f"Remove file failed for doc {doc_id}: {e}")

            # 3) 删除数据库记录
            success = await kb_crud.delete_document(db, doc_id)
            if success:
                self._invalidate_bm25_cache(kb_id)
            return success


# 实例化全局服务对象
kb_service = KnowledgeService()
