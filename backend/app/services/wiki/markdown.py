"""Markdown helpers for Wiki-RAG pages."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Iterable, Mapping, Sequence


_NON_ALNUM_RE = re.compile(r"[^a-zA-Z0-9]+")
_SAFE_EVENT_RE = re.compile(r"[^a-zA-Z0-9_-]+")
_INT_FRONTMATTER_KEYS = {
    "created_by_message_id",
    "doc_id",
    "from_page_id",
    "kb_id",
    "page_id",
    "patches_created",
    "source_doc_id",
    "to_page_id",
}
_FLOAT_FRONTMATTER_KEYS = {"confidence", "score"}


def slugify_title(
    title: str | None,
    fallback: str | None = "page",
    prefix: str | None = None,
) -> str:
    """Build a filesystem-friendly ASCII slug from a title."""

    raw = (title or "").strip() or (fallback or "")
    ascii_title = raw.encode("ascii", "ignore").decode("ascii")
    slug = _NON_ALNUM_RE.sub("-", ascii_title).strip("-").lower()

    if not slug:
        ascii_fallback = (fallback or "").encode("ascii", "ignore").decode("ascii")
        slug = _NON_ALNUM_RE.sub("-", ascii_fallback).strip("-").lower()

    if not slug:
        slug = "page"

    if prefix is not None:
        safe_prefix = _NON_ALNUM_RE.sub("-", str(prefix)).strip("-").lower()
        if safe_prefix:
            return f"{safe_prefix}-{slug}"

    return slug


def build_frontmatter(values: Mapping[str, Any]) -> str:
    """Build simple YAML-like frontmatter without external dependencies."""

    lines = ["---"]
    for key, value in values.items():
        if value is None:
            continue
        lines.append(f"{key}: {_format_value(value)}")
    lines.append("---")

    return "\n".join(lines)


def extract_frontmatter(markdown: str) -> tuple[dict[str, Any], str]:
    """Extract frontmatter created by build_frontmatter and stripped body text."""

    if not markdown.startswith("---"):
        return {}, markdown

    lines = markdown.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, markdown

    end_index = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_index = index
            break

    if end_index is None:
        return {}, markdown

    frontmatter: dict[str, Any] = {}
    for line in lines[1:end_index]:
        if not line.strip() or ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        normalized_key = key.strip()
        frontmatter[normalized_key] = _parse_scalar(normalized_key, raw_value.strip())

    body = "\n".join(lines[end_index + 1 :]).strip()
    return frontmatter, body


def build_log_heading(
    event_time: datetime,
    event_type: str,
    parts: Sequence[str],
) -> str:
    """Build a stable H2 log heading for parseable changelog entries."""

    timestamp = event_time.strftime("%Y-%m-%d %H:%M")
    safe_event_type = _SAFE_EVENT_RE.sub("_", event_type.strip()).strip("_")
    if not safe_event_type:
        safe_event_type = "event"

    suffix = " | ".join(str(part).strip() for part in parts if str(part).strip())
    heading = f"## [{timestamp}] {safe_event_type}"
    if suffix:
        heading = f"{heading} | {suffix}"

    return heading


def build_markdown_page(
    frontmatter: Mapping[str, Any],
    title: str,
    sections: Iterable[tuple[str, str]],
) -> str:
    """Build a complete wiki markdown page with H1 and H2 sections."""

    blocks = [build_frontmatter(frontmatter), f"# {title.strip()}"]
    for section_title, section_body in sections:
        blocks.append(f"## {section_title.strip()}\n\n{(section_body or '').strip()}")

    return "\n\n".join(blocks).rstrip() + "\n"


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list | tuple):
        return json.dumps(
            [_clean_list_item(item) for item in value],
            ensure_ascii=False,
        )
    return str(value).strip()


def _parse_scalar(key: str, value: str) -> Any:
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if value.startswith("[") and value.endswith("]"):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            inner = value[1:-1].strip()
            if not inner:
                return []
            return [_clean_list_item(item) for item in inner.split(",")]
        if isinstance(parsed, list):
            return [_clean_list_item(item) for item in parsed]

    if key in _INT_FRONTMATTER_KEYS:
        try:
            return int(value)
        except ValueError:
            return _clean_string(value)

    if key in _FLOAT_FRONTMATTER_KEYS:
        try:
            return float(value)
        except ValueError:
            return _clean_string(value)

    return _clean_string(value)


def _clean_list_item(item: Any) -> str:
    return _clean_string(str(item))


def _clean_string(value: str) -> str:
    return value.strip().strip("\"'")
