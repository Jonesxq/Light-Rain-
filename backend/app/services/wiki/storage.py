"""Path-safe Markdown storage for Wiki-RAG pages."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path, PurePosixPath

from app.core.config import settings

PROJECT_ROOT = Path(__file__).resolve().parents[4]


class WikiStorage:
    """Read and write Markdown wiki pages under per-knowledge-base roots."""

    def __init__(self, root_dir: str | Path | None = None) -> None:
        if root_dir is None:
            configured_root = Path(settings.wiki.WIKI_STORAGE_DIR)
            self.root_dir = (
                configured_root
                if configured_root.is_absolute()
                else PROJECT_ROOT / configured_root
            )
            return

        self.root_dir = Path(root_dir)

    def kb_root(self, kb_id: int) -> Path:
        return self.root_dir / f"kb_{int(kb_id)}"

    def _validated_kb_root(self, kb_id: int) -> Path:
        storage_root = self.root_dir.resolve()
        logical_kb_root = self.kb_root(kb_id)
        expected_relative_root = Path(f"kb_{int(kb_id)}")

        try:
            relative_root = logical_kb_root.relative_to(self.root_dir)
        except ValueError as exc:
            raise ValueError("Wiki knowledge-base root escapes the storage root") from exc

        if relative_root != expected_relative_root:
            raise ValueError("Wiki knowledge-base root must be directly under storage root")

        is_junction = getattr(logical_kb_root, "is_junction", None)
        if logical_kb_root.is_symlink() or (is_junction is not None and is_junction()):
            raise ValueError("Wiki knowledge-base root cannot be a symlink or junction")

        if not logical_kb_root.exists():
            return logical_kb_root

        resolved_kb_root = logical_kb_root.resolve()
        if not resolved_kb_root.is_relative_to(storage_root):
            raise ValueError("Wiki knowledge-base root escapes the storage root")

        return logical_kb_root

    def normalize_page_path(self, page_path: str) -> str:
        normalized = str(page_path).strip().replace("\\", "/")
        if not normalized:
            raise ValueError("Wiki page path cannot be empty")
        if ":" in normalized:
            raise ValueError("Wiki page path cannot contain drive prefixes or colons")
        if normalized.startswith("/"):
            raise ValueError("Wiki page path must be relative")

        parts = normalized.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise ValueError("Wiki page path cannot contain empty, dot, or parent segments")

        posix_path = PurePosixPath(*parts)
        if posix_path.suffix != ".md":
            raise ValueError("Wiki page path must end with .md")

        return posix_path.as_posix()

    def resolve_page_path(self, kb_id: int, page_path: str) -> Path:
        safe_page_path = self.normalize_page_path(page_path)
        kb_root = self._validated_kb_root(kb_id)
        resolved_kb_root = kb_root.resolve()
        resolved_path = (kb_root / safe_page_path).resolve()

        if not resolved_path.is_relative_to(resolved_kb_root):
            raise ValueError("Wiki page path escapes the knowledge-base root")

        return resolved_path

    def read_page(self, kb_id: int, page_path: str) -> str:
        return self.resolve_page_path(kb_id, page_path).read_text(
            encoding="utf-8",
            newline="",
        )

    def page_exists(self, kb_id: int, page_path: str) -> bool:
        return self.resolve_page_path(kb_id, page_path).is_file()

    def write_page(self, kb_id: int, page_path: str, content: str) -> Path:
        target_path = self.resolve_page_path(kb_id, page_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        temp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                newline="",
                delete=False,
                dir=target_path.parent,
                prefix=f".{target_path.name}.",
                suffix=".tmp",
            ) as temp_file:
                temp_path = temp_file.name
                temp_file.write(content)
                temp_file.flush()
                os.fsync(temp_file.fileno())

            os.replace(temp_path, target_path)
            temp_path = None
        finally:
            if temp_path is not None:
                Path(temp_path).unlink(missing_ok=True)

        return target_path

    def list_markdown_pages(self, kb_id: int) -> list[str]:
        kb_root = self._validated_kb_root(kb_id)
        if not kb_root.exists():
            return []

        resolved_root = kb_root.resolve()
        pages: list[str] = []
        for path in kb_root.rglob("*.md"):
            if not path.is_file():
                continue
            resolved_path = path.resolve()
            if not resolved_path.is_relative_to(resolved_root):
                continue
            pages.append(resolved_path.relative_to(resolved_root).as_posix())

        return sorted(pages)

    def content_hash(self, content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()
