"""Wiki-RAG facade service."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.wiki.compiler import WikiCompiler
from app.services.wiki.lint import WikiLint
from app.services.wiki.retriever import WikiRetriever
from app.services.wiki.storage import WikiStorage
from app.services.wiki.types import WikiCompileResult, WikiSearchHit


class WikiService:
    """Facade for Wiki-RAG operations."""

    def __init__(self, storage: WikiStorage | None = None) -> None:
        self.storage = storage or WikiStorage()
        self.compiler = WikiCompiler(storage=self.storage)
        self.retriever = WikiRetriever(storage=self.storage)
        self.lint = WikiLint(self.storage)
        self.ready = True

    async def compile_document(
        self,
        db: AsyncSession,
        *,
        kb_id: int,
        doc_id: int,
    ) -> WikiCompileResult:
        return await self.compiler.compile_document(db, kb_id=kb_id, doc_id=doc_id)

    async def search_pages(
        self,
        db: AsyncSession,
        *,
        kb_id: int,
        query: str,
        top_k: int,
    ) -> list[WikiSearchHit]:
        return await self.retriever.search(db, kb_id=kb_id, query=query, top_k=top_k)
