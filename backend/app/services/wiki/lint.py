"""Lint checks for filesystem-backed Wiki-RAG Markdown pages."""

from __future__ import annotations

import re
from typing import Iterable

from app.models.wiki import WikiPage
from app.services.wiki.links import WikiLinkExtractor
from app.services.wiki.markdown import extract_frontmatter
from app.services.wiki.storage import WikiStorage
from app.services.wiki.types import PAGE_INDEX, PAGE_LOG, WikiLintWarning


_LOG_HEADING_RE = re.compile(
    r"^## \[\d{4}-\d{2}-\d{2} \d{2}:\d{2}\] [A-Za-z0-9_-]+(?: \| .+)?$"
)


class WikiLint:
    """Run non-fatal audit checks over wiki Markdown files."""

    def __init__(self, storage: WikiStorage) -> None:
        self.storage = storage

    def lint_files(
        self,
        kb_id: int,
        db_pages: Iterable[WikiPage],
    ) -> list[WikiLintWarning]:
        warnings: list[WikiLintWarning] = []
        file_paths = set(self.storage.list_markdown_pages(kb_id))
        db_page_list = list(db_pages)
        db_paths = {page.path for page in db_page_list}

        for path in sorted(file_paths):
            markdown = self.storage.read_page(kb_id, path)
            frontmatter, body = extract_frontmatter(markdown)

            if path != PAGE_LOG and not frontmatter:
                warnings.append(
                    WikiLintWarning(
                        code="missing_frontmatter",
                        message=f"Wiki page {path} is missing frontmatter",
                        path=path,
                    )
                )

            if db_page_list and path not in db_paths:
                warnings.append(
                    WikiLintWarning(
                        code="missing_db_row",
                        message=f"Wiki page file {path} has no database row",
                        path=path,
                    )
                )

            if path == PAGE_INDEX:
                warnings.extend(self._lint_index_links(kb_id, markdown, path))
            elif path == PAGE_LOG:
                warnings.extend(self._lint_log_headings(body, path))

        for page in db_page_list:
            if page.path not in file_paths:
                warnings.append(
                    WikiLintWarning(
                        code="missing_page_file",
                        message=f"Database wiki page {page.path} has no Markdown file",
                        path=page.path,
                    )
                )

        return warnings

    def _lint_index_links(
        self,
        kb_id: int,
        markdown: str,
        path: str,
    ) -> list[WikiLintWarning]:
        warnings: list[WikiLintWarning] = []
        for link in WikiLinkExtractor.extract(kb_id, path, markdown):
            if link.link_type != "related_to":
                continue

            target_path = self._strip_fragment(link.to_path)
            try:
                exists = self.storage.page_exists(kb_id, target_path)
            except ValueError as exc:
                warnings.append(
                    WikiLintWarning(
                        code="unsafe_index_link",
                        message=f"Index link {link.to_path} is unsafe: {exc}",
                        path=path,
                    )
                )
                continue

            if not exists:
                warnings.append(
                    WikiLintWarning(
                        code="broken_index_link",
                        message=f"Index link {link.to_path} points to a missing page",
                        path=path,
                    )
                )

        return warnings

    def _lint_log_headings(self, body: str, path: str) -> list[WikiLintWarning]:
        warnings: list[WikiLintWarning] = []
        for line in body.splitlines():
            if not line.startswith("## "):
                continue
            if _LOG_HEADING_RE.fullmatch(line.strip()) is None:
                warnings.append(
                    WikiLintWarning(
                        code="malformed_log_heading",
                        message=f"Log heading is not parseable: {line.strip()}",
                        path=path,
                    )
                )
        return warnings

    @staticmethod
    def _strip_fragment(target_path: str) -> str:
        return target_path.split("#", 1)[0].strip()
