"""知识库核心初始化与基础依赖模块"""

from typing import Any, Dict, List, Tuple

from langchain_community.embeddings import DashScopeEmbeddings
from langchain_milvus import Milvus
from langchain_openai import ChatOpenAI
from pymilvus import MilvusClient, connections as milvus_connections
from pymilvus.exceptions import ConnectionNotExistException

from app.core.config.settings import settings
from app.core.logger import logger_manager
from app.services.document_chunking import DocumentChunkingService
from app.utils.llm_factory import build_chat_llm
from app.services.knowledge_types import BM25Index, ChunkCandidate

logger = logger_manager.get_logger(__name__)


class KnowledgeCoreMixin:
    """知识库核心配置与初始化Mixin：提供知识库组件的初始化功能"""

    def _init_knowledge_components(self) -> None:
        """初始化嵌入模型、BM25缓存与文档分块器"""
        self.embeddings = DashScopeEmbeddings(
            model=settings.llm.EMBEDDING_MODEL,
            dashscope_api_key=settings.llm.QWEN_API_KEY
        )
        self._bm25_cache: dict[int, Tuple[float, List[ChunkCandidate], BM25Index]] = {}
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
        """获取用于文档分片摘要的LLM实例
        
        Returns:
            配置好的ChatOpenAI实例（temperature=0，用于摘要生成）
        """
        return build_chat_llm(
            model=settings.llm.DEFAULT_MODEL,
            temperature=0.0,
            streaming=False,
        )

    def _build_milvus_connection_args(self) -> Dict[str, Any]:
        """构建Milvus连接参数"""
        connection_args: Dict[str, Any] = {"uri": settings.llm.MILVUS_URI}
        if settings.llm.MILVUS_USER:
            connection_args["user"] = settings.llm.MILVUS_USER
        if settings.llm.MILVUS_PASSWORD:
            connection_args["password"] = settings.llm.MILVUS_PASSWORD
        return connection_args

    def _ensure_legacy_connection_alias(self, connection_args: Dict[str, Any]) -> str:
        """确保旧版pymilvus connections单例存在对应alias连接"""
        try:
            prewarm_client = MilvusClient(**connection_args)
            alias = getattr(prewarm_client, "_using", "")
            prewarm_client.close()
            if not alias:
                raise RuntimeError("MilvusClient did not provide a valid alias.")

            if not milvus_connections.has_connection(alias):
                # 传 db_name="" 以便让 pymilvus 从 URI path 自动解析数据库名。
                milvus_connections.connect(alias=alias, db_name="", **connection_args)
                logger.debug(f"Registered legacy Milvus alias bridge: alias={alias}")
            return alias
        except Exception as e:
            raise RuntimeError(
                f"Failed to ensure Milvus legacy alias bridge (uri={connection_args.get('uri')}): {e}"
            ) from e

    def _create_milvus_store(self, collection_name: str, connection_args: Dict[str, Any]) -> Milvus:
        """创建Milvus向量库实例"""
        return Milvus(
            embedding_function=self.embeddings,
            connection_args=connection_args,
            collection_name=collection_name,
            auto_id=True,
            drop_old=False,
        )

    def _get_vector_store(self, kb_id: int):
        """根据知识库ID构建/获取向量库实例

        Args:
            kb_id: 知识库ID

        Returns:
            Milvus向量存储实例
        """
        collection_name = f"{settings.llm.MILVUS_COLLECTION_PREFIX}{kb_id}"
        connection_args = self._build_milvus_connection_args()

        prewarm_alias = self._ensure_legacy_connection_alias(connection_args)
        logger.debug(
            f"Milvus alias prepared before vector store init: kb_id={kb_id}, "
            f"collection={collection_name}, alias={prewarm_alias}"
        )

        for attempt in (1, 2):
            try:
                store = self._create_milvus_store(collection_name, connection_args)
                alias = store.alias
                if not milvus_connections.has_connection(alias):
                    # 兜底：若当前 store alias 尚未注册，补注册一次。
                    milvus_connections.connect(alias=alias, db_name="", **connection_args)
                    logger.debug(
                        f"Registered fallback Milvus alias bridge: kb_id={kb_id}, "
                        f"collection={collection_name}, alias={alias}"
                    )

                logger.info(
                    f"Milvus vector store ready: kb_id={kb_id}, collection={collection_name}, alias={alias}"
                )
                return store
            except ConnectionNotExistException as e:
                if attempt >= 2:
                    raise
                logger.warning(
                    f"Milvus alias missing during store init, retrying once: "
                    f"kb_id={kb_id}, collection={collection_name}, error={e}"
                )
                self._ensure_legacy_connection_alias(connection_args)
