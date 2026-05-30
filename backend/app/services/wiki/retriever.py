"""Index-first Wiki-RAG retrieval."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.wiki import wiki_crud
from app.services.shared.bm25 import BM25Index, _tokenize
from app.services.wiki.links import WikiLinkExtractor
from app.services.wiki.markdown import extract_frontmatter
from app.services.wiki.storage import WikiStorage
from app.services.wiki.types import PAGE_INDEX, WikiSearchHit


_INDEX_LINK_BOOST = 0.25
_SNIPPET_LENGTH = 240
_WHITESPACE_RE = re.compile(r"\s+")


class WikiRetriever:
    """Search wiki pages with a small boost for index-linked navigation pages."""

    def __init__(self, storage: WikiStorage | None = None) -> None:
        self.storage = storage or WikiStorage()

    async def search(
        self,
        db: AsyncSession,
        *,
        kb_id: int,
        query: str,
        top_k: int,
    ) -> list[WikiSearchHit]:
        if top_k <= 0 or not query.strip():
            return []

        pages = await wiki_crud.list_pages(db, kb_id)
        if not pages:
            return []

        index_linked_paths = self._extract_index_linked_paths(kb_id)
        documents = []
        for page in pages:
            try:
                markdown = self.storage.read_page(kb_id, page.path)
            except (FileNotFoundError, OSError, ValueError):
                continue

            frontmatter, body = extract_frontmatter(markdown)
            searchable_text = "\n".join(
                [
                    page.title,
                    page.path,
                    page.page_type,
                    self._frontmatter_text(frontmatter),
                    body,
                ]
            )
            documents.append(
                {
                    "page": page,
                    "body": body,
                    "searchable_text": searchable_text,
                }
            )

        if not documents:
            return []

        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        index = BM25Index([_tokenize(doc["searchable_text"]) for doc in documents])
        base_scores = index.get_scores(query_tokens)
        if not base_scores:
            return []

        hits: list[WikiSearchHit] = []
        for doc, base_score in zip(documents, base_scores, strict=True):
            page = doc["page"]
            score = float(base_score)
            if page.path in index_linked_paths:
                score += _INDEX_LINK_BOOST
            if score <= 0:
                continue

            hits.append(
                WikiSearchHit(
                    page_id=page.id,
                    path=page.path,
                    title=page.title,
                    page_type=page.page_type,
                    score=score,
                    snippet=self._snippet(doc["body"]),
                )
            )

        return sorted(hits, key=lambda hit: (-hit.score, hit.path))[:top_k]

    def _extract_index_linked_paths(self, kb_id: int) -> set[str]:
        try:
            content = self.storage.read_page(kb_id, PAGE_INDEX)
        except (FileNotFoundError, OSError, ValueError):
            return set()

        paths: set[str] = set()
        for link in WikiLinkExtractor.extract(kb_id, PAGE_INDEX, content):
            target = (link.to_path or "").strip()
            if link.link_type != "related_to":
                continue
            if not target.endswith(".md") or "#" in target:
                continue
            try:
                paths.add(self.storage.normalize_page_path(target))
            except ValueError:
                continue

        return paths

    def _frontmatter_text(self, value: Any) -> str:
        if isinstance(value, dict):
            return " ".join(self._frontmatter_text(item) for item in value.values())
        if isinstance(value, list | tuple | set):
            return " ".join(self._frontmatter_text(item) for item in value)
        if value is None:
            return ""
        return str(value)

    def _snippet(self, body: str) -> str:
        return _WHITESPACE_RE.sub(" ", body).strip()[:_SNIPPET_LENGTH]
