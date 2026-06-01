"""Wiki-RAG facade service."""

from __future__ import annotations

import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.wiki import wiki_crud
from app.models.wiki import WikiPatch
from app.services.wiki.compiler import WikiCompiler
from app.services.wiki.lint import WikiLint
from app.services.wiki.markdown import build_markdown_page, extract_frontmatter
from app.services.wiki.retriever import WikiRetriever
from app.services.wiki.storage import WikiStorage
from app.services.wiki.types import PAGE_FAQ, WikiCompileResult, WikiSearchHit


class WikiPatchNotFoundError(Exception):
    """Raised when a patch does not exist in the requested knowledge base."""


class WikiPatchConflictError(Exception):
    """Raised when a patch cannot transition from its current state."""


class WikiPatchUnsupportedOperationError(Exception):
    """Raised when a patch operation is not yet supported for application."""


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

    async def apply_patch(
        self,
        db: AsyncSession,
        *,
        kb_id: int,
        patch_id: int,
    ) -> WikiPatch:
        patch = await wiki_crud.get_patch(db, kb_id, patch_id)
        if patch is None:
            raise WikiPatchNotFoundError("Wiki patch not found")
        if patch.status != "pending":
            raise WikiPatchConflictError("Only pending wiki patches can be applied")

        target_path = self.storage.normalize_page_path(patch.target_path)
        current_page = await wiki_crud.get_page_by_path(db, kb_id, target_path)
        if patch.operation == "create" and (
            current_page is not None or self.storage.page_exists(kb_id, target_path)
        ):
            await wiki_crud.update_patch_status(
                db,
                patch,
                status="rejected",
                page_id=current_page.id if current_page is not None else None,
            )
            raise WikiPatchConflictError("Wiki patch target page already exists")

        next_content = self._build_patched_content(
            kb_id=kb_id,
            patch=patch,
            target_path=target_path,
            page_exists=current_page is not None,
        )
        self.storage.write_page(kb_id, target_path, next_content)

        page = await wiki_crud.upsert_page(
            db,
            kb_id=kb_id,
            path=target_path,
            title=self._resolve_page_title(
                target_path,
                next_content,
                fallback=current_page.title if current_page else patch.question,
            ),
            page_type=self._resolve_page_type(
                target_path,
                next_content,
                fallback=current_page.page_type if current_page else None,
            ),
            content_hash=self.storage.content_hash(next_content),
            source_doc_id=current_page.source_doc_id if current_page else None,
            provenance=self._patch_provenance(current_page, patch),
        )
        await wiki_crud.create_revision(
            db,
            page_id=page.id,
            kb_id=kb_id,
            path=target_path,
            content_hash=page.content_hash,
            content_snapshot=next_content,
            change_reason=f"apply wiki patch {patch.id}",
            provenance={"patch_id": patch.id, "operation": patch.operation},
        )

        links = self.compiler.link_extractor.extract(
            kb_id=kb_id,
            from_path=target_path,
            markdown=next_content,
            from_page_id=page.id,
        )
        await wiki_crud.replace_links(
            db,
            kb_id=kb_id,
            from_path=target_path,
            links=links,
        )
        applied_patch = await wiki_crud.update_patch_status(
            db,
            patch,
            status="applied",
            page_id=page.id,
        )
        self.compiler.storage = self.storage
        await self.compiler.refresh_index(db, kb_id=kb_id)
        return applied_patch

    async def reject_patch(
        self,
        db: AsyncSession,
        *,
        kb_id: int,
        patch_id: int,
    ) -> WikiPatch:
        patch = await wiki_crud.get_patch(db, kb_id, patch_id)
        if patch is None:
            raise WikiPatchNotFoundError("Wiki patch not found")
        if patch.status != "pending":
            raise WikiPatchConflictError("Only pending wiki patches can be rejected")
        return await wiki_crud.update_patch_status(db, patch, status="rejected")

    def _build_patched_content(
        self,
        *,
        kb_id: int,
        patch: WikiPatch,
        target_path: str,
        page_exists: bool,
    ) -> str:
        patch_markdown = patch.patch_markdown.strip()
        if not patch_markdown:
            raise WikiPatchUnsupportedOperationError("Wiki patch markdown is empty")

        if patch.operation == "append":
            if page_exists or self.storage.page_exists(kb_id, target_path):
                existing = self.storage.read_page(kb_id, target_path).rstrip()
                return f"{existing}\n\n{patch_markdown}\n"

            return build_markdown_page(
                {
                    "title": self._default_title_for_path(target_path),
                    "page_type": self._default_page_type_for_path(target_path),
                    "status": "active",
                },
                self._default_title_for_path(target_path),
                [("Entries", patch_markdown)],
            )

        if patch.operation == "create":
            if page_exists or self.storage.page_exists(kb_id, target_path):
                raise WikiPatchConflictError("Wiki patch target page already exists")
            return self._ensure_markdown_page(target_path, patch_markdown)

        raise WikiPatchUnsupportedOperationError(
            f"Unsupported wiki patch operation: {patch.operation}"
        )

    def _ensure_markdown_page(self, target_path: str, markdown: str) -> str:
        frontmatter, body = extract_frontmatter(markdown)
        if frontmatter and self._extract_h1(body):
            return self._ensure_trailing_newline(markdown)
        if self._extract_h1(markdown):
            return self._ensure_trailing_newline(markdown)

        title = self._default_title_for_path(target_path)
        return build_markdown_page(
            {
                "title": title,
                "page_type": self._default_page_type_for_path(target_path),
                "status": "active",
            },
            title,
            [("Content", markdown)],
        )

    @staticmethod
    def _ensure_trailing_newline(markdown: str) -> str:
        return markdown if markdown.endswith("\n") else f"{markdown}\n"

    def _resolve_page_title(
        self,
        target_path: str,
        markdown: str,
        *,
        fallback: str | None,
    ) -> str:
        frontmatter, body = extract_frontmatter(markdown)
        title = frontmatter.get("title") or self._extract_h1(body or markdown)
        resolved = title or fallback or self._default_title_for_path(target_path)
        return str(resolved).strip()

    def _resolve_page_type(
        self,
        target_path: str,
        markdown: str,
        *,
        fallback: str | None,
    ) -> str:
        frontmatter, _body = extract_frontmatter(markdown)
        page_type = frontmatter.get("page_type") or fallback
        return str(page_type or self._default_page_type_for_path(target_path)).strip()

    @staticmethod
    def _extract_h1(markdown: str) -> str | None:
        match = re.search(r"(?m)^#\s+(.+?)\s*$", markdown)
        if match is None:
            return None
        return match.group(1).strip()

    @staticmethod
    def _default_title_for_path(path: str) -> str:
        if path == PAGE_FAQ:
            return "FAQ"
        filename = path.rsplit("/", 1)[-1].removesuffix(".md")
        return filename.replace("-", " ").replace("_", " ").title() or "Wiki Page"

    @staticmethod
    def _default_page_type_for_path(path: str) -> str:
        if path == PAGE_FAQ:
            return "faq"
        if path in {"index.md", "schema.md", "log.md"}:
            return path.removesuffix(".md")
        return "topic"

    @staticmethod
    def _patch_provenance(current_page, patch: WikiPatch) -> dict:
        provenance = dict(getattr(current_page, "provenance", None) or {})
        provenance["last_patch_id"] = patch.id
        provenance["last_patch_operation"] = patch.operation
        provenance["last_patch_confidence"] = patch.confidence
        if patch.provenance:
            provenance["last_patch_provenance"] = patch.provenance
        return provenance
