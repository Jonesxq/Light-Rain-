"""Wiki-RAG data models."""
from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, Index, JSON
from sqlmodel import Column, Field, SQLModel, Text


class WikiPage(SQLModel, table=True):
    """Compiled wiki page for a knowledge base."""

    __tablename__ = "wiki_pages"
    __table_args__ = (
        Index("ix_wiki_pages_kb_path", "kb_id", "path", unique=True),
        Index("ix_wiki_pages_kb_type", "kb_id", "page_type"),
        Index("ix_wiki_pages_kb_status", "kb_id", "status"),
        Index("ix_wiki_pages_source_doc", "source_doc_id"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    kb_id: int = Field(foreign_key="knowledge_bases.id")
    path: str = Field(max_length=512)
    title: str = Field(max_length=255)
    page_type: str = Field(max_length=50)
    status: str = Field(default="active", max_length=30)
    content_hash: str = Field(default="", max_length=128)
    source_doc_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            ForeignKey("kb_documents.id", ondelete="SET NULL"), nullable=True
        ),
    )
    provenance: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class WikiPageRevision(SQLModel, table=True):
    """Point-in-time snapshot of a wiki page."""

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
    kb_id: int = Field(foreign_key="knowledge_bases.id")
    path: str = Field(max_length=512)
    content_hash: str = Field(max_length=128)
    content_snapshot: str = Field(sa_column=Column(Text, nullable=False))
    change_reason: Optional[str] = Field(default=None, max_length=255)
    provenance: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class WikiPatch(SQLModel, table=True):
    """Manual or generated patch proposal for a wiki page."""

    __tablename__ = "wiki_patches"
    __table_args__ = (
        Index("ix_wiki_patches_kb_status", "kb_id", "status"),
        Index("ix_wiki_patches_target", "kb_id", "target_path"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    kb_id: int = Field(foreign_key="knowledge_bases.id")
    page_id: Optional[int] = Field(
        default=None,
        sa_column=Column(ForeignKey("wiki_pages.id", ondelete="SET NULL"), nullable=True),
    )
    target_path: str = Field(max_length=512)
    operation: str = Field(max_length=50)
    status: str = Field(default="pending", max_length=30)
    question: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    answer: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    patch_markdown: str = Field(sa_column=Column(Text, nullable=False))
    rationale: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    confidence: float = Field(default=0.0)
    provenance: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    created_by_message_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            ForeignKey("chat_messages.id", ondelete="SET NULL"), nullable=True
        ),
    )
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    applied_at: Optional[datetime] = Field(default=None)
    rejected_at: Optional[datetime] = Field(default=None)


class WikiLink(SQLModel, table=True):
    """Directed relationship between wiki pages or paths."""

    __tablename__ = "wiki_links"
    __table_args__ = (
        Index("ix_wiki_links_from", "kb_id", "from_path"),
        Index("ix_wiki_links_to", "kb_id", "to_path"),
        Index("ix_wiki_links_type", "kb_id", "link_type"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    kb_id: int = Field(foreign_key="knowledge_bases.id")
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
    provenance: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class WikiRun(SQLModel, table=True):
    """Wiki ingestion, compilation, or maintenance run."""

    __tablename__ = "wiki_runs"
    __table_args__ = (
        Index("ix_wiki_runs_kb_type", "kb_id", "run_type"),
        Index("ix_wiki_runs_kb_status", "kb_id", "status"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    kb_id: int = Field(foreign_key="knowledge_bases.id")
    doc_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            ForeignKey("kb_documents.id", ondelete="SET NULL"), nullable=True
        ),
    )
    run_type: str = Field(max_length=50)
    status: str = Field(max_length=30)
    metrics: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    error_msg: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    finished_at: Optional[datetime] = Field(default=None)
