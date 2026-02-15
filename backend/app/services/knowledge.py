"""知识库服务门面（聚合 mixins 并对外导出）。"""

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
    """知识库服务门面：由多个 mixin 组合而成。"""

    def __init__(self):
        self._init_knowledge_components()


# 实例化全局服务对象
kb_service = KnowledgeService()
