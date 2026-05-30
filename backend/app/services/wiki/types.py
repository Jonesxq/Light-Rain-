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
LINK_TYPES = {
    "related_to",
    "cites",
    "defines",
    "answers",
    "contradicts",
    "supersedes",
    "mentions",
}


@dataclass
class WikiPageInput:
    """Input needed to create or update a wiki page."""

    path: str
    title: str
    page_type: str
    content: str
    source_doc_id: Optional[int] = None
    provenance: dict = field(default_factory=dict)


@dataclass
class WikiCompileResult:
    """Summary of a wiki compilation run."""

    kb_id: int
    doc_id: Optional[int]
    pages_changed: int
    patches_created: int
    warnings: list[str] = field(default_factory=list)


@dataclass
class WikiLintWarning:
    """Non-fatal wiki lint finding."""

    code: str
    message: str
    path: Optional[str] = None
    severity: str = "warning"


@dataclass
class WikiSearchHit:
    """Search result from wiki retrieval."""

    page_id: Optional[int]
    path: str
    title: str
    page_type: str
    score: float
    snippet: str


@dataclass
class WikiLogEvent:
    """Structured event for wiki changelog pages."""

    event_time: datetime
    event_type: str
    parts: list[str]
