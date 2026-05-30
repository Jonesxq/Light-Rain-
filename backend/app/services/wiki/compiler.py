"""Compile completed documents into filesystem-backed wiki pages."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.knowledge import kb_crud
from app.crud.wiki import wiki_crud
from app.models.knowledge import DocStatus, Document
from app.services.wiki.links import WikiLinkExtractor
from app.services.wiki.markdown import (
    build_frontmatter,
    build_log_heading,
    build_markdown_page,
    slugify_title,
)
from app.services.wiki.storage import WikiStorage
from app.services.wiki.types import (
    PAGE_INDEX,
    PAGE_LOG,
    PAGE_SCHEMA,
    WikiCompileResult,
    WikiPageInput,
)


class WikiCompiler:
    """Compile processed knowledge-base documents into wiki Markdown pages."""

    def __init__(self, storage: WikiStorage | None = None) -> None:
        self.storage = storage or WikiStorage()
        self.link_extractor = WikiLinkExtractor()

    async def compile_document(
        self,
        db: AsyncSession,
        *,
        kb_id: int,
        doc_id: int,
    ) -> WikiCompileResult:
        doc = await kb_crud.get_document(db, doc_id)
        if doc is None or doc.kb_id != kb_id:
            raise ValueError("Document not found")
        if doc.status != DocStatus.COMPLETED:
            raise ValueError("Document is not completed")

        now = datetime.utcnow()
        chunks = self._read_sidecar_chunks(doc)
        source_path = f"sources/{doc.id}-{slugify_title(doc.file_name)}.md"
        pages = [
            self._build_schema_page(now, doc, chunks),
            self._build_index_page(now, doc, source_path),
            self._build_log_page(kb_id, now, doc),
            self._build_source_page(now, doc, source_path, chunks),
        ]

        pages_changed = 0
        for page_input in pages:
            await self._write_and_record_page(db, kb_id=kb_id, page_input=page_input)
            pages_changed += 1

        patch = await wiki_crud.create_patch(
            db,
            kb_id=kb_id,
            target_path="topics/vector-search.md",
            operation="create",
            patch_markdown=self._build_topic_patch(doc, source_path),
            question="Should this source become a topic page?",
            answer="Create a vector search topic candidate from the ingested source.",
            rationale="The compiled source mentions vector search.",
            confidence=0.5,
            provenance={
                "compiler": "wiki",
                "source_doc_id": doc.id,
                "source_path": source_path,
            },
        )
        patches_created = 1 if patch.id is not None else 0

        await wiki_crud.create_run(
            db,
            kb_id=kb_id,
            doc_id=doc.id,
            run_type="ingest_doc",
            status="succeeded",
            metrics={
                "pages_changed": pages_changed,
                "patches_created": patches_created,
                "chunk_count": len(chunks),
                "source_path": source_path,
            },
        )

        return WikiCompileResult(
            kb_id=kb_id,
            doc_id=doc.id,
            pages_changed=pages_changed,
            patches_created=patches_created,
            warnings=[],
        )

    def _read_sidecar_chunks(self, doc: Document) -> list[dict[str, Any]]:
        sidecar_path = Path(f"{doc.file_path}.chunks.jsonl")
        if not sidecar_path.exists():
            return []

        chunks: list[dict[str, Any]] = []
        with sidecar_path.open("r", encoding="utf-8") as sidecar_file:
            for line in sidecar_file:
                stripped = line.strip()
                if not stripped:
                    continue
                parsed = json.loads(stripped)
                if isinstance(parsed, dict):
                    chunks.append(parsed)
                else:
                    chunks.append({"content": str(parsed)})
        return chunks

    def _build_schema_page(
        self,
        now: datetime,
        doc: Document,
        chunks: list[dict[str, Any]],
    ) -> WikiPageInput:
        content = build_markdown_page(
            {
                "title": "Schema",
                "page_type": "schema",
                "status": "active",
                "updated_at": now.isoformat(),
                "tags": ["schema", "wiki"],
            },
            "Schema",
            [
                (
                    "Page Types",
                    "- `index`: navigation across compiled sources\n"
                    "- `source`: provenance-preserving document pages\n"
                    "- `topic`: curated or proposed concept pages",
                ),
                (
                    "Current Ingest",
                    f"- Document: `{doc.file_name}`\n"
                    f"- Chunks: `{len(chunks)}`\n"
                    "- Source markers: `[source:doc=<id> chunk_index=<n>]`",
                ),
            ],
        )
        return WikiPageInput(
            path=PAGE_SCHEMA,
            title="Schema",
            page_type="schema",
            content=content,
            provenance={"compiler": "wiki", "source_doc_id": doc.id},
        )

    def _build_index_page(
        self,
        now: datetime,
        doc: Document,
        source_path: str,
    ) -> WikiPageInput:
        content = build_markdown_page(
            {
                "title": "Index",
                "page_type": "index",
                "status": "active",
                "updated_at": now.isoformat(),
                "tags": ["index"],
            },
            "Index",
            [
                (
                    "Sources",
                    f"- [{doc.file_name}]({source_path})",
                ),
                (
                    "Topic Candidates",
                    "- [Vector Search](topics/vector-search.md)",
                ),
            ],
        )
        return WikiPageInput(
            path=PAGE_INDEX,
            title="Index",
            page_type="index",
            content=content,
            provenance={"compiler": "wiki", "source_doc_id": doc.id},
        )

    def _build_log_page(self, kb_id: int, now: datetime, doc: Document) -> WikiPageInput:
        heading = build_log_heading(now, "ingest", [f"doc_id={doc.id}", doc.file_name])
        entry = f"{heading}\n\nCompiled `{doc.file_name}` into wiki pages.\n"
        if self.storage.page_exists(kb_id, PAGE_LOG):
            existing = self.storage.read_page(kb_id, PAGE_LOG).rstrip()
            content = f"{existing}\n\n{entry}"
        else:
            content = f"# Log\n\n{entry}"

        return WikiPageInput(
            path=PAGE_LOG,
            title="Log",
            page_type="log",
            content=content,
            provenance={"compiler": "wiki", "source_doc_id": doc.id},
        )

    def _build_source_page(
        self,
        now: datetime,
        doc: Document,
        source_path: str,
        chunks: list[dict[str, Any]],
    ) -> WikiPageInput:
        chunk_sections = self._build_chunk_sections(doc, chunks)
        content = build_markdown_page(
            {
                "title": doc.file_name,
                "page_type": "source",
                "status": "active",
                "doc_id": doc.id,
                "file_name": doc.file_name,
                "file_type": doc.file_type,
                "chunk_count": len(chunks),
                "source_count": len(chunks),
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
                "tags": ["source", slugify_title(doc.file_type, fallback="file")],
            },
            doc.file_name,
            [
                (
                    "Source Metadata",
                    f"- Document ID: `{doc.id}`\n"
                    f"- File type: `{doc.file_type}`\n"
                    f"- Chunks: `{len(chunks)}`",
                ),
                ("Chunks", chunk_sections),
            ],
        )
        return WikiPageInput(
            path=source_path,
            title=doc.file_name,
            page_type="source",
            content=content,
            source_doc_id=doc.id,
            provenance={
                "compiler": "wiki",
                "source_doc_id": doc.id,
                "source_count": len(chunks),
            },
        )

    def _build_chunk_sections(self, doc: Document, chunks: list[dict[str, Any]]) -> str:
        if not chunks:
            return f"[source:doc={doc.id} chunk_index=0]\n\n_No chunks found._"

        blocks: list[str] = []
        for fallback_index, chunk in enumerate(chunks):
            chunk_index = chunk.get("chunk_index", fallback_index)
            content = self._chunk_content(chunk)
            blocks.append(
                f"### Chunk {chunk_index}\n\n"
                f"[source:doc={doc.id} chunk_index={chunk_index}]\n\n"
                f"{content}"
            )
        return "\n\n".join(blocks)

    @staticmethod
    def _chunk_content(chunk: dict[str, Any]) -> str:
        for key in ("content", "text", "page_content"):
            value = chunk.get(key)
            if value:
                return str(value).strip()
        return "_No chunk content._"

    async def _write_and_record_page(
        self,
        db: AsyncSession,
        *,
        kb_id: int,
        page_input: WikiPageInput,
    ) -> None:
        self.storage.write_page(kb_id, page_input.path, page_input.content)
        content_hash = self.storage.content_hash(page_input.content)
        page = await wiki_crud.upsert_page(
            db,
            kb_id=kb_id,
            path=page_input.path,
            title=page_input.title,
            page_type=page_input.page_type,
            content_hash=content_hash,
            source_doc_id=page_input.source_doc_id,
            provenance=page_input.provenance,
        )
        await wiki_crud.create_revision(
            db,
            page_id=page.id,
            kb_id=kb_id,
            path=page_input.path,
            content_hash=content_hash,
            content_snapshot=page_input.content,
            change_reason=f"compile {page_input.page_type} page",
            provenance=page_input.provenance,
        )

        links = self.link_extractor.extract(
            kb_id=kb_id,
            from_path=page_input.path,
            markdown=page_input.content,
            from_page_id=page.id,
        )
        await wiki_crud.replace_links(
            db,
            kb_id=kb_id,
            from_path=page_input.path,
            links=links,
        )

    @staticmethod
    def _build_topic_patch(doc: Document, source_path: str) -> str:
        return (
            build_frontmatter(
                {
                    "title": "Vector Search",
                    "page_type": "topic",
                    "status": "active",
                    "source_doc_id": doc.id,
                    "tags": ["topic", "vector-search"],
                }
            )
            + "\n\n"
            + "# Vector Search\n\n"
            + f"Seed this topic from [{doc.file_name}]({source_path}).\n"
        )
