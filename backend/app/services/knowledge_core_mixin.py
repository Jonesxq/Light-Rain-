"""知识库核心初始化与基础依赖。"""

from typing import List, Tuple

from langchain_community.embeddings import DashScopeEmbeddings
from langchain_milvus import Milvus
from langchain_openai import ChatOpenAI

from app.core.config.settings import settings
from app.services.document_chunking import DocumentChunkingService
from app.utils.llm_factory import build_chat_llm
from app.services.knowledge_types import BM25Index, ChunkCandidate


class KnowledgeCoreMixin:
    """知识库核心配置与初始化能力。"""

    def _init_knowledge_components(self) -> None:
        """初始化嵌入模型、BM25 缓存与分块器。"""
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
        """获取用于分片摘要的 LLM 实例。"""
        return build_chat_llm(
            model=settings.llm.DEFAULT_MODEL,
            temperature=0.0,
            streaming=False,
        )

    def _get_vector_store(self, kb_id: int):
        """根据 KB 构建/获取向量库实例。"""
        collection_name = f"{settings.llm.MILVUS_COLLECTION_PREFIX}{kb_id}"

        return Milvus(
            embedding_function=self.embeddings,
            connection_args={"uri": settings.llm.MILVUS_URI},
            collection_name=collection_name,
            auto_id=True,
            drop_old=False,
        )
