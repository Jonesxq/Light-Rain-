"""Utilities for cleaning RAG context text before indexing or answering."""

from __future__ import annotations

import re

_HTML_COMMENT_RE = re.compile(r"<!--[\s\S]*?-->")
_SPACE_RE = re.compile(r"[ \t]+")
_BLANK_RE = re.compile(r"\n{3,}")
_SEMANTIC_RE = re.compile(r"[A-Za-z0-9\u4e00-\u9fff]")
_WORD_RE = re.compile(r"[A-Za-z0-9\u4e00-\u9fff]+")


def clean_rag_text(text: str | None) -> str:
    """Remove Docling/Markdown artifacts while preserving semantic text."""
    if not text:
        return ""

    cleaned = _HTML_COMMENT_RE.sub("", str(text))
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")

    kept_lines: list[str] = []
    for line in cleaned.splitlines():
        stripped = _SPACE_RE.sub(" ", line.strip())
        if not stripped:
            kept_lines.append("")
            continue
        if _is_noise_line(stripped):
            continue
        kept_lines.append(stripped)

    cleaned = "\n".join(kept_lines)
    cleaned = _SPACE_RE.sub(" ", cleaned)
    cleaned = _BLANK_RE.sub("\n\n", cleaned)
    return cleaned.strip()


def is_artifact_only_text(text: str | None) -> bool:
    """Return true when text has too little semantic content for RAG."""
    cleaned = clean_rag_text(text)
    if not cleaned:
        return True

    semantic_count = len(_SEMANTIC_RE.findall(cleaned))
    word_count = len(_WORD_RE.findall(cleaned))
    if semantic_count < 8 and word_count < 2:
        return True

    compact = re.sub(r"\s+", "", cleaned)
    if len(compact) >= 20 and semantic_count / max(len(compact), 1) < 0.2:
        return True

    return False


def _is_noise_line(line: str) -> bool:
    if _is_markdown_table_separator(line):
        return True
    if _is_horizontal_rule_like(line):
        return True
    return False


def _is_markdown_table_separator(line: str) -> bool:
    if "---" not in line or "|" not in line:
        return False
    return bool(re.fullmatch(r"[\s|:\-]+", line))


def _is_horizontal_rule_like(line: str) -> bool:
    compact = re.sub(r"\s+", "", line)
    if len(compact) < 8:
        return False
    if _SEMANTIC_RE.search(compact):
        return False
    return bool(re.fullmatch(r"[-_=*~.|/\\]+", compact))
