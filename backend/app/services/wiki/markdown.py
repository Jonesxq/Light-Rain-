"""Markdown helpers for Wiki-RAG pages."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Iterable, Mapping, Sequence


_NON_ALNUM_RE = re.compile(r"[^a-zA-Z0-9]+")
_SAFE_EVENT_RE = re.compile(r"[^a-zA-Z0-9_-]+")
_INT_FRONTMATTER_KEYS = {
    "chunk_count",
    "created_by_message_id",
    "doc_id",
    "from_page_id",
    "kb_id",
    "page_id",
    "patches_created",
    "source_count",
    "source_doc_id",
    "to_page_id",
}
_FLOAT_FRONTMATTER_KEYS = {"confidence", "score"}
_LIST_FRONTMATTER_KEYS = {"tags", "wiki_links"}
_BOOL_FRONTMATTER_KEYS = {"archived", "draft", "enabled"}
_FRONTMATTER_DELIMITER_RE = re.compile(r"^---[ \t]*(?:\r\n|\n|\r|$)", re.MULTILINE)


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
    """Extract frontmatter created by build_frontmatter and preserve body text."""

    if not markdown.startswith("---"):
        return {}, markdown

    opening_match = _FRONTMATTER_DELIMITER_RE.match(markdown)
    if opening_match is None:
        return {}, markdown

    closing_match = _FRONTMATTER_DELIMITER_RE.search(markdown, opening_match.end())
    if closing_match is None:
        return {}, markdown

    frontmatter: dict[str, Any] = {}
    frontmatter_text = markdown[opening_match.end() : closing_match.start()]
    for line in frontmatter_text.splitlines():
        if not line.strip() or ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        normalized_key = key.strip()
        frontmatter[normalized_key] = _parse_scalar(normalized_key, raw_value.strip())

    body = markdown[closing_match.end() :]
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
    sections: Iterable[tuple[str, str | None]],
) -> str:
    """Build a complete wiki markdown page with H1 and H2 sections."""

    markdown = f"{build_frontmatter(frontmatter)}\n\n# {title.strip()}"
    for section_title, section_body in sections:
        body = "" if section_body is None else section_body
        markdown = (
            f"{markdown}{_markdown_block_separator(markdown)}"
            f"## {section_title.strip()}\n\n{body}"
        )

    if not markdown.endswith("\n"):
        markdown = f"{markdown}\n"

    return markdown


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
    return json.dumps(str(value).strip(), ensure_ascii=False)


def _markdown_block_separator(markdown: str) -> str:
    if markdown.endswith("\n\n"):
        return ""
    if markdown.endswith("\n"):
        return "\n"
    return "\n\n"


def _parse_scalar(key: str, value: str) -> Any:
    if key in _LIST_FRONTMATTER_KEYS:
        return _parse_list(value)

    parsed_json_string = _parse_json_string(value)
    scalar_value = parsed_json_string if parsed_json_string is not None else value

    if key in _BOOL_FRONTMATTER_KEYS:
        if scalar_value.lower() == "true":
            return True
        if scalar_value.lower() == "false":
            return False

    if key in _INT_FRONTMATTER_KEYS:
        try:
            return int(scalar_value)
        except ValueError:
            return _clean_string(scalar_value)

    if key in _FLOAT_FRONTMATTER_KEYS:
        try:
            return float(scalar_value)
        except ValueError:
            return _clean_string(scalar_value)

    return _clean_string(scalar_value)


def _parse_list(value: str) -> list[str]:
    if value.startswith("[") and value.endswith("]"):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value]
        if isinstance(parsed, list):
            return [_clean_list_item(item) for item in parsed]

    if not value:
        return []

    return [_clean_list_item(value)]


def _clean_list_item(item: Any) -> str:
    return str(item).strip()


def _parse_json_string(value: str) -> str | None:
    if not value.startswith('"'):
        return None

    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None

    if isinstance(parsed, str):
        return parsed

    return None


def _clean_string(value: str) -> str:
    return value.strip()
