"""Wiki database operations."""

from datetime import datetime
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import delete, desc, select

from app.models.wiki import WikiLink, WikiPage, WikiPageRevision, WikiPatch, WikiRun


class WikiCRUD:
    """CRUD helpers for Wiki-RAG tables."""

    async def upsert_page(
        self,
        db: AsyncSession,
        *,
        kb_id: int,
        path: str,
        title: str,
        page_type: str,
        content_hash: str,
        source_doc_id: Optional[int] = None,
        provenance: Optional[dict] = None,
        status: str = "active",
    ) -> WikiPage:
        page = await self.get_page_by_path(db, kb_id, path)
        if page is not None:
            self._apply_page_update(
                page,
                title=title,
                page_type=page_type,
                content_hash=content_hash,
                source_doc_id=source_doc_id,
                provenance=provenance,
                status=status,
            )
            db.add(page)
            await db.commit()
            await db.refresh(page)
            return page

        page = WikiPage(
            kb_id=kb_id,
            path=path,
            title=title,
            page_type=page_type,
            content_hash=content_hash,
            source_doc_id=source_doc_id,
            provenance=provenance or {},
            status=status,
        )
        db.add(page)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            page = await self.get_page_by_path(db, kb_id, path)
            if page is None:
                raise

            self._apply_page_update(
                page,
                title=title,
                page_type=page_type,
                content_hash=content_hash,
                source_doc_id=source_doc_id,
                provenance=provenance,
                status=status,
            )
            db.add(page)
            await db.commit()

        await db.refresh(page)
        return page

    def _apply_page_update(
        self,
        page: WikiPage,
        *,
        title: str,
        page_type: str,
        content_hash: str,
        source_doc_id: Optional[int],
        provenance: Optional[dict],
        status: str,
    ) -> None:
        page.title = title
        page.page_type = page_type
        page.content_hash = content_hash
        page.source_doc_id = source_doc_id
        if provenance is not None:
            page.provenance = provenance
        page.status = status
        page.updated_at = datetime.utcnow()

    async def get_page_by_path(
        self,
        db: AsyncSession,
        kb_id: int,
        path: str,
    ) -> Optional[WikiPage]:
        statement = select(WikiPage).where(
            WikiPage.kb_id == kb_id, WikiPage.path == path
        )
        result = await db.execute(statement)
        return result.scalar_one_or_none()

    async def get_page(
        self,
        db: AsyncSession,
        kb_id: int,
        page_id: int,
    ) -> Optional[WikiPage]:
        statement = select(WikiPage).where(
            WikiPage.kb_id == kb_id, WikiPage.id == page_id
        )
        result = await db.execute(statement)
        return result.scalar_one_or_none()

    async def list_pages(self, db: AsyncSession, kb_id: int) -> list[WikiPage]:
        statement = (
            select(WikiPage)
            .where(WikiPage.kb_id == kb_id, WikiPage.status != "deleted")
            .order_by(WikiPage.path.asc())
        )
        result = await db.execute(statement)
        return list(result.scalars().all())

    async def create_revision(
        self,
        db: AsyncSession,
        *,
        page_id: Optional[int],
        kb_id: int,
        path: str,
        content_hash: str,
        content_snapshot: str,
        change_reason: str,
        provenance: Optional[dict] = None,
    ) -> WikiPageRevision:
        revision = WikiPageRevision(
            page_id=page_id,
            kb_id=kb_id,
            path=path,
            content_hash=content_hash,
            content_snapshot=content_snapshot,
            change_reason=change_reason,
            provenance=provenance or {},
        )
        db.add(revision)
        await db.commit()
        await db.refresh(revision)
        return revision

    async def list_revisions(
        self,
        db: AsyncSession,
        page_id: int,
    ) -> list[WikiPageRevision]:
        statement = (
            select(WikiPageRevision)
            .where(WikiPageRevision.page_id == page_id)
            .order_by(desc(WikiPageRevision.created_at), desc(WikiPageRevision.id))
        )
        result = await db.execute(statement)
        return list(result.scalars().all())

    async def create_patch(
        self,
        db: AsyncSession,
        *,
        kb_id: int,
        target_path: str,
        operation: str,
        patch_markdown: str,
        page_id: Optional[int] = None,
        status: str = "pending",
        question: Optional[str] = None,
        answer: Optional[str] = None,
        rationale: Optional[str] = None,
        confidence: float = 0.0,
        provenance: Optional[dict] = None,
        created_by_message_id: Optional[int] = None,
        applied_at: Optional[datetime] = None,
        rejected_at: Optional[datetime] = None,
    ) -> WikiPatch:
        patch = WikiPatch(
            kb_id=kb_id,
            page_id=page_id,
            target_path=target_path,
            operation=operation,
            status=status,
            question=question,
            answer=answer,
            patch_markdown=patch_markdown,
            rationale=rationale,
            confidence=confidence,
            provenance=provenance or {},
            created_by_message_id=created_by_message_id,
            applied_at=applied_at,
            rejected_at=rejected_at,
        )
        db.add(patch)
        await db.commit()
        await db.refresh(patch)
        return patch

    async def list_patches(
        self,
        db: AsyncSession,
        kb_id: int,
        status: Optional[str] = None,
    ) -> list[WikiPatch]:
        statement = select(WikiPatch).where(WikiPatch.kb_id == kb_id)
        if status is not None:
            statement = statement.where(WikiPatch.status == status)
        statement = statement.order_by(desc(WikiPatch.created_at), desc(WikiPatch.id))
        result = await db.execute(statement)
        return list(result.scalars().all())

    async def replace_links(
        self,
        db: AsyncSession,
        *,
        kb_id: int,
        from_path: str,
        links: list[WikiLink],
    ) -> None:
        for link in links:
            await self._validate_link_scope(
                db, kb_id=kb_id, from_path=from_path, link=link
            )

        await db.execute(
            delete(WikiLink).where(
                WikiLink.kb_id == kb_id,
                WikiLink.from_path == from_path,
            )
        )
        for link in links:
            db.add(
                WikiLink(
                    kb_id=kb_id,
                    from_page_id=link.from_page_id,
                    from_path=from_path,
                    to_page_id=link.to_page_id,
                    to_path=link.to_path,
                    link_type=link.link_type,
                    anchor_text=link.anchor_text,
                    provenance=dict(link.provenance or {}),
                )
            )
        await db.commit()

    async def _validate_link_scope(
        self,
        db: AsyncSession,
        *,
        kb_id: int,
        from_path: str,
        link: WikiLink,
    ) -> None:
        if link.kb_id != kb_id:
            raise ValueError("Wiki link kb_id must match replace_links kb_id")
        if link.from_path != from_path:
            raise ValueError("Wiki link from_path must match replace_links from_path")

        if link.from_page_id is not None:
            from_page = await self.get_page(db, kb_id, link.from_page_id)
            if from_page is None or from_page.path != from_path:
                raise ValueError("Wiki link from_page_id must match kb_id and from_path")

        if link.to_page_id is not None:
            to_page = await self.get_page(db, kb_id, link.to_page_id)
            if to_page is None or to_page.path != link.to_path:
                raise ValueError("Wiki link to_page_id must match kb_id and to_path")

    async def create_run(
        self,
        db: AsyncSession,
        *,
        kb_id: int,
        run_type: str,
        status: str,
        doc_id: Optional[int] = None,
        metrics: Optional[dict] = None,
        error_msg: Optional[str] = None,
    ) -> WikiRun:
        run = WikiRun(
            kb_id=kb_id,
            doc_id=doc_id,
            run_type=run_type,
            status=status,
            metrics=metrics or {},
            error_msg=error_msg,
            finished_at=(
                datetime.utcnow() if status in {"succeeded", "failed"} else None
            ),
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        return run


wiki_crud = WikiCRUD()
