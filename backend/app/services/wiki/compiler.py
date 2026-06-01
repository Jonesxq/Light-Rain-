"""Compile completed documents into filesystem-backed wiki pages."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.knowledge import kb_crud
from app.crud.wiki import wiki_crud
from app.models.knowledge import DocStatus, Document
from app.models.wiki import WikiPage
from app.services.wiki.links import WikiLinkExtractor
from app.services.wiki.markdown import (
    build_frontmatter,
    build_log_heading,
    build_markdown_page,
    extract_frontmatter,
    slugify_title,
)
from app.services.wiki.storage import PROJECT_ROOT, WikiStorage
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
        source_path = self._source_path_for_doc(doc)
        topic_path = f"topics/doc-{doc.id}-topic.md"
        pages = [
            self._build_log_page(kb_id, now, doc),
            self._build_source_page(now, doc, source_path, chunks),
        ]

        pages_changed = 0
        for page_input in pages:
            await self._write_and_record_page(db, kb_id=kb_id, page_input=page_input)
            pages_changed += 1

        completed_docs = await kb_crud.get_completed_documents(db, kb_id)
        await self._write_and_record_page(
            db,
            kb_id=kb_id,
            page_input=self._build_schema_page(now, completed_docs),
        )
        pages_changed += 1

        topic_refreshed = await self._refresh_topic_page_if_compiler_owned(
            db,
            kb_id=kb_id,
            doc=doc,
            source_path=source_path,
            topic_path=topic_path,
            chunks=chunks,
            now=now,
        )
        if topic_refreshed:
            pages_changed += 1

        await self.refresh_index(db, kb_id=kb_id, now=now)
        pages_changed += 1

        patch = await self._create_topic_patch_if_needed(
            db,
            kb_id=kb_id,
            doc=doc,
            source_path=source_path,
            topic_path=topic_path,
            chunks=chunks,
            now=now,
        )
        patches_created = 1 if patch is not None and patch.id is not None else 0

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

    async def _refresh_topic_page_if_compiler_owned(
        self,
        db: AsyncSession,
        *,
        kb_id: int,
        doc: Document,
        source_path: str,
        topic_path: str,
        chunks: list[dict[str, Any]],
        now: datetime,
    ) -> bool:
        existing_page = await wiki_crud.get_page_by_path(db, kb_id, topic_path)
        if existing_page is None and not self.storage.page_exists(kb_id, topic_path):
            return False
        if not self.storage.page_exists(kb_id, topic_path):
            return False

        try:
            existing_markdown = self.storage.read_page(kb_id, topic_path)
        except (OSError, ValueError):
            return False

        if not (
            self._is_legacy_placeholder_topic(existing_markdown)
            or self._is_compiler_generated_topic(existing_markdown, doc)
        ):
            return False

        await self._write_and_record_page(
            db,
            kb_id=kb_id,
            page_input=self._build_topic_page(
                now,
                doc,
                source_path,
                topic_path,
                chunks,
            ),
        )
        refreshed_page = await wiki_crud.get_page_by_path(db, kb_id, topic_path)
        await wiki_crud.reject_pending_create_patches_for_target(
            db,
            kb_id=kb_id,
            target_path=topic_path,
            page_id=refreshed_page.id if refreshed_page is not None else None,
        )
        return True

    @staticmethod
    def _is_legacy_placeholder_topic(markdown: str) -> bool:
        return (
            "## 待整理要点" in markdown
            and "请审核该来源是否适合沉淀为独立主题页" in markdown
        )

    @staticmethod
    def _is_compiler_generated_topic(markdown: str, doc: Document) -> bool:
        frontmatter, body = extract_frontmatter(markdown)
        if frontmatter.get("page_type") != "topic":
            return False

        source_doc_id = frontmatter.get("source_doc_id")
        if source_doc_id is not None:
            try:
                if int(source_doc_id) != doc.id:
                    return False
            except (TypeError, ValueError):
                return False

        return (
            "由已编译来源片段自动整理" in body
            and "## 关键要点" in body
            and "## 后续维护" in body
        )

    async def _create_topic_patch_if_needed(
        self,
        db: AsyncSession,
        *,
        kb_id: int,
        doc: Document,
        source_path: str,
        topic_path: str,
        chunks: list[dict[str, Any]],
        now: datetime,
    ):
        existing_page = await wiki_crud.get_page_by_path(db, kb_id, topic_path)
        if existing_page is not None or self.storage.page_exists(kb_id, topic_path):
            await wiki_crud.reject_pending_create_patches_for_target(
                db,
                kb_id=kb_id,
                target_path=topic_path,
                page_id=existing_page.id if existing_page is not None else None,
            )
            return None

        existing_patches = await wiki_crud.list_patches_by_target(
            db,
            kb_id=kb_id,
            target_path=topic_path,
            operation="create",
        )
        if existing_patches:
            return None

        return await wiki_crud.create_patch(
            db,
            kb_id=kb_id,
            target_path=topic_path,
            operation="create",
            patch_markdown=self._build_topic_patch(
                now,
                doc,
                source_path,
                topic_path,
                chunks,
            ),
            question="是否将该来源整理成中文主题页？",
            answer=f"基于《{doc.file_name}》创建一个中文主题页候选，便于后续人工审核和归纳。",
            rationale="文档已编译为来源页，建议由人工确认是否需要沉淀为主题页。",
            confidence=0.5,
            provenance={
                "compiler": "wiki",
                "source_doc_id": doc.id,
                "source_path": source_path,
                "topic_path": topic_path,
            },
        )

    def _read_sidecar_chunks(self, doc: Document) -> list[dict[str, Any]]:
        sidecar_path = Path(f"{self._resolve_document_path(doc.file_path)}.chunks.jsonl")
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

    @staticmethod
    def _resolve_document_path(file_path: str | Path) -> Path:
        path = Path(file_path)
        if path.is_absolute():
            return path
        return PROJECT_ROOT / path

    def _build_schema_page(
        self,
        now: datetime,
        documents: list[Document],
    ) -> WikiPageInput:
        document_items = self._build_schema_document_items(documents)
        content = build_markdown_page(
            {
                "title": "Wiki 维护协议",
                "page_type": "schema",
                "status": "active",
                "updated_at": now.isoformat(),
                "document_count": len(documents),
                "tags": ["schema", "wiki", "维护协议"],
            },
            "Wiki 维护协议",
            [
                (
                    "知识库边界",
                    "- 一个 Wiki 只维护当前这一个知识库，不跨知识库混用来源、主题页或回答记忆\n"
                    "- 当前知识库的上传文档会编译为 `sources/*.md` 来源页\n"
                    "- 后续沉淀出的稳定结论会进入 `topics/*.md` 中文主题页",
                ),
                (
                    "已上传文档",
                    document_items,
                ),
                (
                    "页面类型",
                    "- `index`：知识库 Wiki 首页，汇总来源页与主题页\n"
                    "- `source`：保留来源和引用标记的上传文档页\n"
                    "- `topic`：人工采纳或后续沉淀的中文主题页\n"
                    "- `schema`：当前知识库的 Wiki 维护协议\n"
                    "- `log`：Wiki 编译和更新日志",
                ),
                (
                    "回答流程",
                    "- 一阶段先查询当前知识库 Wiki；如果 Wiki 已能回答用户问题，就直接基于 Wiki 返回答案\n"
                    "- Wiki 不足以回答时，再进入二阶段 RAG 检索当前知识库的原始文档 chunks\n"
                    "- 二阶段产生的高质量答案应进入待写回流程，供人工采纳后沉淀为 Wiki 内容",
                ),
                (
                    "写回规则",
                    "- 新稳定概念、规则、定义、问答结论优先写入或更新 `topics/*.md`\n"
                    "- 写回内容必须保留来源链接或来源标记，避免形成无出处总结\n"
                    "- 如果答案只适合一次性回复，不具备复用价值，则不写回 Wiki\n"
                    "- 人工采纳后，把高质量答案沉淀回 Wiki，并更新 `index.md` 与 `log.md`",
                ),
                (
                    "引用标记",
                    "- 来源页使用 `[source:doc=<文档ID> chunk_index=<分块序号>]` 标记可追溯片段\n"
                    "- 主题页应保留必要来源链接，方便回答时回溯到原文\n"
                    "- 回答用户时优先引用 Wiki 主题页；需要精确原文时再引用来源页片段",
                ),
            ],
        )
        return WikiPageInput(
            path=PAGE_SCHEMA,
            title="Wiki 维护协议",
            page_type="schema",
            content=content,
            provenance={
                "compiler": "wiki",
                "source_doc_ids": [doc.id for doc in documents],
            },
        )

    def _build_schema_document_items(self, documents: list[Document]) -> str:
        if not documents:
            return "- 暂无已完成文档"

        sorted_documents = sorted(documents, key=lambda doc: doc.id or 0)
        items: list[str] = []
        for doc in sorted_documents:
            source_path = self._source_path_for_doc(doc)
            chunk_count = self._schema_chunk_count(doc)
            items.append(
                f"- [{doc.file_name}]({source_path})"
                f"（文档 ID：`{doc.id}`，分块数：`{chunk_count}`）"
            )
        return "\n".join(items)

    def _schema_chunk_count(self, doc: Document) -> int:
        sidecar_chunk_count = len(self._read_sidecar_chunks(doc))
        if sidecar_chunk_count:
            return sidecar_chunk_count
        return int(doc.chunk_count or 0)

    @staticmethod
    def _source_path_for_doc(doc: Document) -> str:
        return f"sources/{doc.id}-{slugify_title(doc.file_name)}.md"

    async def refresh_index(
        self,
        db: AsyncSession,
        *,
        kb_id: int,
        now: datetime | None = None,
    ) -> None:
        pages = await wiki_crud.list_pages(db, kb_id)
        page_input = self._build_index_page(kb_id, now or datetime.utcnow(), pages)
        await self._write_and_record_page(db, kb_id=kb_id, page_input=page_input)

    def _build_index_page(
        self,
        kb_id: int,
        now: datetime,
        pages: list[WikiPage],
    ) -> WikiPageInput:
        source_items = self._build_index_links(kb_id, pages, page_type="source")
        topic_items = self._build_index_links(kb_id, pages, page_type="topic")
        content = build_markdown_page(
            {
                "title": "Wiki 首页",
                "page_type": "index",
                "status": "active",
                "updated_at": now.isoformat(),
                "tags": ["index"],
            },
            "Wiki 首页",
            [
                (
                    "来源页",
                    source_items or "- 暂无来源页",
                ),
                (
                    "主题页",
                    topic_items or "- 暂无主题页",
                ),
            ],
        )
        return WikiPageInput(
            path=PAGE_INDEX,
            title="Wiki 首页",
            page_type="index",
            content=content,
            provenance={"compiler": "wiki", "page_count": len(pages)},
        )

    def _build_index_links(
        self,
        kb_id: int,
        pages: list[WikiPage],
        *,
        page_type: str,
    ) -> str:
        filtered_pages = sorted(
            (page for page in pages if page.page_type == page_type),
            key=lambda page: page.path,
        )
        items: list[str] = []
        for page in filtered_pages:
            frontmatter = self._page_frontmatter(kb_id, page.path)
            summary = self._page_summary(kb_id, page.path)
            metadata = self._index_metadata(page, frontmatter)
            items.append(
                f"- [{page.title or page.path}]({page.path})\n"
                f"  - {metadata}\n"
                f"  - 摘要：{summary}"
            )

        return "\n".join(items)

    @staticmethod
    def _index_metadata(page: WikiPage, frontmatter: dict[str, Any]) -> str:
        if page.page_type == "source":
            doc_id = frontmatter.get("doc_id") or page.source_doc_id
            chunk_count = frontmatter.get("chunk_count", frontmatter.get("source_count"))
            fields = ["类型：来源页"]
            if doc_id is not None:
                fields.append(f"文档 ID：`{doc_id}`")
            if chunk_count is not None:
                fields.append(f"分块数：`{chunk_count}`")
            return "；".join(fields)

        if page.page_type == "topic":
            source_doc_id = frontmatter.get("source_doc_id") or page.source_doc_id
            fields = ["类型：主题页"]
            if source_doc_id is not None:
                fields.append(f"来源文档 ID：`{source_doc_id}`")
            return "；".join(fields)

        return f"类型：{page.page_type}"

    def _page_frontmatter(self, kb_id: int, page_path: str) -> dict[str, Any]:
        try:
            markdown = self.storage.read_page(kb_id, page_path)
        except (OSError, ValueError):
            return {}
        frontmatter, _body = extract_frontmatter(markdown)
        return frontmatter

    def _page_summary(self, kb_id: int, page_path: str) -> str:
        try:
            markdown = self.storage.read_page(kb_id, page_path)
        except (OSError, ValueError):
            return "暂无摘要"

        _frontmatter, body = extract_frontmatter(markdown)
        for line in body.splitlines():
            stripped = line.strip()
            if "摘要：" in stripped:
                _label, summary = stripped.split("摘要：", 1)
                if summary.strip():
                    return self._truncate_text(summary.strip(), max_chars=180)

        return self._plain_text_excerpt(body, max_chars=180) or "暂无摘要"

    def _plain_text_excerpt(self, markdown: str, *, max_chars: int) -> str:
        lines: list[str] = []
        for line in markdown.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#") or stripped.startswith("[source:doc="):
                continue
            if stripped in {"---"}:
                continue
            lines.append(stripped.lstrip("- ").strip())

        text = " ".join(lines)
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        text = text.replace("`", "")
        return self._truncate_text(text, max_chars=max_chars)

    def _build_log_page(
        self,
        kb_id: int,
        now: datetime,
        doc: Document,
    ) -> WikiPageInput:
        frontmatter = {
            "title": "Log",
            "page_type": "log",
            "status": "active",
            "updated_at": now.isoformat(),
            "tags": ["log"],
            "source_doc_id": doc.id,
        }
        heading = build_log_heading(now, "ingest", [f"doc_id={doc.id}", doc.file_name])
        entry = f"{heading}\n\nCompiled `{doc.file_name}` into wiki pages.\n"
        if self.storage.page_exists(kb_id, PAGE_LOG):
            existing = self.storage.read_page(kb_id, PAGE_LOG).rstrip()
            existing_frontmatter, _body = extract_frontmatter(existing)
            if existing_frontmatter:
                content = f"{existing}\n\n{entry}"
            else:
                content = f"{build_frontmatter(frontmatter)}\n\n{existing}\n\n{entry}"
        else:
            content = build_markdown_page(frontmatter, "Log", [("Entries", entry)])

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
        source_summary = self._build_source_summary(doc, chunks)
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
                ("来源摘要", source_summary),
                ("原文片段", chunk_sections),
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

    def _build_source_summary(
        self,
        doc: Document,
        chunks: list[dict[str, Any]],
    ) -> str:
        return (
            f"- 文档 ID：`{doc.id}`\n"
            f"- 文件名：`{doc.file_name}`\n"
            f"- 文件类型：`{doc.file_type}`\n"
            f"- 分块数：`{len(chunks)}`\n"
            f"- 摘要：{self._document_summary(chunks)}"
        )

    def _build_chunk_sections(self, doc: Document, chunks: list[dict[str, Any]]) -> str:
        if not chunks:
            return f"[source:doc={doc.id} chunk_index=0]\n\n暂无分块内容。"

        blocks: list[str] = []
        for fallback_index, chunk in enumerate(chunks):
            chunk_index = chunk.get("chunk_index", fallback_index)
            content = self._chunk_content(chunk)
            blocks.append(
                f"### 片段 {chunk_index}\n\n"
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
        return "暂无分块内容。"

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

    def _build_topic_page(
        self,
        now: datetime,
        doc: Document,
        source_path: str,
        topic_path: str,
        chunks: list[dict[str, Any]],
    ) -> WikiPageInput:
        title = f"{doc.file_name} 主题页"
        content = build_markdown_page(
            {
                "title": title,
                "page_type": "topic",
                "status": "active",
                "source_doc_id": doc.id,
                "source_count": len(chunks),
                "updated_at": now.isoformat(),
                "tags": ["topic", "中文主题页"],
            },
            title,
            [
                (
                    "来源摘要",
                    f"本主题页来自 [{doc.file_name}]({source_path})，"
                    "由已编译来源片段自动整理，采纳后可作为一阶段 Wiki 回答素材。\n\n"
                    f"- 文档 ID：`{doc.id}`\n"
                    f"- 分块数：`{len(chunks)}`\n"
                    f"- 摘要：{self._document_summary(chunks)}",
                ),
                ("关键要点", self._build_topic_key_points(doc, chunks)),
                (
                    "后续维护",
                    "- 人工采纳后可补充定义、适用范围、例外、责任和跨页链接。\n"
                    "- 更新主题页时应保留来源链接或来源标记，方便回答回溯。",
                ),
            ],
        )
        return WikiPageInput(
            path=topic_path,
            title=title,
            page_type="topic",
            content=content,
            source_doc_id=doc.id,
            provenance={
                "compiler": "wiki",
                "source_doc_id": doc.id,
                "source_path": source_path,
                "source_count": len(chunks),
            },
        )

    def _build_topic_patch(
        self,
        now: datetime,
        doc: Document,
        source_path: str,
        topic_path: str,
        chunks: list[dict[str, Any]],
    ) -> str:
        return self._build_topic_page(
            now,
            doc,
            source_path,
            topic_path,
            chunks,
        ).content

    def _build_topic_key_points(
        self,
        doc: Document,
        chunks: list[dict[str, Any]],
    ) -> str:
        if not chunks:
            return "- 暂无可整理的分块内容。"

        items: list[str] = []
        for fallback_index, chunk in enumerate(chunks[:6]):
            chunk_index = chunk.get("chunk_index", fallback_index)
            content = self._truncate_text(
                self._chunk_content(chunk),
                max_chars=220,
            )
            items.append(
                f"- {content} [source:doc={doc.id} chunk_index={chunk_index}]"
            )
        return "\n".join(items)

    def _document_summary(self, chunks: list[dict[str, Any]]) -> str:
        for chunk in chunks:
            content = self._chunk_content(chunk)
            if content and content != "暂无分块内容。":
                return self._truncate_text(content, max_chars=220)
        return "暂无可用分块内容。"

    @staticmethod
    def _truncate_text(text: str, *, max_chars: int) -> str:
        normalized = re.sub(r"\s+", " ", text).strip()
        if len(normalized) <= max_chars:
            return normalized
        return f"{normalized[: max_chars - 3].rstrip()}..."
