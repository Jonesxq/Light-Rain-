from datetime import datetime

from app.models.wiki import WikiPage
from app.services.wiki.links import WikiLinkExtractor
from app.services.wiki.lint import WikiLint
from app.services.wiki.markdown import build_frontmatter, build_log_heading
from app.services.wiki.storage import WikiStorage


def _warning_codes(warnings):
    return {warning.code for warning in warnings}


def test_link_extractor_finds_markdown_link_and_source_marker():
    markdown = """
See [ Guide ]( guides/start.md ) and [source:doc=12 chunk=3].
Ignore ![Image](image.md), [external](https://example.com), and [anchor](#local).
"""

    links = WikiLinkExtractor.extract(
        kb_id=7,
        from_path="index.md",
        markdown=markdown,
        from_page_id=99,
    )

    assert [(link.to_path, link.link_type, link.anchor_text) for link in links] == [
        ("guides/start.md", "related_to", "Guide"),
        ("source:doc=12 chunk=3", "cites", "source:doc=12 chunk=3"),
    ]
    assert links[0].kb_id == 7
    assert links[0].from_path == "index.md"
    assert links[0].from_page_id == 99
    assert links[0].provenance == {"kind": "markdown_link"}
    assert links[1].provenance == {"kind": "source_marker"}


def test_lint_reports_missing_frontmatter_broken_index_link_and_malformed_log_heading(
    tmp_path,
):
    storage = WikiStorage(root_dir=tmp_path)
    storage.write_page(1, "index.md", build_frontmatter({"title": "Index"}) + "\n[Missing](missing.md)")
    storage.write_page(1, "topic.md", "# Topic without frontmatter")
    storage.write_page(1, "log.md", "## not parseable\n\nBody")

    warnings = WikiLint(storage).lint_files(kb_id=1, db_pages=[])

    codes = _warning_codes(warnings)
    assert "missing_frontmatter" in codes
    assert "broken_index_link" in codes
    assert "malformed_log_heading" in codes


def test_lint_ignores_external_anchor_and_image_index_links(tmp_path):
    storage = WikiStorage(root_dir=tmp_path)
    storage.write_page(
        1,
        "index.md",
        build_frontmatter({"title": "Index"})
        + "\n[External](https://example.com)\n[Anchor](#local)\n![Image](missing.md)",
    )

    warnings = WikiLint(storage).lint_files(kb_id=1, db_pages=[])

    assert _warning_codes(warnings) == set()


def test_lint_reports_db_row_file_mismatches_when_db_pages_are_present(tmp_path):
    storage = WikiStorage(root_dir=tmp_path)
    storage.write_page(1, "index.md", build_frontmatter({"title": "Index"}) + "\n# Index")
    storage.write_page(1, "orphan.md", build_frontmatter({"title": "Orphan"}) + "\n# Orphan")
    db_pages = [
        WikiPage(kb_id=1, path="index.md", title="Index", page_type="index"),
        WikiPage(kb_id=1, path="missing.md", title="Missing", page_type="topic"),
    ]

    warnings = WikiLint(storage).lint_files(kb_id=1, db_pages=db_pages)

    assert "missing_db_row" in _warning_codes(warnings)
    assert "missing_page_file" in _warning_codes(warnings)


def test_lint_reports_unsafe_index_link(tmp_path):
    storage = WikiStorage(root_dir=tmp_path)
    storage.write_page(
        1,
        "index.md",
        build_frontmatter({"title": "Index"}) + "\n[Unsafe](../secret.md)",
    )

    warnings = WikiLint(storage).lint_files(kb_id=1, db_pages=[])

    assert "unsafe_index_link" in _warning_codes(warnings)


def test_lint_accepts_parseable_log_heading(tmp_path):
    storage = WikiStorage(root_dir=tmp_path)
    storage.write_page(
        1,
        "log.md",
        build_log_heading(
            event_time=datetime(2026, 5, 30, 9, 15),
            event_type="ingest",
            parts=["doc_id=12"],
        ),
    )

    warnings = WikiLint(storage).lint_files(kb_id=1, db_pages=[])

    assert "malformed_log_heading" not in _warning_codes(warnings)
