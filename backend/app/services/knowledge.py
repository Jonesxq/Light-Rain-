"""知识库服务门面（聚合mixins并对外导出）模块"""

from app.services.knowledge_types import BM25Index, ChunkCandidate, SearchItem
from app.services.knowledge_core_mixin import KnowledgeCoreMixin
from app.services.knowledge_storage_mixin import KnowledgeStorageMixin
from app.services.knowledge_bm25_mixin import KnowledgeBM25Mixin
from app.services.knowledge_vector_mixin import KnowledgeVectorMixin
from app.services.knowledge_search_mixin import KnowledgeSearchMixin
from app.services.knowledge_ingest_mixin import KnowledgeIngestMixin


class KnowledgeService(
    KnowledgeCoreMixin,
    KnowledgeStorageMixin,
    KnowledgeBM25Mixin,
    KnowledgeVectorMixin,
    KnowledgeSearchMixin,
    KnowledgeIngestMixin,
):
    """知识库服务门面类：由多个Mixin组合而成，提供完整的知识库功能
    
    功能包括：
    - 核心组件初始化（嵌入模型、BM25缓存、分块器）
    - Sidecar文件读写和原始分片管理
    - BM25索引和RRF融合
    - 向量检索和元数据解析
    - 知识库检索和重排
    - 文档导入、重建索引和删除
    """

    def __init__(self):
        """初始化知识库服务，调用核心组件初始化方法"""
        self._init_knowledge_components()


kb_service = KnowledgeService()
