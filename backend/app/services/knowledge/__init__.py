"""知识库服务包入口。"""

from app.services.knowledge.service import KnowledgeService
from app.services.knowledge.types import ChunkCandidate, SearchItem

kb_service = KnowledgeService()

__all__ = ["ChunkCandidate", "KnowledgeService", "SearchItem", "kb_service"]
