"""知识库服务：文档入库、检索、重排、删除等业务逻辑。"""
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
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_core.documents import Document as LangChainDocument
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_milvus import Milvus
from langchain_openai import ChatOpenAI
from sqlmodel import select

# 项目内部模块导入
from app.constant.prompts import CHUNK_SUMMARY_SYSTEM_PROMPT
from app.core.config.settings import settings
from app.core.database import mysql_manager
from app.core.logger import logger_manager
from app.core.redis import redis_manager
from app.crud.knowledge import kb_crud
from app.models.knowledge import DocStatus, Document, DocumentChunk
from app.services.document_chunking import DocumentChunkingService
from app.services.query_rewrite import query_rewrite_service

logger = logger_manager.get_logger(__name__)


# 轻量分词：优先使用 jieba，否则退化为中英文字符切分
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]")
_SIDECAR_SUFFIX = ".chunks.jsonl"


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


@dataclass
class ChunkCandidate:
    """BM25 阶段候选切片（原文 chunk）"""
    parent_id: str
    content: str
    structured_meta: Optional[dict] = None


@dataclass
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

    def _get_summary_llm(self) -> ChatOpenAI:
        """获取摘要模型（复用默认模型）"""
        return ChatOpenAI(
            model=settings.llm.DEFAULT_MODEL,
            openai_api_key=settings.llm.QWEN_API_KEY,
            openai_api_base=settings.llm.QWEN_BASE_URL,
            temperature=0.0,
            streaming=False,
        )

    def _get_vector_store(self, kb_id: int):
        """为每个知识库获取或创建一个 Milvus 实例"""
        collection_name = f"{settings.llm.MILVUS_COLLECTION_PREFIX}{kb_id}"

        return Milvus(
            embedding_function=self.embeddings,
            connection_args={"uri": settings.llm.MILVUS_URI},
            collection_name=collection_name,
            auto_id=True,
            drop_old=False,
        )

    def _normalize_milvus_delete_ids(self, vector_ids: List[str]) -> Tuple[List[int], int]:
        """
        归一化 Milvus 删除 ID：
        - 将数据库中保存的 vector_id（字符串）转换为 Int64；
        - 过滤空值/非数字值，避免 `pk in ['...']` 类型错误。
        """
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

    def _get_sidecar_path(self, file_path: str) -> str:
        """原文 chunk sidecar 文件路径"""
        return f"{file_path}{_SIDECAR_SUFFIX}" if file_path else ""

    def _remove_sidecar_file(self, file_path: str) -> None:
        """删除 sidecar 文件（忽略不存在场景）"""
        sidecar_path = self._get_sidecar_path(file_path)
        if not sidecar_path:
            return
        try:
            if os.path.exists(sidecar_path):
                os.remove(sidecar_path)
        except Exception as e:
            logger.warning(f"Remove sidecar failed for {sidecar_path}: {e}")

    def _write_sidecar_atomic(self, sidecar_path: str, rows: List[dict]) -> None:
        """原子写入 sidecar，避免并发或异常导致半文件"""
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
        """读取 sidecar 并转换为 BM25 候选列表（容错坏行）"""
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

    def get_raw_chunk_preview(self, doc: Document, chunk_index: int) -> Optional[dict]:
        """按 doc + chunk_index 读取原文 chunk（用于预览）"""
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
        """从已完成文档的 sidecar 聚合原文 chunk 候选"""
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

    async def _summarize_chunk(self, llm: ChatOpenAI, raw_text: str, max_chars: int) -> str:
        """为单个原文 chunk 生成摘要；失败时回退原文"""
        if not raw_text:
            return ""
        try:
            messages = [
                SystemMessage(content=CHUNK_SUMMARY_SYSTEM_PROMPT.format(max_chars=max_chars)),
                HumanMessage(content=raw_text),
            ]
            response = await llm.ainvoke(messages)
            summary = (getattr(response, "content", "") or "").strip()
            if not summary:
                return raw_text
            if len(summary) > max_chars:
                return summary[:max_chars]
            return summary
        except Exception as e:
            logger.warning(f"Chunk summary failed, fallback to raw chunk: {e}")
            return raw_text

    async def _summarize_chunks(self, raw_chunks: List[str]) -> List[str]:
        """并发生成摘要（受配置限制）"""
        if not raw_chunks:
            return []

        llm = self._get_summary_llm()
        max_chars = max(50, int(settings.llm.RAG_SUMMARY_MAX_CHARS))
        concurrency = max(1, int(settings.llm.RAG_SUMMARY_CONCURRENCY))
        semaphore = asyncio.Semaphore(concurrency)
        summaries = [""] * len(raw_chunks)

        async def worker(idx: int, text: str) -> None:
            async with semaphore:
                summaries[idx] = await self._summarize_chunk(llm, text, max_chars)

        await asyncio.gather(*(worker(i, text) for i, text in enumerate(raw_chunks)))
        return summaries

    def _invalidate_bm25_cache(self, kb_id: int) -> None:
        """文档更新后失效缓存，避免使用旧索引"""
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
        """按知识库构建/读取 BM25 索引（基于原文 sidecar）"""
        now = time.time()
        cached = self._bm25_cache.get(kb_id)
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

        candidates = await self._load_raw_candidates_from_storage(kb_id)
        if not candidates:
            return [], None

        tokenized = [_tokenize(c.content) for c in candidates]
        bm25 = BM25Index(tokenized)

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
        """对外暴露原文 chunk 候选（供评估等流程复用）"""
        candidates, _ = await self._get_bm25_index(kb_id)
        return candidates

    def _build_raw_lookup(self, candidates: List[ChunkCandidate]) -> dict[str, ChunkCandidate]:
        """构建 parent_id -> 原文 chunk 映射"""
        return {c.parent_id: c for c in candidates if c.parent_id}

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

    async def _semantic_search_global(self, kb_id: int, query: str, top_k: int):
        """全库语义检索（在摘要向量上检索）"""
        if top_k <= 0:
            return []
        try:
            vector_db = self._get_vector_store(kb_id)
            return await vector_db.asimilarity_search(query, k=top_k)
        except Exception as e:
            logger.warning(f"Global semantic search failed: {e}")
            return []

    def _extract_parent_id_from_meta(self, meta: Optional[dict]) -> Optional[str]:
        """从 structured_meta 中提取 parent_id"""
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

    def _candidate_key(self, item: SearchItem) -> str:
        """生成候选的唯一键（用于去重与融合）"""
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

    async def _items_from_documents(
        self,
        docs,
        raw_lookup: Optional[dict[str, ChunkCandidate]] = None,
    ) -> List[SearchItem]:
        """将摘要向量检索结果映射为原文 SearchItem"""
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
        """后台任务：解析文档 -> 生成摘要 -> 摘要向量化 -> 写入 Milvus 与 MySQL"""
        async with mysql_manager.async_session_maker() as db:
            doc = await db.get(Document, doc_id)
            if not doc:
                logger.error(f"Ingest Error: Document {doc_id} not found.")
                return

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
                chunks = self.chunker.load_and_split(
                    doc.file_path,
                    doc.file_type,
                    base_meta=base_meta,
                )
                if not chunks:
                    raise ValueError("Document chunking produced empty result.")

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

                raw_contents = [row["raw_content"] for row in prepared_rows]
                summaries = await self._summarize_chunks(raw_contents)
                if len(summaries) != len(prepared_rows):
                    raise ValueError("Chunk summary count mismatch.")

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
                logger.error(f"Failed to ingest document {doc.id}: {str(e)}")
                self._remove_sidecar_file(doc.file_path)
                await kb_crud.update_document_status(
                    db,
                    doc_id=doc.id,
                    status=DocStatus.FAILED,
                    error_msg=str(e),
                )

    async def reindex_document(self, doc_id: int) -> bool:
        """重建文档索引：清空旧切片与 sidecar -> 重新解析入库"""
        async with mysql_manager.async_session_maker() as db:
            doc = await db.get(Document, doc_id)
            if not doc:
                return False

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

    async def search_knowledge(
        self,
        kb_id: int,
        query: str,
        top_k: int = 3,
        rewritten_query: Optional[str] = None,
    ) -> Tuple[str, List[dict]]:
        """RAG 检索：BM25(原文) + 语义召回(摘要向量) -> RRF 融合 -> 重排"""
        try:
            if rewritten_query is None:
                rewritten_query = await query_rewrite_service.rewrite_query(query)
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

    async def delete_document(self, kb_id: int, doc_id: int) -> bool:
        """删除文档：清理 Milvus 向量 + sidecar + 原文件 + DB 记录"""
        async with mysql_manager.async_session_maker() as db:
            doc = await kb_crud.get_document(db, doc_id)
            if not doc or doc.kb_id != kb_id:
                return False

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
        """删除知识库：先清理向量与本地文件，再删除 KB 记录"""
        async with mysql_manager.async_session_maker() as db:
            kb = await kb_crud.get_kb(db, kb_id)
            if not kb:
                return False

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


# 实例化全局服务对象
kb_service = KnowledgeService()
