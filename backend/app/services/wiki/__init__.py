"""Wiki-RAG service package."""

from app.services.wiki.service import WikiService

wiki_service = WikiService()

__all__ = ["WikiService", "wiki_service"]
