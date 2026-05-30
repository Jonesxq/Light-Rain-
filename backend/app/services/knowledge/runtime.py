"""知识库运行时组件：负责模型依赖初始化与 Milvus 连接桥接。"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from langchain_community.embeddings import DashScopeEmbeddings
from langchain_milvus import Milvus
from langchain_openai import ChatOpenAI
from pymilvus import MilvusClient, connections as milvus_connections
from pymilvus.exceptions import ConnectionNotExistException

from app.core.config.settings import settings
from app.core.logger import logger_manager
from app.services.knowledge.types import ChunkCandidate
from app.services.shared.bm25 import BM25Index
from app.services.shared.document_chunking import DocumentChunkingService
from app.utils.llm_factory import build_chat_llm

logger = logger_manager.get_logger(__name__)


class KnowledgeRuntime:
    """管理知识库长生命周期依赖，如嵌入模型、分块器与向量库连接。"""

    def __init__(self, service):
        """保存门面服务引用，供运行时组件回调共享状态。"""
        self.service = service

    def init_components(self) -> None:
        """初始化知识库检索与入库所需的核心依赖。"""
        self.service.embeddings = DashScopeEmbeddings(
            model=settings.llm.EMBEDDING_MODEL,
            dashscope_api_key=settings.llm.QWEN_API_KEY,
        )
        self.service._bm25_cache: dict[int, Tuple[float, List[ChunkCandidate], BM25Index]] = {}
        self.service.chunker = DocumentChunkingService(
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
        """构建用于分块摘要的低温度非流式模型实例。"""
        return build_chat_llm(
            model=settings.llm.DEFAULT_MODEL,
            temperature=0.0,
            streaming=False,
        )

    def _build_milvus_connection_args(self) -> Dict[str, Any]:
        """按配置组装 Milvus 连接参数。"""
        connection_args: Dict[str, Any] = {"uri": settings.llm.MILVUS_URI}
        if settings.llm.MILVUS_USER:
            connection_args["user"] = settings.llm.MILVUS_USER
        if settings.llm.MILVUS_PASSWORD:
            connection_args["password"] = settings.llm.MILVUS_PASSWORD
        return connection_args

    def _ensure_legacy_connection_alias(self, connection_args: Dict[str, Any]) -> str:
        """预热并补齐旧版别名连接，避免历史调用路径找不到 alias。"""
        try:
            prewarm_client = MilvusClient(**connection_args)
            alias = getattr(prewarm_client, "_using", "")
            prewarm_client.close()
            if not alias:
                raise RuntimeError("MilvusClient did not provide a valid alias.")

            if not milvus_connections.has_connection(alias):
                milvus_connections.connect(alias=alias, db_name="", **connection_args)
                logger.debug(f"Registered legacy Milvus alias bridge: alias={alias}")
            return alias
        except Exception as exc:
            raise RuntimeError(
                f"Failed to ensure Milvus legacy alias bridge (uri={connection_args.get('uri')}): {exc}"
            ) from exc

    def _create_milvus_store(self, collection_name: str, connection_args: Dict[str, Any]) -> Milvus:
        """创建 LangChain Milvus 向量存储实例。"""
        return Milvus(
            embedding_function=self.service.embeddings,
            connection_args=connection_args,
            collection_name=collection_name,
            auto_id=True,
            drop_old=False,
        )

    def _get_vector_store(self, kb_id: int):
        """获取指定知识库的向量存储，并在必要时重试一次连接初始化。"""
        collection_name = f"{settings.llm.MILVUS_COLLECTION_PREFIX}{kb_id}"
        connection_args = self.service._build_milvus_connection_args()

        prewarm_alias = self.service._ensure_legacy_connection_alias(connection_args)
        logger.debug(
            f"Milvus alias prepared before vector store init: kb_id={kb_id}, "
            f"collection={collection_name}, alias={prewarm_alias}"
        )

        for attempt in (1, 2):
            try:
                store = self.service._create_milvus_store(collection_name, connection_args)
                alias = store.alias
                if not milvus_connections.has_connection(alias):
                    milvus_connections.connect(alias=alias, db_name="", **connection_args)
                    logger.debug(
                        f"Registered fallback Milvus alias bridge: kb_id={kb_id}, "
                        f"collection={collection_name}, alias={alias}"
                    )

                logger.info(
                    f"Milvus vector store ready: kb_id={kb_id}, collection={collection_name}, alias={alias}"
                )
                return store
            except ConnectionNotExistException:
                if attempt >= 2:
                    raise
                logger.warning(
                    "Milvus alias missing during store init, retrying once: "
                    f"kb_id={kb_id}, collection={collection_name}"
                )
                self.service._ensure_legacy_connection_alias(connection_args)
