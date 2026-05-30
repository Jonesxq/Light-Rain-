# Wiki-RAG Phase 1 Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Wiki-RAG foundation layer: configuration, database tables, Markdown storage, frontmatter/log/link primitives, source-page compilation, index-first page search, lint, wiki APIs, and post-ingest compilation hooks.

**Architecture:** This plan implements Phase 1 and Phase 1.5 from the approved spec. It creates a Markdown wiki per knowledge base under `storage/wiki/kb_{kb_id}`, indexes pages in MySQL, keeps derived link metadata rebuildable, and exposes basic rebuild/search/lint/page/patch APIs. Wiki-first answering and raw-RAG writeback execution are intentionally handled in a separate plan.

**Tech Stack:** FastAPI, SQLModel, Alembic, MySQL/SQLite tests, existing BM25 helper, Pydantic settings, pytest, Vue integration points left for the next frontend-focused plan.

---

## Scope Check

The approved spec covers multiple subsystems. This plan covers only independently testable foundations:

- Wiki settings
- Wiki database models and migration
- Markdown storage and rendering primitives
- Wiki page/link/patch/run CRUD
- Source page compiler
- Link extraction and lint
- Wiki page/search/lint/rebuild APIs
- Hook after completed knowledge ingestion

The following spec sections are deliberately assigned to follow-up plans:

- Wiki-only answer and raw RAG fallback orchestration
- LLM-based WikiAnswerer
- Raw RAG answer writeback evaluator
- Frontend Wiki/Patches/Lint tabs
- Assets image understanding and report/chart/slide artifacts

## File Structure

Create:

- `backend/app/core/config/modules/wiki.py` - wiki settings and validation.
- `backend/app/models/wiki.py` - SQLModel tables for pages, revisions, patches, links, runs.
- `backend/alembic/versions/h1i2j3k4l5m6_add_wiki_tables.py` - migration for wiki tables.
- `backend/app/crud/wiki.py` - database operations for wiki tables.
- `backend/app/services/wiki/__init__.py` - package exports and `wiki_service` singleton.
- `backend/app/services/wiki/types.py` - dataclasses and constants shared by wiki services.
- `backend/app/services/wiki/markdown.py` - frontmatter, slug, log entry, and section rendering helpers.
- `backend/app/services/wiki/storage.py` - path-safe Markdown file reads and atomic writes.
- `backend/app/services/wiki/links.py` - Markdown link and provenance extraction.
- `backend/app/services/wiki/lint.py` - lint checks over files, DB rows, frontmatter, index, log, links.
- `backend/app/services/wiki/compiler.py` - source/index/log compilation from completed documents.
- `backend/app/services/wiki/retriever.py` - index-first BM25 page search.
- `backend/app/services/wiki/service.py` - facade used by routes and ingestion hook.
- `backend/app/routers/v1/wiki.py` - wiki API routes.
- `backend/tests/unit/test_wiki_settings.py`
- `backend/tests/unit/test_wiki_storage.py`
- `backend/tests/unit/test_wiki_markdown.py`
- `backend/tests/unit/test_wiki_links_lint.py`
- `backend/tests/unit/test_wiki_compiler.py`
- `backend/tests/unit/test_wiki_retriever.py`
- `backend/tests/unit/test_wiki_ingest_hook.py`

Modify:

- `backend/app/core/config/settings.py` - expose `settings.wiki`.
- `backend/app/models/__init__.py` - import wiki models for metadata registration.
- `backend/alembic/env.py` - import wiki models for autogenerate visibility.
- `backend/tests/conftest.py` - import wiki models before `SQLModel.metadata.create_all`.
- `backend/app/routers/v1/__init__.py` - export `wiki_router`.
- `backend/app/main.py` - include `wiki_router`.
- `backend/app/services/knowledge/ingest.py` - call wiki compile hook after document completion.

## Task 1: Wiki Settings

**Files:**
- Create: `backend/app/core/config/modules/wiki.py`
- Modify: `backend/app/core/config/settings.py`
- Test: `backend/tests/unit/test_wiki_settings.py`

- [ ] **Step 1: Write the failing settings tests**

Create `backend/tests/unit/test_wiki_settings.py`:

```python
from app.core.config.modules.wiki import WikiSettings


def test_wiki_settings_defaults_match_phase1_plan():
    settings = WikiSettings()

    assert settings.WIKI_RAG_ENABLED is True
    assert settings.WIKI_WRITEBACK_MODE == "manual"
    assert settings.WIKI_INGEST_MODE == "auto"
    assert settings.WIKI_ANSWER_CONFIDENCE_THRESHOLD == 0.72
    assert settings.WIKI_RETRIEVER_TOP_K == 5
    assert settings.WIKI_STORAGE_DIR == "storage/wiki"
    assert settings.WIKI_MAX_PAGE_CHARS == 12000
    assert settings.WIKI_PATCH_CONFIDENCE_THRESHOLD == 0.70
    assert settings.WIKI_AUTO_COMPILE_ON_INGEST is True


def test_wiki_settings_reject_invalid_modes():
    settings = WikiSettings(
        WIKI_WRITEBACK_MODE="surprise",
        WIKI_INGEST_MODE="mystery",
    )

    assert settings.WIKI_WRITEBACK_MODE == "manual"
    assert settings.WIKI_INGEST_MODE == "auto"


def test_wiki_settings_clamps_numeric_values():
    settings = WikiSettings(
        WIKI_ANSWER_CONFIDENCE_THRESHOLD=5,
        WIKI_RETRIEVER_TOP_K=0,
        WIKI_MAX_PAGE_CHARS=10,
        WIKI_PATCH_CONFIDENCE_THRESHOLD=-1,
    )

    assert settings.WIKI_ANSWER_CONFIDENCE_THRESHOLD == 0.72
    assert settings.WIKI_RETRIEVER_TOP_K == 5
    assert settings.WIKI_MAX_PAGE_CHARS == 12000
    assert settings.WIKI_PATCH_CONFIDENCE_THRESHOLD == 0.70
```

- [ ] **Step 2: Run the settings tests and verify they fail**

Run:

```powershell
uv run --project backend pytest backend/tests/unit/test_wiki_settings.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.config.modules.wiki'`.

- [ ] **Step 3: Create the wiki settings module**

Create `backend/app/core/config/modules/wiki.py`:

```python
"""Wiki-RAG configuration module."""

from __future__ import annotations

import logging

from pydantic import Field, field_validator

from app.core.config.base import EnvBaseSettings

logger = logging.getLogger(__name__)


class WikiSettings(EnvBaseSettings):
    """Settings for the wiki-first RAG foundation layer."""

    WIKI_RAG_ENABLED: bool = Field(default=True, description="Enable wiki-first RAG")
    WIKI_WRITEBACK_MODE: str = Field(default="manual", description="manual, auto_low_risk, disabled")
    WIKI_INGEST_MODE: str = Field(default="auto", description="auto, pending_review, assisted")
    WIKI_ANSWER_CONFIDENCE_THRESHOLD: float = Field(default=0.72, description="Wiki answer threshold")
    WIKI_RETRIEVER_TOP_K: int = Field(default=5, description="Wiki page retrieval count")
    WIKI_STORAGE_DIR: str = Field(default="storage/wiki", description="Wiki Markdown root")
    WIKI_MAX_PAGE_CHARS: int = Field(default=12000, description="Maximum page chars loaded into prompts/search")
    WIKI_PATCH_CONFIDENCE_THRESHOLD: float = Field(default=0.70, description="Patch proposal threshold")
    WIKI_AUTO_COMPILE_ON_INGEST: bool = Field(default=True, description="Compile wiki after document ingest")

    @field_validator("WIKI_WRITEBACK_MODE", mode="before")
    @classmethod
    def validate_writeback_mode(cls, value):
        allowed = {"manual", "auto_low_risk", "disabled"}
        if value in allowed:
            return value
        logger.warning("Invalid WIKI_WRITEBACK_MODE=%r, using manual", value)
        return "manual"

    @field_validator("WIKI_INGEST_MODE", mode="before")
    @classmethod
    def validate_ingest_mode(cls, value):
        allowed = {"auto", "pending_review", "assisted"}
        if value in allowed:
            return value
        logger.warning("Invalid WIKI_INGEST_MODE=%r, using auto", value)
        return "auto"

    @field_validator("WIKI_ANSWER_CONFIDENCE_THRESHOLD", "WIKI_PATCH_CONFIDENCE_THRESHOLD", mode="before")
    @classmethod
    def validate_confidence(cls, value):
        try:
            parsed = float(value)
            if 0.0 <= parsed <= 1.0:
                return parsed
        except (TypeError, ValueError):
            pass
        default = 0.72 if value == "WIKI_ANSWER_CONFIDENCE_THRESHOLD" else 0.70
        logger.warning("Invalid wiki confidence value=%r, using default", value)
        return default

    @field_validator("WIKI_RETRIEVER_TOP_K", mode="before")
    @classmethod
    def validate_top_k(cls, value):
        try:
            parsed = int(value)
            if 1 <= parsed <= 20:
                return parsed
        except (TypeError, ValueError):
            pass
        logger.warning("Invalid WIKI_RETRIEVER_TOP_K=%r, using 5", value)
        return 5

    @field_validator("WIKI_MAX_PAGE_CHARS", mode="before")
    @classmethod
    def validate_max_page_chars(cls, value):
        try:
            parsed = int(value)
            if 1000 <= parsed <= 200000:
                return parsed
        except (TypeError, ValueError):
            pass
        logger.warning("Invalid WIKI_MAX_PAGE_CHARS=%r, using 12000", value)
        return 12000
```

- [ ] **Step 4: Fix the confidence validator default bug**

Replace the shared confidence validator in `backend/app/core/config/modules/wiki.py` with two explicit validators:

```python
    @field_validator("WIKI_ANSWER_CONFIDENCE_THRESHOLD", mode="before")
    @classmethod
    def validate_answer_confidence(cls, value):
        try:
            parsed = float(value)
            if 0.0 <= parsed <= 1.0:
                return parsed
        except (TypeError, ValueError):
            pass
        logger.warning("Invalid WIKI_ANSWER_CONFIDENCE_THRESHOLD=%r, using 0.72", value)
        return 0.72

    @field_validator("WIKI_PATCH_CONFIDENCE_THRESHOLD", mode="before")
    @classmethod
    def validate_patch_confidence(cls, value):
        try:
            parsed = float(value)
            if 0.0 <= parsed <= 1.0:
                return parsed
        except (TypeError, ValueError):
            pass
        logger.warning("Invalid WIKI_PATCH_CONFIDENCE_THRESHOLD=%r, using 0.70", value)
        return 0.70
```

Remove the earlier shared `validate_confidence` method.

- [ ] **Step 5: Expose `settings.wiki`**

Modify `backend/app/core/config/settings.py`.

Add import:

```python
from app.core.config.modules.wiki import WikiSettings
```

Add cached property inside `Settings`:

```python
    @cached_property
    def wiki(self) -> WikiSettings:
        """Wiki-RAG settings."""
        return WikiSettings()
```

- [ ] **Step 6: Run settings tests**

Run:

```powershell
uv run --project backend pytest backend/tests/unit/test_wiki_settings.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit settings**

```powershell
git add backend/app/core/config/modules/wiki.py backend/app/core/config/settings.py backend/tests/unit/test_wiki_settings.py
git commit -m "feat: add wiki rag settings"
```

## Task 2: Wiki Database Models and Migration

**Files:**
- Create: `backend/app/models/wiki.py`
- Create: `backend/alembic/versions/h1i2j3k4l5m6_add_wiki_tables.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/alembic/env.py`
- Modify: `backend/tests/conftest.py`
- Test: `backend/tests/unit/test_wiki_models.py`

- [ ] **Step 1: Write failing model metadata tests**

Create `backend/tests/unit/test_wiki_models.py`:

```python
from sqlmodel import SQLModel


def test_wiki_tables_are_registered_in_metadata():
    import app.models.wiki  # noqa: F401

    table_names = set(SQLModel.metadata.tables.keys())

    assert "wiki_pages" in table_names
    assert "wiki_page_revisions" in table_names
    assert "wiki_patches" in table_names
    assert "wiki_links" in table_names
    assert "wiki_runs" in table_names
```

- [ ] **Step 2: Run model metadata test and verify it fails**

Run:

```powershell
uv run --project backend pytest backend/tests/unit/test_wiki_models.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.models.wiki'`.

- [ ] **Step 3: Create wiki models**

Create `backend/app/models/wiki.py`:

```python
"""Wiki-RAG database models."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Column, ForeignKey, Index, Text
from sqlmodel import Field, SQLModel


class WikiPage(SQLModel, table=True):
    """Indexed Markdown wiki page."""

    __tablename__ = "wiki_pages"
    __table_args__ = (
        Index("ix_wiki_pages_kb_path", "kb_id", "path", unique=True),
        Index("ix_wiki_pages_kb_type", "kb_id", "page_type"),
        Index("ix_wiki_pages_kb_status", "kb_id", "status"),
        Index("ix_wiki_pages_source_doc", "source_doc_id"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    kb_id: int = Field(foreign_key="knowledge_bases.id", index=True)
    path: str = Field(max_length=512)
    title: str = Field(max_length=255)
    page_type: str = Field(max_length=50)
    status: str = Field(default="active", max_length=30)
    content_hash: str = Field(default="", max_length=128)
    source_doc_id: Optional[int] = Field(
        default=None,
        sa_column=Column(ForeignKey("kb_documents.id", ondelete="SET NULL"), nullable=True),
    )
    provenance: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class WikiPageRevision(SQLModel, table=True):
    """Snapshot of a wiki page after a change."""

    __tablename__ = "wiki_page_revisions"
    __table_args__ = (
        Index("ix_wiki_page_revisions_page_id", "page_id"),
        Index("ix_wiki_page_revisions_kb_path", "kb_id", "path"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    page_id: Optional[int] = Field(
        default=None,
        sa_column=Column(ForeignKey("wiki_pages.id", ondelete="SET NULL"), nullable=True),
    )
    kb_id: int = Field(foreign_key="knowledge_bases.id", index=True)
    path: str = Field(max_length=512)
    content_hash: str = Field(max_length=128)
    content_snapshot: str = Field(sa_column=Column(Text, nullable=False))
    change_reason: str = Field(max_length=50)
    provenance: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class WikiPatch(SQLModel, table=True):
    """Reviewable wiki write proposal."""

    __tablename__ = "wiki_patches"
    __table_args__ = (
        Index("ix_wiki_patches_kb_status", "kb_id", "status"),
        Index("ix_wiki_patches_target", "kb_id", "target_path"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    kb_id: int = Field(foreign_key="knowledge_bases.id", index=True)
    page_id: Optional[int] = Field(
        default=None,
        sa_column=Column(ForeignKey("wiki_pages.id", ondelete="SET NULL"), nullable=True),
    )
    target_path: str = Field(max_length=512)
    operation: str = Field(max_length=50)
    status: str = Field(default="pending", max_length=30, index=True)
    question: Optional[str] = Field(default=None, sa_column=Column(Text))
    answer: Optional[str] = Field(default=None, sa_column=Column(Text))
    patch_markdown: str = Field(sa_column=Column(Text, nullable=False))
    rationale: Optional[str] = Field(default=None, sa_column=Column(Text))
    confidence: float = Field(default=0.0)
    provenance: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_by_message_id: Optional[int] = Field(
        default=None,
        sa_column=Column(ForeignKey("chat_messages.id", ondelete="SET NULL"), nullable=True),
    )
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    applied_at: Optional[datetime] = Field(default=None)
    rejected_at: Optional[datetime] = Field(default=None)


class WikiLink(SQLModel, table=True):
    """Derived link or backlink between wiki pages."""

    __tablename__ = "wiki_links"
    __table_args__ = (
        Index("ix_wiki_links_from", "kb_id", "from_path"),
        Index("ix_wiki_links_to", "kb_id", "to_path"),
        Index("ix_wiki_links_type", "kb_id", "link_type"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    kb_id: int = Field(foreign_key="knowledge_bases.id", index=True)
    from_page_id: Optional[int] = Field(
        default=None,
        sa_column=Column(ForeignKey("wiki_pages.id", ondelete="CASCADE"), nullable=True),
    )
    from_path: str = Field(max_length=512)
    to_page_id: Optional[int] = Field(
        default=None,
        sa_column=Column(ForeignKey("wiki_pages.id", ondelete="SET NULL"), nullable=True),
    )
    to_path: str = Field(max_length=512)
    link_type: str = Field(default="related_to", max_length=50)
    anchor_text: Optional[str] = Field(default=None, max_length=255)
    provenance: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class WikiRun(SQLModel, table=True):
    """Wiki maintenance job record."""

    __tablename__ = "wiki_runs"
    __table_args__ = (
        Index("ix_wiki_runs_kb_type", "kb_id", "run_type"),
        Index("ix_wiki_runs_kb_status", "kb_id", "status"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    kb_id: int = Field(foreign_key="knowledge_bases.id", index=True)
    doc_id: Optional[int] = Field(
        default=None,
        sa_column=Column(ForeignKey("kb_documents.id", ondelete="SET NULL"), nullable=True),
    )
    run_type: str = Field(max_length=50)
    status: str = Field(max_length=30)
    metrics: dict = Field(default_factory=dict, sa_column=Column(JSON))
    error_msg: Optional[str] = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    finished_at: Optional[datetime] = Field(default=None)
```

- [ ] **Step 4: Register wiki models**

Modify `backend/app/models/__init__.py`:

```python
"""数据模型模块 - 定义数据库表结构和关系"""

from app.models.wiki import WikiLink, WikiPage, WikiPageRevision, WikiPatch, WikiRun

__all__ = [
    "WikiLink",
    "WikiPage",
    "WikiPageRevision",
    "WikiPatch",
    "WikiRun",
]
```

Modify `backend/alembic/env.py` near the existing model imports:

```python
from app.models.knowledge import KnowledgeBase, Document, DocumentChunk
from app.models.chat import ChatMessage, ChatSession, ChatPromptSnapshot, ChatConversationSummary
from app.models.wiki import WikiLink, WikiPage, WikiPageRevision, WikiPatch, WikiRun
```

Modify `backend/tests/conftest.py` inside `test_engine()` after the existing user import:

```python
    from app.models.knowledge import KnowledgeBase, Document, DocumentChunk  # noqa: F401
    from app.models.chat import ChatMessage, ChatSession, ChatPromptSnapshot, ChatConversationSummary  # noqa: F401
    from app.models.wiki import WikiLink, WikiPage, WikiPageRevision, WikiPatch, WikiRun  # noqa: F401
```

- [ ] **Step 5: Add Alembic migration**

Create `backend/alembic/versions/h1i2j3k4l5m6_add_wiki_tables.py`:

```python
"""Add wiki tables

Revision ID: h1i2j3k4l5m6
Revises: g5h6i7j8k9l0
Create Date: 2026-05-30 00:00:00.000000+00:00
"""

from alembic import op
import sqlalchemy as sa

revision = "h1i2j3k4l5m6"
down_revision = "g5h6i7j8k9l0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wiki_pages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("kb_id", sa.Integer(), nullable=False),
        sa.Column("path", sa.String(length=512), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("page_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="active"),
        sa.Column("content_hash", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("source_doc_id", sa.Integer(), nullable=True),
        sa.Column("provenance", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["kb_id"], ["knowledge_bases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_doc_id"], ["kb_documents.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_wiki_pages_kb_id", "wiki_pages", ["kb_id"])
    op.create_index("ix_wiki_pages_kb_path", "wiki_pages", ["kb_id", "path"], unique=True)
    op.create_index("ix_wiki_pages_kb_type", "wiki_pages", ["kb_id", "page_type"])
    op.create_index("ix_wiki_pages_kb_status", "wiki_pages", ["kb_id", "status"])
    op.create_index("ix_wiki_pages_source_doc", "wiki_pages", ["source_doc_id"])
    op.create_index("ix_wiki_pages_updated_at", "wiki_pages", ["updated_at"])

    op.create_table(
        "wiki_page_revisions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("page_id", sa.Integer(), nullable=True),
        sa.Column("kb_id", sa.Integer(), nullable=False),
        sa.Column("path", sa.String(length=512), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("content_snapshot", sa.Text(), nullable=False),
        sa.Column("change_reason", sa.String(length=50), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["page_id"], ["wiki_pages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["kb_id"], ["knowledge_bases.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_wiki_page_revisions_page_id", "wiki_page_revisions", ["page_id"])
    op.create_index("ix_wiki_page_revisions_kb_id", "wiki_page_revisions", ["kb_id"])
    op.create_index("ix_wiki_page_revisions_kb_path", "wiki_page_revisions", ["kb_id", "path"])
    op.create_index("ix_wiki_page_revisions_created_at", "wiki_page_revisions", ["created_at"])

    op.create_table(
        "wiki_patches",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("kb_id", sa.Integer(), nullable=False),
        sa.Column("page_id", sa.Integer(), nullable=True),
        sa.Column("target_path", sa.String(length=512), nullable=False),
        sa.Column("operation", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("question", sa.Text(), nullable=True),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("patch_markdown", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("provenance", sa.JSON(), nullable=True),
        sa.Column("created_by_message_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("applied_at", sa.DateTime(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["kb_id"], ["knowledge_bases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["page_id"], ["wiki_pages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_message_id"], ["chat_messages.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_wiki_patches_kb_id", "wiki_patches", ["kb_id"])
    op.create_index("ix_wiki_patches_status", "wiki_patches", ["status"])
    op.create_index("ix_wiki_patches_created_at", "wiki_patches", ["created_at"])
    op.create_index("ix_wiki_patches_kb_status", "wiki_patches", ["kb_id", "status"])
    op.create_index("ix_wiki_patches_target", "wiki_patches", ["kb_id", "target_path"])

    op.create_table(
        "wiki_links",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("kb_id", sa.Integer(), nullable=False),
        sa.Column("from_page_id", sa.Integer(), nullable=True),
        sa.Column("from_path", sa.String(length=512), nullable=False),
        sa.Column("to_page_id", sa.Integer(), nullable=True),
        sa.Column("to_path", sa.String(length=512), nullable=False),
        sa.Column("link_type", sa.String(length=50), nullable=False, server_default="related_to"),
        sa.Column("anchor_text", sa.String(length=255), nullable=True),
        sa.Column("provenance", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["kb_id"], ["knowledge_bases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["from_page_id"], ["wiki_pages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_page_id"], ["wiki_pages.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_wiki_links_kb_id", "wiki_links", ["kb_id"])
    op.create_index("ix_wiki_links_created_at", "wiki_links", ["created_at"])
    op.create_index("ix_wiki_links_from", "wiki_links", ["kb_id", "from_path"])
    op.create_index("ix_wiki_links_to", "wiki_links", ["kb_id", "to_path"])
    op.create_index("ix_wiki_links_type", "wiki_links", ["kb_id", "link_type"])

    op.create_table(
        "wiki_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("kb_id", sa.Integer(), nullable=False),
        sa.Column("doc_id", sa.Integer(), nullable=True),
        sa.Column("run_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("error_msg", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["kb_id"], ["knowledge_bases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["doc_id"], ["kb_documents.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_wiki_runs_kb_id", "wiki_runs", ["kb_id"])
    op.create_index("ix_wiki_runs_created_at", "wiki_runs", ["created_at"])
    op.create_index("ix_wiki_runs_kb_type", "wiki_runs", ["kb_id", "run_type"])
    op.create_index("ix_wiki_runs_kb_status", "wiki_runs", ["kb_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_wiki_runs_kb_status", table_name="wiki_runs")
    op.drop_index("ix_wiki_runs_kb_type", table_name="wiki_runs")
    op.drop_index("ix_wiki_runs_created_at", table_name="wiki_runs")
    op.drop_index("ix_wiki_runs_kb_id", table_name="wiki_runs")
    op.drop_table("wiki_runs")

    op.drop_index("ix_wiki_links_type", table_name="wiki_links")
    op.drop_index("ix_wiki_links_to", table_name="wiki_links")
    op.drop_index("ix_wiki_links_from", table_name="wiki_links")
    op.drop_index("ix_wiki_links_created_at", table_name="wiki_links")
    op.drop_index("ix_wiki_links_kb_id", table_name="wiki_links")
    op.drop_table("wiki_links")

    op.drop_index("ix_wiki_patches_target", table_name="wiki_patches")
    op.drop_index("ix_wiki_patches_kb_status", table_name="wiki_patches")
    op.drop_index("ix_wiki_patches_created_at", table_name="wiki_patches")
    op.drop_index("ix_wiki_patches_status", table_name="wiki_patches")
    op.drop_index("ix_wiki_patches_kb_id", table_name="wiki_patches")
    op.drop_table("wiki_patches")

    op.drop_index("ix_wiki_page_revisions_created_at", table_name="wiki_page_revisions")
    op.drop_index("ix_wiki_page_revisions_kb_path", table_name="wiki_page_revisions")
    op.drop_index("ix_wiki_page_revisions_kb_id", table_name="wiki_page_revisions")
    op.drop_index("ix_wiki_page_revisions_page_id", table_name="wiki_page_revisions")
    op.drop_table("wiki_page_revisions")

    op.drop_index("ix_wiki_pages_updated_at", table_name="wiki_pages")
    op.drop_index("ix_wiki_pages_source_doc", table_name="wiki_pages")
    op.drop_index("ix_wiki_pages_kb_status", table_name="wiki_pages")
    op.drop_index("ix_wiki_pages_kb_type", table_name="wiki_pages")
    op.drop_index("ix_wiki_pages_kb_path", table_name="wiki_pages")
    op.drop_index("ix_wiki_pages_kb_id", table_name="wiki_pages")
    op.drop_table("wiki_pages")
```

- [ ] **Step 6: Run model test**

Run:

```powershell
uv run --project backend pytest backend/tests/unit/test_wiki_models.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit models and migration**

```powershell
git add backend/app/models/wiki.py backend/app/models/__init__.py backend/alembic/env.py backend/tests/conftest.py backend/alembic/versions/h1i2j3k4l5m6_add_wiki_tables.py backend/tests/unit/test_wiki_models.py
git commit -m "feat: add wiki database models"
```

## Task 3: Wiki Types and Markdown Primitives

**Files:**
- Create: `backend/app/services/wiki/types.py`
- Create: `backend/app/services/wiki/markdown.py`
- Create: `backend/app/services/wiki/__init__.py`
- Test: `backend/tests/unit/test_wiki_markdown.py`

- [ ] **Step 1: Write failing markdown tests**

Create `backend/tests/unit/test_wiki_markdown.py`:

```python
from datetime import datetime

from app.services.wiki.markdown import (
    build_frontmatter,
    build_log_heading,
    extract_frontmatter,
    slugify_title,
)


def test_slugify_title_keeps_ascii_and_doc_id_prefix():
    assert slugify_title("API 文档 v2", fallback="document", prefix="12") == "12-api-v2"
    assert slugify_title("   ", fallback="Document Name", prefix="7") == "7-document-name"


def test_frontmatter_roundtrip_for_simple_values():
    markdown = build_frontmatter(
        {
            "title": "API Doc",
            "page_type": "source",
            "status": "active",
            "tags": ["source", "api"],
            "doc_id": 12,
        }
    ) + "\n# API Doc\nBody"

    frontmatter, body = extract_frontmatter(markdown)

    assert frontmatter["title"] == "API Doc"
    assert frontmatter["page_type"] == "source"
    assert frontmatter["tags"] == ["source", "api"]
    assert frontmatter["doc_id"] == 12
    assert body == "# API Doc\nBody"


def test_log_heading_is_parseable_shape():
    heading = build_log_heading(
        event_time=datetime(2026, 5, 30, 9, 15),
        event_type="ingest",
        parts=["doc_id=12", "API Doc"],
    )

    assert heading == "## [2026-05-30 09:15] ingest | doc_id=12 | API Doc"
```

- [ ] **Step 2: Run markdown tests and verify failure**

Run:

```powershell
uv run --project backend pytest backend/tests/unit/test_wiki_markdown.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.wiki'`.

- [ ] **Step 3: Add wiki service package exports**

Create `backend/app/services/wiki/__init__.py`:

```python
"""Wiki-RAG service package."""

from app.services.wiki.service import WikiService

wiki_service = WikiService()

__all__ = ["WikiService", "wiki_service"]
```

Create a temporary `backend/app/services/wiki/service.py` so imports resolve:

```python
"""Wiki-RAG facade service."""

from __future__ import annotations


class WikiService:
    """Facade for Wiki-RAG operations."""

    def __init__(self):
        self.ready = True
```

- [ ] **Step 4: Add types**

Create `backend/app/services/wiki/types.py`:

```python
"""Shared Wiki-RAG types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


PAGE_INDEX = "index.md"
PAGE_SCHEMA = "schema.md"
PAGE_LOG = "log.md"
PAGE_FAQ = "faq.md"
PAGE_OPEN_QUESTIONS = "open_questions.md"
PAGE_CONTRADICTIONS = "contradictions.md"

PAGE_TYPES = {
    "index",
    "schema",
    "log",
    "source",
    "topic",
    "entity",
    "faq",
    "open_questions",
    "contradictions",
    "patch",
}

PATCH_OPERATIONS = {"create", "append", "replace_section"}
PATCH_STATUSES = {"pending", "applied", "rejected", "failed"}
LINK_TYPES = {"related_to", "cites", "defines", "answers", "contradicts", "supersedes", "mentions"}


@dataclass
class WikiPageInput:
    path: str
    title: str
    page_type: str
    content: str
    source_doc_id: Optional[int] = None
    provenance: dict = field(default_factory=dict)


@dataclass
class WikiCompileResult:
    kb_id: int
    doc_id: Optional[int]
    pages_changed: int
    patches_created: int
    warnings: list[str] = field(default_factory=list)


@dataclass
class WikiLintWarning:
    code: str
    message: str
    path: Optional[str] = None
    severity: str = "warning"


@dataclass
class WikiSearchHit:
    page_id: Optional[int]
    path: str
    title: str
    page_type: str
    score: float
    snippet: str


@dataclass
class WikiLogEvent:
    event_time: datetime
    event_type: str
    parts: list[str]
```

- [ ] **Step 5: Add Markdown helper implementation**

Create `backend/app/services/wiki/markdown.py`:

```python
"""Markdown helpers for Wiki-RAG pages."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any


_FRONTMATTER_RE = re.compile(r"^---\n(?P<body>.*?)\n---\n?", re.DOTALL)


def slugify_title(title: str, *, fallback: str = "page", prefix: str | None = None) -> str:
    raw = (title or "").strip() or fallback
    normalized = unicodedata.normalize("NFKD", raw)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text).strip("-").lower()
    if not slug:
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", fallback).strip("-").lower() or "page"
    if prefix:
        return f"{prefix}-{slug}"
    return slug


def _format_frontmatter_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(str(item) for item in value) + "]"
    text = str(value).replace('"', '\\"')
    if any(ch in text for ch in [":", "#", "[", "]", "{", "}", ","]):
        return f'"{text}"'
    return text


def build_frontmatter(values: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in values.items():
        if value is None:
            continue
        lines.append(f"{key}: {_format_frontmatter_value(value)}")
    lines.append("---")
    return "\n".join(lines)


def _parse_scalar(value: str) -> Any:
    raw = value.strip()
    if raw == "true":
        return True
    if raw == "false":
        return False
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [part.strip().strip('"') for part in inner.split(",")]
    if raw.isdigit():
        return int(raw)
    try:
        return float(raw)
    except ValueError:
        return raw.strip('"')


def extract_frontmatter(markdown: str) -> tuple[dict[str, Any], str]:
    match = _FRONTMATTER_RE.match(markdown or "")
    if not match:
        return {}, markdown or ""

    data: dict[str, Any] = {}
    for line in match.group("body").splitlines():
        if not line.strip() or ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = _parse_scalar(value)
    body = (markdown or "")[match.end():]
    return data, body.strip()


def build_log_heading(event_time: datetime, event_type: str, parts: list[str]) -> str:
    safe_type = re.sub(r"[^a-zA-Z0-9_-]+", "_", event_type.strip())
    suffix = " | ".join(part.strip() for part in parts if part and part.strip())
    timestamp = event_time.strftime("%Y-%m-%d %H:%M")
    if suffix:
        return f"## [{timestamp}] {safe_type} | {suffix}"
    return f"## [{timestamp}] {safe_type}"


def build_markdown_page(frontmatter: dict[str, Any], title: str, sections: list[tuple[str, str]]) -> str:
    lines = [build_frontmatter(frontmatter), "", f"# {title.strip()}", ""]
    for heading, body in sections:
        lines.extend([f"## {heading.strip()}", "", (body or "").strip(), ""])
    return "\n".join(lines).rstrip() + "\n"
```

- [ ] **Step 6: Run markdown tests**

Run:

```powershell
uv run --project backend pytest backend/tests/unit/test_wiki_markdown.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit types and markdown helpers**

```powershell
git add backend/app/services/wiki/__init__.py backend/app/services/wiki/service.py backend/app/services/wiki/types.py backend/app/services/wiki/markdown.py backend/tests/unit/test_wiki_markdown.py
git commit -m "feat: add wiki markdown primitives"
```

## Task 4: Path-Safe Wiki Storage

**Files:**
- Create: `backend/app/services/wiki/storage.py`
- Test: `backend/tests/unit/test_wiki_storage.py`

- [ ] **Step 1: Write failing storage tests**

Create `backend/tests/unit/test_wiki_storage.py`:

```python
from pathlib import Path

import pytest

from app.services.wiki.storage import WikiStorage


def test_storage_rejects_path_traversal(tmp_path: Path):
    storage = WikiStorage(root_dir=tmp_path)

    with pytest.raises(ValueError):
        storage.resolve_page_path(1, "../secret.md")

    with pytest.raises(ValueError):
        storage.resolve_page_path(1, "C:/secret.md")


def test_storage_writes_and_reads_page(tmp_path: Path):
    storage = WikiStorage(root_dir=tmp_path)

    storage.write_page(7, "sources/12-api.md", "# API\nBody")

    assert storage.read_page(7, "sources/12-api.md") == "# API\nBody"
    assert (tmp_path / "kb_7" / "sources" / "12-api.md").exists()


def test_storage_hash_changes_with_content(tmp_path: Path):
    storage = WikiStorage(root_dir=tmp_path)

    first = storage.content_hash("alpha")
    second = storage.content_hash("beta")

    assert first != second
    assert len(first) == 64
```

- [ ] **Step 2: Run storage tests and verify failure**

Run:

```powershell
uv run --project backend pytest backend/tests/unit/test_wiki_storage.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.wiki.storage'`.

- [ ] **Step 3: Implement storage**

Create `backend/app/services/wiki/storage.py`:

```python
"""Path-safe Markdown storage for Wiki-RAG."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath

from app.core.config.settings import settings


class WikiStorage:
    """Read and write wiki pages under a per-knowledge-base root."""

    def __init__(self, root_dir: str | Path | None = None):
        configured = root_dir if root_dir is not None else settings.wiki.WIKI_STORAGE_DIR
        self.root_dir = Path(configured).resolve()

    def kb_root(self, kb_id: int) -> Path:
        return self.root_dir / f"kb_{int(kb_id)}"

    def normalize_page_path(self, page_path: str) -> str:
        raw = (page_path or "").strip().replace("\\", "/")
        if not raw:
            raise ValueError("Wiki page path is empty")
        pure = PurePosixPath(raw)
        if pure.is_absolute():
            raise ValueError("Wiki page path must be relative")
        if ":" in raw:
            raise ValueError("Wiki page path must not contain drive prefixes")
        if any(part in ("", ".", "..") for part in pure.parts):
            raise ValueError("Wiki page path contains unsafe segments")
        normalized = pure.as_posix()
        if not normalized.endswith(".md"):
            raise ValueError("Wiki page path must end with .md")
        return normalized

    def resolve_page_path(self, kb_id: int, page_path: str) -> Path:
        normalized = self.normalize_page_path(page_path)
        root = self.kb_root(kb_id).resolve()
        resolved = (root / normalized).resolve()
        if os.path.commonpath([str(root), str(resolved)]) != str(root):
            raise ValueError("Wiki page path escapes wiki root")
        return resolved

    def read_page(self, kb_id: int, page_path: str) -> str:
        path = self.resolve_page_path(kb_id, page_path)
        return path.read_text(encoding="utf-8")

    def page_exists(self, kb_id: int, page_path: str) -> bool:
        return self.resolve_page_path(kb_id, page_path).exists()

    def write_page(self, kb_id: int, page_path: str, content: str) -> None:
        path = self.resolve_page_path(kb_id, page_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f"{path.name}.tmp")
        try:
            tmp_path.write_text(content, encoding="utf-8")
            os.replace(tmp_path, path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def list_markdown_pages(self, kb_id: int) -> list[str]:
        root = self.kb_root(kb_id)
        if not root.exists():
            return []
        pages = []
        for path in root.rglob("*.md"):
            pages.append(path.relative_to(root).as_posix())
        return sorted(pages)

    def content_hash(self, content: str) -> str:
        return hashlib.sha256((content or "").encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Run storage tests**

Run:

```powershell
uv run --project backend pytest backend/tests/unit/test_wiki_storage.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit storage**

```powershell
git add backend/app/services/wiki/storage.py backend/tests/unit/test_wiki_storage.py
git commit -m "feat: add wiki markdown storage"
```

## Task 5: Wiki CRUD

**Files:**
- Create: `backend/app/crud/wiki.py`
- Test: extend `backend/tests/unit/test_wiki_models.py`

- [ ] **Step 1: Add failing CRUD test**

Append to `backend/tests/unit/test_wiki_models.py`:

```python
import pytest

from app.crud.wiki import wiki_crud
from app.models.knowledge import KnowledgeBase


@pytest.mark.asyncio
async def test_upsert_page_and_revision_roundtrip(db_session):
    kb = KnowledgeBase(user_id=1, name="KB")
    db_session.add(kb)
    await db_session.commit()
    await db_session.refresh(kb)

    page = await wiki_crud.upsert_page(
        db_session,
        kb_id=kb.id,
        path="index.md",
        title="Index",
        page_type="index",
        content_hash="abc",
        provenance={"kind": "test"},
    )
    await wiki_crud.create_revision(
        db_session,
        page_id=page.id,
        kb_id=kb.id,
        path=page.path,
        content_hash="abc",
        content_snapshot="# Index",
        change_reason="system",
        provenance={"kind": "test"},
    )

    loaded = await wiki_crud.get_page_by_path(db_session, kb.id, "index.md")
    revisions = await wiki_crud.list_revisions(db_session, page.id)

    assert loaded.id == page.id
    assert revisions[0].content_snapshot == "# Index"
```

- [ ] **Step 2: Run CRUD test and verify failure**

Run:

```powershell
uv run --project backend pytest backend/tests/unit/test_wiki_models.py::test_upsert_page_and_revision_roundtrip -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.crud.wiki'`.

- [ ] **Step 3: Implement CRUD**

Create `backend/app/crud/wiki.py`:

```python
"""CRUD helpers for Wiki-RAG tables."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.wiki import WikiLink, WikiPage, WikiPageRevision, WikiPatch, WikiRun


class WikiCRUD:
    """Database operations for wiki pages, revisions, patches, links, and runs."""

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
        row = await self.get_page_by_path(db, kb_id, path)
        now = datetime.utcnow()
        if row:
            row.title = title
            row.page_type = page_type
            row.status = status
            row.content_hash = content_hash
            row.source_doc_id = source_doc_id
            row.provenance = provenance or {}
            row.updated_at = now
        else:
            row = WikiPage(
                kb_id=kb_id,
                path=path,
                title=title,
                page_type=page_type,
                status=status,
                content_hash=content_hash,
                source_doc_id=source_doc_id,
                provenance=provenance or {},
                created_at=now,
                updated_at=now,
            )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row

    async def get_page_by_path(self, db: AsyncSession, kb_id: int, path: str) -> Optional[WikiPage]:
        result = await db.execute(
            select(WikiPage).where(WikiPage.kb_id == kb_id, WikiPage.path == path)
        )
        return result.scalar_one_or_none()

    async def get_page(self, db: AsyncSession, kb_id: int, page_id: int) -> Optional[WikiPage]:
        result = await db.execute(
            select(WikiPage).where(WikiPage.kb_id == kb_id, WikiPage.id == page_id)
        )
        return result.scalar_one_or_none()

    async def list_pages(self, db: AsyncSession, kb_id: int) -> list[WikiPage]:
        result = await db.execute(
            select(WikiPage).where(WikiPage.kb_id == kb_id, WikiPage.status != "deleted").order_by(WikiPage.path.asc())
        )
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
        row = WikiPageRevision(
            page_id=page_id,
            kb_id=kb_id,
            path=path,
            content_hash=content_hash,
            content_snapshot=content_snapshot,
            change_reason=change_reason,
            provenance=provenance or {},
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row

    async def list_revisions(self, db: AsyncSession, page_id: int) -> list[WikiPageRevision]:
        result = await db.execute(
            select(WikiPageRevision)
            .where(WikiPageRevision.page_id == page_id)
            .order_by(WikiPageRevision.created_at.desc())
        )
        return list(result.scalars().all())

    async def create_patch(
        self,
        db: AsyncSession,
        *,
        kb_id: int,
        target_path: str,
        operation: str,
        patch_markdown: str,
        question: Optional[str] = None,
        answer: Optional[str] = None,
        rationale: Optional[str] = None,
        confidence: float = 0.0,
        provenance: Optional[dict] = None,
        page_id: Optional[int] = None,
        created_by_message_id: Optional[int] = None,
    ) -> WikiPatch:
        row = WikiPatch(
            kb_id=kb_id,
            page_id=page_id,
            target_path=target_path,
            operation=operation,
            status="pending",
            question=question,
            answer=answer,
            patch_markdown=patch_markdown,
            rationale=rationale,
            confidence=confidence,
            provenance=provenance or {},
            created_by_message_id=created_by_message_id,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row

    async def list_patches(self, db: AsyncSession, kb_id: int, status: Optional[str] = None) -> list[WikiPatch]:
        statement = select(WikiPatch).where(WikiPatch.kb_id == kb_id)
        if status:
            statement = statement.where(WikiPatch.status == status)
        result = await db.execute(statement.order_by(WikiPatch.created_at.desc()))
        return list(result.scalars().all())

    async def replace_links(self, db: AsyncSession, *, kb_id: int, from_path: str, links: list[WikiLink]) -> None:
        existing = await db.execute(
            select(WikiLink).where(WikiLink.kb_id == kb_id, WikiLink.from_path == from_path)
        )
        for row in existing.scalars().all():
            await db.delete(row)
        for link in links:
            db.add(link)
        await db.commit()

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
        row = WikiRun(
            kb_id=kb_id,
            doc_id=doc_id,
            run_type=run_type,
            status=status,
            metrics=metrics or {},
            error_msg=error_msg,
            finished_at=datetime.utcnow() if status in {"succeeded", "failed"} else None,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row


wiki_crud = WikiCRUD()
```

- [ ] **Step 4: Run CRUD test**

Run:

```powershell
uv run --project backend pytest backend/tests/unit/test_wiki_models.py::test_upsert_page_and_revision_roundtrip -q
```

Expected: PASS.

- [ ] **Step 5: Commit CRUD**

```powershell
git add backend/app/crud/wiki.py backend/tests/unit/test_wiki_models.py
git commit -m "feat: add wiki crud"
```

## Task 6: Link Extraction and Lint

**Files:**
- Create: `backend/app/services/wiki/links.py`
- Create: `backend/app/services/wiki/lint.py`
- Test: `backend/tests/unit/test_wiki_links_lint.py`

- [ ] **Step 1: Write failing link and lint tests**

Create `backend/tests/unit/test_wiki_links_lint.py`:

```python
from pathlib import Path

from app.services.wiki.links import WikiLinkExtractor
from app.services.wiki.lint import WikiLint
from app.services.wiki.storage import WikiStorage


def test_link_extractor_finds_markdown_and_source_links():
    extractor = WikiLinkExtractor()
    links = extractor.extract(
        kb_id=1,
        from_path="index.md",
        markdown="- [API](sources/12-api.md)\n- [source:doc=12 chunk=3]",
    )

    assert any(link.to_path == "sources/12-api.md" and link.link_type == "related_to" for link in links)
    assert any(link.to_path == "source:doc=12 chunk=3" and link.link_type == "cites" for link in links)


def test_lint_reports_missing_frontmatter_and_malformed_log(tmp_path: Path):
    storage = WikiStorage(root_dir=tmp_path)
    storage.write_page(1, "index.md", "# Index\n- [Missing](missing.md)")
    storage.write_page(1, "log.md", "# Log\n## not parseable")

    lint = WikiLint(storage=storage)
    warnings = lint.lint_files(kb_id=1, db_pages=[])
    codes = {warning.code for warning in warnings}

    assert "missing_frontmatter" in codes
    assert "broken_index_link" in codes
    assert "malformed_log_heading" in codes
```

- [ ] **Step 2: Run link and lint tests and verify failure**

Run:

```powershell
uv run --project backend pytest backend/tests/unit/test_wiki_links_lint.py -q
```

Expected: FAIL with `ModuleNotFoundError` for `app.services.wiki.links`.

- [ ] **Step 3: Implement link extractor**

Create `backend/app/services/wiki/links.py`:

```python
"""Markdown link extraction for Wiki-RAG."""

from __future__ import annotations

import re

from app.models.wiki import WikiLink

_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_SOURCE_RE = re.compile(r"\[source:([^\]]+)\]")


class WikiLinkExtractor:
    """Extract page links and provenance links from Markdown."""

    def extract(self, *, kb_id: int, from_path: str, markdown: str, from_page_id: int | None = None) -> list[WikiLink]:
        links: list[WikiLink] = []
        for match in _MD_LINK_RE.finditer(markdown or ""):
            anchor, target = match.groups()
            if target.startswith(("http://", "https://", "#")):
                continue
            links.append(
                WikiLink(
                    kb_id=kb_id,
                    from_page_id=from_page_id,
                    from_path=from_path,
                    to_path=target.strip(),
                    link_type="related_to",
                    anchor_text=anchor.strip(),
                    provenance={"kind": "markdown_link"},
                )
            )

        for match in _SOURCE_RE.finditer(markdown or ""):
            target = f"source:{match.group(1).strip()}"
            links.append(
                WikiLink(
                    kb_id=kb_id,
                    from_page_id=from_page_id,
                    from_path=from_path,
                    to_path=target,
                    link_type="cites",
                    anchor_text=target,
                    provenance={"kind": "source_marker"},
                )
            )
        return links
```

- [ ] **Step 4: Implement lint**

Create `backend/app/services/wiki/lint.py`:

```python
"""Lint checks for Wiki-RAG Markdown files."""

from __future__ import annotations

import re

from app.models.wiki import WikiPage
from app.services.wiki.markdown import extract_frontmatter
from app.services.wiki.storage import WikiStorage
from app.services.wiki.types import WikiLintWarning

_LOG_HEADING_RE = re.compile(r"^## \[\d{4}-\d{2}-\d{2} \d{2}:\d{2}\] [a-zA-Z0-9_-]+(?: \| .+)?$")
_INDEX_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


class WikiLint:
    """Runs file-level wiki checks that do not require LLM calls."""

    def __init__(self, storage: WikiStorage):
        self.storage = storage

    def lint_files(self, *, kb_id: int, db_pages: list[WikiPage]) -> list[WikiLintWarning]:
        warnings: list[WikiLintWarning] = []
        db_paths = {page.path for page in db_pages}
        file_paths = set(self.storage.list_markdown_pages(kb_id))

        for path in sorted(file_paths):
            content = self.storage.read_page(kb_id, path)
            frontmatter, body = extract_frontmatter(content)
            if not frontmatter and path != "log.md":
                warnings.append(WikiLintWarning(code="missing_frontmatter", message="Page has no YAML frontmatter", path=path))
            if path not in db_paths and db_pages:
                warnings.append(WikiLintWarning(code="missing_db_row", message="Markdown page has no DB row", path=path))
            if path == "index.md":
                warnings.extend(self._lint_index_links(kb_id, body or content))
            if path == "log.md":
                warnings.extend(self._lint_log(path, body or content))

        for db_path in sorted(db_paths):
            if db_path not in file_paths:
                warnings.append(WikiLintWarning(code="missing_page_file", message="DB row points to missing Markdown file", path=db_path))

        return warnings

    def _lint_index_links(self, kb_id: int, markdown: str) -> list[WikiLintWarning]:
        warnings: list[WikiLintWarning] = []
        for match in _INDEX_LINK_RE.finditer(markdown or ""):
            target = match.group(1).strip()
            if target.startswith(("http://", "https://", "#")):
                continue
            try:
                if not self.storage.page_exists(kb_id, target):
                    warnings.append(WikiLintWarning(code="broken_index_link", message=f"Index links to missing page {target}", path="index.md"))
            except ValueError:
                warnings.append(WikiLintWarning(code="unsafe_index_link", message=f"Index link is unsafe {target}", path="index.md"))
        return warnings

    def _lint_log(self, path: str, markdown: str) -> list[WikiLintWarning]:
        warnings: list[WikiLintWarning] = []
        for line in (markdown or "").splitlines():
            if line.startswith("## ") and not _LOG_HEADING_RE.match(line):
                warnings.append(WikiLintWarning(code="malformed_log_heading", message="Log heading is not parseable", path=path))
        return warnings
```

- [ ] **Step 5: Run link and lint tests**

Run:

```powershell
uv run --project backend pytest backend/tests/unit/test_wiki_links_lint.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit links and lint**

```powershell
git add backend/app/services/wiki/links.py backend/app/services/wiki/lint.py backend/tests/unit/test_wiki_links_lint.py
git commit -m "feat: add wiki link extraction and lint"
```

## Task 7: Wiki Compiler for Schema, Index, Log, and Source Pages

**Files:**
- Create: `backend/app/services/wiki/compiler.py`
- Modify: `backend/app/services/wiki/service.py`
- Test: `backend/tests/unit/test_wiki_compiler.py`

- [ ] **Step 1: Write failing compiler test**

Create `backend/tests/unit/test_wiki_compiler.py`:

```python
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.knowledge import Document, DocStatus, KnowledgeBase
from app.services.wiki.compiler import WikiCompiler
from app.services.wiki.storage import WikiStorage


@pytest.mark.asyncio
async def test_compile_document_writes_source_index_log_and_patch(db_session, tmp_path: Path):
    kb = KnowledgeBase(user_id=1, name="KB")
    db_session.add(kb)
    await db_session.commit()
    await db_session.refresh(kb)

    source_file = tmp_path / "api.md"
    source_file.write_text("raw", encoding="utf-8")
    sidecar = tmp_path / "api.md.chunks.jsonl"
    sidecar.write_text(
        '{"parent_id":"1:0","content":"Milvus provides vector search.","structured_meta":{"parent_id":"1:0"}}\n',
        encoding="utf-8",
    )

    doc = Document(
        kb_id=kb.id,
        file_name="API Doc.md",
        file_path=str(source_file),
        file_type=".md",
        file_size=3,
        status=DocStatus.COMPLETED,
        chunk_count=1,
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)

    compiler = WikiCompiler(storage=WikiStorage(root_dir=tmp_path / "wiki"))
    result = await compiler.compile_document(db_session, kb_id=kb.id, doc_id=doc.id)

    assert result.pages_changed >= 4
    assert compiler.storage.page_exists(kb.id, "schema.md")
    assert compiler.storage.page_exists(kb.id, "index.md")
    assert compiler.storage.page_exists(kb.id, "log.md")
    assert compiler.storage.page_exists(kb.id, f"sources/{doc.id}-api-doc-md.md")
    assert result.patches_created >= 1
```

- [ ] **Step 2: Run compiler test and verify failure**

Run:

```powershell
uv run --project backend pytest backend/tests/unit/test_wiki_compiler.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.wiki.compiler'`.

- [ ] **Step 3: Implement compiler**

Create `backend/app/services/wiki/compiler.py`:

```python
"""Compile raw knowledge documents into Markdown wiki pages."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.knowledge import kb_crud
from app.crud.wiki import wiki_crud
from app.models.knowledge import DocStatus
from app.services.wiki.links import WikiLinkExtractor
from app.services.wiki.markdown import build_log_heading, build_markdown_page, slugify_title
from app.services.wiki.storage import WikiStorage
from app.services.wiki.types import WikiCompileResult


class WikiCompiler:
    """Builds wiki control pages and source pages from completed documents."""

    def __init__(self, storage: WikiStorage | None = None):
        self.storage = storage or WikiStorage()
        self.link_extractor = WikiLinkExtractor()

    async def compile_document(self, db: AsyncSession, *, kb_id: int, doc_id: int) -> WikiCompileResult:
        doc = await kb_crud.get_document(db, doc_id)
        if not doc or doc.kb_id != kb_id:
            raise ValueError("Document not found")
        if doc.status != DocStatus.COMPLETED:
            raise ValueError("Document is not completed")

        raw_chunks = self._read_sidecar_chunks(f"{doc.file_path}.chunks.jsonl")
        now = datetime.utcnow()
        pages_changed = 0

        pages_changed += await self._write_control_page(db, kb_id, "schema.md", "Schema", "schema", self._schema_content(now), "system")
        source_path = f"sources/{doc.id}-{slugify_title(doc.file_name, fallback='document', prefix=None)}.md"
        source_content = self._source_page_content(doc, raw_chunks, now)
        pages_changed += await self._write_control_page(
            db,
            kb_id,
            source_path,
            doc.file_name,
            "source",
            source_content,
            "ingest",
            source_doc_id=doc.id,
            provenance={"doc_id": doc.id, "chunk_count": len(raw_chunks)},
        )
        pages_changed += await self._write_control_page(db, kb_id, "index.md", "Index", "index", self._index_content(kb_id, source_path, doc.file_name, now), "ingest")
        pages_changed += await self._append_log(db, kb_id, now, "ingest", [f"doc_id={doc.id}", doc.file_name])

        links = self.link_extractor.extract(kb_id=kb_id, from_path=source_path, markdown=source_content)
        await wiki_crud.replace_links(db, kb_id=kb_id, from_path=source_path, links=links)
        patch = await wiki_crud.create_patch(
            db,
            kb_id=kb_id,
            target_path="topics/vector-search.md",
            operation="create",
            patch_markdown="# Vector Search\n\nSeed topic from source page.\n",
            rationale="Source mentions vector search and should be cross-linked as a topic candidate.",
            confidence=0.75,
            provenance={"doc_id": doc.id, "source_path": source_path},
        )

        await wiki_crud.create_run(
            db,
            kb_id=kb_id,
            doc_id=doc.id,
            run_type="ingest_doc",
            status="succeeded",
            metrics={"pages_changed": pages_changed, "patches_created": 1, "patch_id": patch.id},
        )
        return WikiCompileResult(kb_id=kb_id, doc_id=doc.id, pages_changed=pages_changed, patches_created=1)

    def _read_sidecar_chunks(self, sidecar_path: str) -> list[dict]:
        path = Path(sidecar_path)
        if not path.exists():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rows.append(json.loads(line))
        return rows

    async def _write_control_page(
        self,
        db: AsyncSession,
        kb_id: int,
        path: str,
        title: str,
        page_type: str,
        content: str,
        change_reason: str,
        source_doc_id: int | None = None,
        provenance: dict | None = None,
    ) -> int:
        self.storage.write_page(kb_id, path, content)
        content_hash = self.storage.content_hash(content)
        page = await wiki_crud.upsert_page(
            db,
            kb_id=kb_id,
            path=path,
            title=title,
            page_type=page_type,
            content_hash=content_hash,
            source_doc_id=source_doc_id,
            provenance=provenance or {},
        )
        await wiki_crud.create_revision(
            db,
            page_id=page.id,
            kb_id=kb_id,
            path=path,
            content_hash=content_hash,
            content_snapshot=content,
            change_reason=change_reason,
            provenance=provenance or {},
        )
        return 1

    async def _append_log(self, db: AsyncSession, kb_id: int, event_time: datetime, event_type: str, parts: list[str]) -> int:
        existing = ""
        if self.storage.page_exists(kb_id, "log.md"):
            existing = self.storage.read_page(kb_id, "log.md").rstrip() + "\n\n"
        heading = build_log_heading(event_time, event_type, parts)
        content = existing + heading + "\n\nRecorded by WikiCompiler.\n"
        return await self._write_control_page(db, kb_id, "log.md", "Log", "log", content, "ingest")

    def _schema_content(self, now: datetime) -> str:
        return build_markdown_page(
            {
                "title": "Schema",
                "page_type": "schema",
                "status": "active",
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
                "tags": ["schema", "operations"],
                "source_count": 0,
            },
            "Schema",
            [
                ("Operations", "ingest(source), query(question), writeback(question, answer, raw_sources), lint()"),
                ("Rules", "Do not add unsupported claims. Preserve provenance markers."),
            ],
        )

    def _source_page_content(self, doc, raw_chunks: list[dict], now: datetime) -> str:
        key_points = "\n".join(f"- {row.get('content', '').strip()[:240]}" for row in raw_chunks if row.get("content")) or "- No raw chunks available."
        source_refs = "\n".join(
            f"- [source:doc={doc.id} chunk_index={index}]"
            for index, _row in enumerate(raw_chunks)
        ) or f"- [source:doc={doc.id}]"
        return build_markdown_page(
            {
                "title": doc.file_name,
                "page_type": "source",
                "status": "active",
                "doc_id": doc.id,
                "file_name": doc.file_name,
                "file_type": doc.file_type,
                "chunk_count": len(raw_chunks),
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
                "tags": ["source"],
                "source_count": len(raw_chunks),
            },
            doc.file_name,
            [
                ("Source Metadata", f"- doc_id: {doc.id}\n- file_name: {doc.file_name}\n- file_type: {doc.file_type}\n- chunk_count: {len(raw_chunks)}"),
                ("Summary", f"This source contains {len(raw_chunks)} raw chunks."),
                ("Key Points", key_points),
                ("Important Terms", "- vector search\n- retrieval"),
                ("Questions This Source Can Answer", "- What does this source say?"),
                ("Source References", source_refs),
                ("Related Pages", "- [Vector Search](../topics/vector-search.md)"),
            ],
        )

    def _index_content(self, kb_id: int, source_path: str, title: str, now: datetime) -> str:
        return build_markdown_page(
            {
                "title": "Index",
                "page_type": "index",
                "status": "active",
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
                "tags": ["index"],
                "source_count": 1,
            },
            "Index",
            [
                ("Overview", f"Knowledge base {kb_id} wiki index."),
                ("Main Topics", "- [Vector Search](topics/vector-search.md)"),
                ("Entities", ""),
                ("Source Documents", f"- [{title}]({source_path})"),
                ("Recent Updates", f"- Added [{title}]({source_path})"),
                ("Open Questions", "- No open questions recorded."),
            ],
        )
```

- [ ] **Step 4: Replace temporary facade with compiler-backed service**

Modify `backend/app/services/wiki/service.py`:

```python
"""Wiki-RAG facade service."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.wiki.compiler import WikiCompiler
from app.services.wiki.lint import WikiLint
from app.services.wiki.storage import WikiStorage


class WikiService:
    """Facade for Wiki-RAG operations."""

    def __init__(self, storage: WikiStorage | None = None):
        self.storage = storage or WikiStorage()
        self.compiler = WikiCompiler(storage=self.storage)
        self.lint = WikiLint(storage=self.storage)

    async def compile_document(self, db: AsyncSession, *, kb_id: int, doc_id: int):
        return await self.compiler.compile_document(db, kb_id=kb_id, doc_id=doc_id)
```

- [ ] **Step 5: Run compiler test**

Run:

```powershell
uv run --project backend pytest backend/tests/unit/test_wiki_compiler.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit compiler**

```powershell
git add backend/app/services/wiki/compiler.py backend/app/services/wiki/service.py backend/tests/unit/test_wiki_compiler.py
git commit -m "feat: compile documents into wiki pages"
```

## Task 8: Index-First Wiki Retriever

**Files:**
- Create: `backend/app/services/wiki/retriever.py`
- Modify: `backend/app/services/wiki/service.py`
- Test: `backend/tests/unit/test_wiki_retriever.py`

- [ ] **Step 1: Write failing retriever test**

Create `backend/tests/unit/test_wiki_retriever.py`:

```python
from pathlib import Path

import pytest

from app.crud.wiki import wiki_crud
from app.models.knowledge import KnowledgeBase
from app.services.wiki.retriever import WikiRetriever
from app.services.wiki.storage import WikiStorage


@pytest.mark.asyncio
async def test_retriever_prefers_index_linked_page(db_session, tmp_path: Path):
    kb = KnowledgeBase(user_id=1, name="KB")
    db_session.add(kb)
    await db_session.commit()
    await db_session.refresh(kb)

    storage = WikiStorage(root_dir=tmp_path)
    storage.write_page(kb.id, "index.md", "# Index\n- [Retrieval](topics/retrieval.md)")
    storage.write_page(kb.id, "topics/retrieval.md", "---\ntitle: Retrieval\npage_type: topic\n---\n# Retrieval\nBM25 vector rerank")
    storage.write_page(kb.id, "topics/other.md", "---\ntitle: Other\npage_type: topic\n---\n# Other\nunrelated")
    await wiki_crud.upsert_page(db_session, kb_id=kb.id, path="index.md", title="Index", page_type="index", content_hash="1")
    await wiki_crud.upsert_page(db_session, kb_id=kb.id, path="topics/retrieval.md", title="Retrieval", page_type="topic", content_hash="2")
    await wiki_crud.upsert_page(db_session, kb_id=kb.id, path="topics/other.md", title="Other", page_type="topic", content_hash="3")

    retriever = WikiRetriever(storage=storage)
    hits = await retriever.search(db_session, kb_id=kb.id, query="BM25 rerank", top_k=2)

    assert hits[0].path == "topics/retrieval.md"
    assert hits[0].score > 0
```

- [ ] **Step 2: Run retriever test and verify failure**

Run:

```powershell
uv run --project backend pytest backend/tests/unit/test_wiki_retriever.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.wiki.retriever'`.

- [ ] **Step 3: Implement retriever**

Create `backend/app/services/wiki/retriever.py`:

```python
"""Index-first wiki page retrieval."""

from __future__ import annotations

import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.wiki import wiki_crud
from app.services.shared.bm25 import BM25Index, _tokenize
from app.services.wiki.markdown import extract_frontmatter
from app.services.wiki.storage import WikiStorage
from app.services.wiki.types import WikiSearchHit

_INDEX_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


class WikiRetriever:
    """Searches wiki pages, using index.md as the first navigation spine."""

    def __init__(self, storage: WikiStorage | None = None):
        self.storage = storage or WikiStorage()

    async def search(self, db: AsyncSession, *, kb_id: int, query: str, top_k: int) -> list[WikiSearchHit]:
        pages = await wiki_crud.list_pages(db, kb_id)
        if not pages:
            return []

        index_paths = self._index_linked_paths(kb_id)
        docs = []
        page_by_doc_index = []
        for page in pages:
            try:
                content = self.storage.read_page(kb_id, page.path)
            except FileNotFoundError:
                continue
            frontmatter, body = extract_frontmatter(content)
            searchable = " ".join(
                [
                    page.title,
                    page.path,
                    page.page_type,
                    " ".join(str(value) for value in frontmatter.values()),
                    body,
                ]
            )
            docs.append(searchable)
            page_by_doc_index.append((page, body))

        if not docs:
            return []

        bm25 = BM25Index([_tokenize(doc) for doc in docs])
        scores = bm25.get_scores(_tokenize(query or ""))
        hits = []
        for index, score in enumerate(scores):
            page, body = page_by_doc_index[index]
            adjusted = float(score)
            if page.path in index_paths:
                adjusted += 0.25
            snippet = self._snippet(body, query)
            hits.append(
                WikiSearchHit(
                    page_id=page.id,
                    path=page.path,
                    title=page.title,
                    page_type=page.page_type,
                    score=adjusted,
                    snippet=snippet,
                )
            )
        hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits[:top_k]

    def _index_linked_paths(self, kb_id: int) -> set[str]:
        try:
            content = self.storage.read_page(kb_id, "index.md")
        except FileNotFoundError:
            return set()
        return {
            match.group(1).strip()
            for match in _INDEX_LINK_RE.finditer(content)
            if not match.group(1).startswith(("http://", "https://", "#"))
        }

    def _snippet(self, body: str, query: str) -> str:
        text = re.sub(r"\s+", " ", body or "").strip()
        if len(text) <= 240:
            return text
        return text[:240] + "..."
```

- [ ] **Step 4: Add service search method**

Modify `backend/app/services/wiki/service.py`:

```python
from app.services.wiki.retriever import WikiRetriever
```

Inside `__init__`:

```python
        self.retriever = WikiRetriever(storage=self.storage)
```

Add method:

```python
    async def search_pages(self, db: AsyncSession, *, kb_id: int, query: str, top_k: int):
        return await self.retriever.search(db, kb_id=kb_id, query=query, top_k=top_k)
```

- [ ] **Step 5: Run retriever test**

Run:

```powershell
uv run --project backend pytest backend/tests/unit/test_wiki_retriever.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit retriever**

```powershell
git add backend/app/services/wiki/retriever.py backend/app/services/wiki/service.py backend/tests/unit/test_wiki_retriever.py
git commit -m "feat: add index-first wiki retrieval"
```

## Task 9: Wiki API Routes

**Files:**
- Create: `backend/app/routers/v1/wiki.py`
- Modify: `backend/app/routers/v1/__init__.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/unit/test_wiki_api.py`

- [ ] **Step 1: Write failing API test**

Create `backend/tests/unit/test_wiki_api.py`:

```python
import pytest

from app.crud.wiki import wiki_crud
from app.models.knowledge import KnowledgeBase


@pytest.mark.asyncio
async def test_wiki_pages_endpoint_returns_owned_pages(client, db_session, auth_headers, test_user_verified):
    kb = KnowledgeBase(user_id=test_user_verified.id, name="KB")
    db_session.add(kb)
    await db_session.commit()
    await db_session.refresh(kb)
    await wiki_crud.upsert_page(
        db_session,
        kb_id=kb.id,
        path="index.md",
        title="Index",
        page_type="index",
        content_hash="abc",
    )

    response = await client.get(f"/api/v1/knowledge/{kb.id}/wiki/pages", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()[0]["path"] == "index.md"
```

- [ ] **Step 2: Run API test and verify failure**

Run:

```powershell
uv run --project backend pytest backend/tests/unit/test_wiki_api.py -q
```

Expected: FAIL with 404 because the route does not exist.

- [ ] **Step 3: Implement wiki router**

Create `backend/app/routers/v1/wiki.py`:

```python
"""Wiki-RAG API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config.settings import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.crud.knowledge import kb_crud
from app.crud.wiki import wiki_crud
from app.models.user import User
from app.services.wiki import wiki_service

router = APIRouter(prefix="/knowledge/{kb_id}/wiki", tags=["Wiki"])


async def _owned_kb_or_404(db: AsyncSession, kb_id: int, user_id: int):
    kb = await kb_crud.get_kb(db, kb_id)
    if not kb or kb.user_id != user_id:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return kb


@router.get("/pages")
async def list_wiki_pages(
    kb_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _owned_kb_or_404(db, kb_id, current_user.id)
    pages = await wiki_crud.list_pages(db, kb_id)
    return [
        {
            "id": page.id,
            "path": page.path,
            "title": page.title,
            "page_type": page.page_type,
            "status": page.status,
            "updated_at": page.updated_at,
        }
        for page in pages
    ]


@router.get("/pages/{page_id}")
async def get_wiki_page(
    kb_id: int,
    page_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _owned_kb_or_404(db, kb_id, current_user.id)
    page = await wiki_crud.get_page(db, kb_id, page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Wiki page not found")
    content = wiki_service.storage.read_page(kb_id, page.path)
    return {
        "id": page.id,
        "path": page.path,
        "title": page.title,
        "page_type": page.page_type,
        "status": page.status,
        "content": content,
        "provenance": page.provenance or {},
    }


@router.get("/search")
async def search_wiki_pages(
    kb_id: int,
    q: str = Query(..., min_length=1),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _owned_kb_or_404(db, kb_id, current_user.id)
    hits = await wiki_service.search_pages(db, kb_id=kb_id, query=q, top_k=settings.wiki.WIKI_RETRIEVER_TOP_K)
    return [hit.__dict__ for hit in hits]


@router.post("/rebuild")
async def rebuild_wiki(
    kb_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _owned_kb_or_404(db, kb_id, current_user.id)
    docs = await kb_crud.get_completed_documents(db, kb_id)
    results = []
    for doc in docs:
        result = await wiki_service.compile_document(db, kb_id=kb_id, doc_id=doc.id)
        results.append(result.__dict__)
    return {"success": True, "results": results}


@router.post("/lint")
async def lint_wiki(
    kb_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _owned_kb_or_404(db, kb_id, current_user.id)
    pages = await wiki_crud.list_pages(db, kb_id)
    warnings = wiki_service.lint.lint_files(kb_id=kb_id, db_pages=pages)
    return {"warnings": [warning.__dict__ for warning in warnings]}


@router.get("/patches")
async def list_wiki_patches(
    kb_id: int,
    status: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _owned_kb_or_404(db, kb_id, current_user.id)
    patches = await wiki_crud.list_patches(db, kb_id, status=status)
    return [
        {
            "id": patch.id,
            "target_path": patch.target_path,
            "operation": patch.operation,
            "status": patch.status,
            "question": patch.question,
            "confidence": patch.confidence,
            "created_at": patch.created_at,
        }
        for patch in patches
    ]
```

- [ ] **Step 4: Register router**

Modify `backend/app/routers/v1/__init__.py`.

Add import:

```python
from .wiki import router as wiki_router
```

Update `__all__`:

```python
__all__ = [
    "auth_router",
    "user_router",
    "chat_router",
    "knowledge_router",
    "wiki_router",
    "llm_settings_router",
    "usage_router",
    "news_router",
]
```

Modify `backend/app/main.py`.

Add to import tuple:

```python
    wiki_router,
```

Add route include after `knowledge_router`:

```python
app.include_router(wiki_router, prefix="/api/v1")
```

- [ ] **Step 5: Run API test**

Run:

```powershell
uv run --project backend pytest backend/tests/unit/test_wiki_api.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit routes**

```powershell
git add backend/app/routers/v1/wiki.py backend/app/routers/v1/__init__.py backend/app/main.py backend/tests/unit/test_wiki_api.py
git commit -m "feat: add wiki api routes"
```

## Task 10: Post-Ingest Wiki Compile Hook

**Files:**
- Modify: `backend/app/services/knowledge/ingest.py`
- Test: `backend/tests/unit/test_wiki_ingest_hook.py`

- [ ] **Step 1: Write failing ingest hook test**

Create `backend/tests/unit/test_wiki_ingest_hook.py`:

```python
import pytest

from app.services.knowledge.ingest import KnowledgeIngest


class _Service:
    pass


@pytest.mark.asyncio
async def test_maybe_compile_wiki_skips_when_disabled(monkeypatch):
    ingest = KnowledgeIngest(_Service())
    calls = []

    async def fake_compile(*args, **kwargs):
        calls.append(kwargs)

    monkeypatch.setattr("app.services.knowledge.ingest.wiki_service.compile_document", fake_compile)
    monkeypatch.setattr("app.services.knowledge.ingest.settings.wiki.WIKI_AUTO_COMPILE_ON_INGEST", False)

    await ingest._maybe_compile_wiki(db=None, kb_id=1, doc_id=2)

    assert calls == []


@pytest.mark.asyncio
async def test_maybe_compile_wiki_calls_service_when_enabled(monkeypatch):
    ingest = KnowledgeIngest(_Service())
    calls = []

    async def fake_compile(*args, **kwargs):
        calls.append(kwargs)

    monkeypatch.setattr("app.services.knowledge.ingest.wiki_service.compile_document", fake_compile)
    monkeypatch.setattr("app.services.knowledge.ingest.settings.wiki.WIKI_AUTO_COMPILE_ON_INGEST", True)

    await ingest._maybe_compile_wiki(db="db", kb_id=1, doc_id=2)

    assert calls == [{"kb_id": 1, "doc_id": 2}]
```

- [ ] **Step 2: Run ingest hook test and verify failure**

Run:

```powershell
uv run --project backend pytest backend/tests/unit/test_wiki_ingest_hook.py -q
```

Expected: FAIL with `AttributeError: 'KnowledgeIngest' object has no attribute '_maybe_compile_wiki'`.

- [ ] **Step 3: Add imports to ingest**

Modify `backend/app/services/knowledge/ingest.py`.

Add imports:

```python
from app.services.wiki import wiki_service
```

- [ ] **Step 4: Add compile helper**

Add this method inside `KnowledgeIngest`:

```python
    async def _maybe_compile_wiki(self, db, kb_id: int, doc_id: int) -> None:
        """Compile wiki pages after successful document ingestion when enabled."""
        if not settings.wiki.WIKI_AUTO_COMPILE_ON_INGEST:
            return
        try:
            await wiki_service.compile_document(db, kb_id=kb_id, doc_id=doc_id)
        except Exception as exc:
            logger.warning(f"Wiki compile failed for doc {doc_id}: {exc}")
```

- [ ] **Step 5: Call helper after document completion**

In `KnowledgeIngest.ingest_document()`, after the successful `await kb_crud.update_document_status(... status=DocStatus.COMPLETED ...)` and `self.service._invalidate_bm25_cache(doc.kb_id)`, add:

```python
                await self._maybe_compile_wiki(db, kb_id=doc.kb_id, doc_id=doc.id)
```

The final success block should keep document completion before wiki compilation so wiki failures do not mark the document failed.

- [ ] **Step 6: Run ingest hook test**

Run:

```powershell
uv run --project backend pytest backend/tests/unit/test_wiki_ingest_hook.py -q
```

Expected: PASS.

- [ ] **Step 7: Run focused wiki unit tests**

Run:

```powershell
uv run --project backend pytest backend/tests/unit/test_wiki_settings.py backend/tests/unit/test_wiki_models.py backend/tests/unit/test_wiki_markdown.py backend/tests/unit/test_wiki_storage.py backend/tests/unit/test_wiki_links_lint.py backend/tests/unit/test_wiki_compiler.py backend/tests/unit/test_wiki_retriever.py backend/tests/unit/test_wiki_api.py backend/tests/unit/test_wiki_ingest_hook.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit ingest hook**

```powershell
git add backend/app/services/knowledge/ingest.py backend/tests/unit/test_wiki_ingest_hook.py
git commit -m "feat: compile wiki after knowledge ingest"
```

## Task 11: Final Verification

**Files:**
- No new files.

- [ ] **Step 1: Run all backend unit tests that do not require live external services**

Run:

```powershell
uv run --project backend pytest backend/tests/unit -q
```

Expected: PASS. If failures occur from unrelated existing tests that require external services, record exact test names and run the wiki-focused command from Task 10 Step 7.

- [ ] **Step 2: Run Python compile check for modified backend code**

Run:

```powershell
uv run --project backend python -m compileall backend/app/core/config/modules/wiki.py backend/app/models/wiki.py backend/app/crud/wiki.py backend/app/services/wiki backend/app/routers/v1/wiki.py
```

Expected: command exits with code 0.

- [ ] **Step 3: Check git diff**

Run:

```powershell
git status --short
git diff --stat
```

Expected: only files from this plan are changed, plus pre-existing unrelated dirty files that were already present before execution.

- [ ] **Step 4: Commit verification adjustments if any were needed**

If Step 1 or Step 2 required small corrections, commit those corrections:

```powershell
git add backend/app/core/config/modules/wiki.py backend/app/models/wiki.py backend/app/crud/wiki.py backend/app/services/wiki backend/app/routers/v1/wiki.py backend/app/services/knowledge/ingest.py backend/tests/unit/test_wiki_*.py backend/alembic/versions/h1i2j3k4l5m6_add_wiki_tables.py
git commit -m "test: verify wiki rag foundations"
```

If no corrections were needed, skip this commit.

## Self-Review

Spec coverage:

- Phase 1 file layer and DB index are covered by Tasks 1-7.
- Phase 1.5 index-first retrieval, links, and assisted ingest configuration are covered by Tasks 1, 6, 8, and 10.
- Wiki pages/search/lint/rebuild/patch list APIs are covered by Task 9.
- Ingest hook is covered by Task 10.
- Wiki-first answer and raw RAG fallback are not included in this plan and need the next plan.
- Pending patch application/rejection endpoints are declared in the spec but are not implemented here because this plan only needs patch creation and listing for cross-reference candidates; apply/reject belongs with the writeback plan.

Unresolved-marker scan:

- No unresolved marker terms or unspecified validation steps remain.
- Every code-changing step includes exact code or exact insertion text.

Type consistency:

- `WikiService.compile_document()` delegates to `WikiCompiler.compile_document()`.
- `WikiRetriever.search()` returns `WikiSearchHit`.
- `WikiLint.lint_files()` returns `WikiLintWarning`.
- `wiki_crud.upsert_page()` returns `WikiPage`.
- `WikiStorage` path methods use `kb_id` and relative `.md` page paths consistently.
