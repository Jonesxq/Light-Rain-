"""Markdown link extraction for Wiki-RAG pages."""

from __future__ import annotations

import re

from app.models.wiki import WikiLink


_MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[([^\]\n]+)\]\(([^)\n]+)\)")
_SOURCE_MARKER_RE = re.compile(r"(?<!!)\[\s*source:([^\]\n]+)\]")
_URI_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


class WikiLinkExtractor:
    """Extract navigable and provenance links from Markdown text."""

    @classmethod
    def extract(
        cls,
        kb_id: int,
        from_path: str,
        markdown: str,
        from_page_id: int | None = None,
    ) -> list[WikiLink]:
        links: list[WikiLink] = []

        for match in _MARKDOWN_LINK_RE.finditer(markdown):
            label = match.group(1).strip()
            target = match.group(2).strip()
            if not label or not target:
                continue
            if cls._should_ignore_markdown_target(target):
                continue

            links.append(
                WikiLink(
                    kb_id=kb_id,
                    from_page_id=from_page_id,
                    from_path=from_path,
                    to_path=target,
                    link_type="related_to",
                    anchor_text=label,
                    provenance={"kind": "markdown_link"},
                )
            )

        for match in _SOURCE_MARKER_RE.finditer(markdown):
            marker_body = match.group(1).strip()
            if not marker_body:
                continue
            target = f"source:{marker_body}"
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

    @staticmethod
    def _should_ignore_markdown_target(target: str) -> bool:
        return _URI_SCHEME_RE.match(target) is not None or target.startswith("#")
