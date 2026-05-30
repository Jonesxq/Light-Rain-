from datetime import datetime

from app.services.wiki.markdown import (
    build_frontmatter,
    build_log_heading,
    build_markdown_page,
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


def test_frontmatter_roundtrip_for_bool_float_and_clean_list_items():
    markdown = build_frontmatter(
        {
            "enabled": True,
            "confidence": 0.72,
            "empty": None,
            "tags": [" source ", '"api"'],
        }
    )

    frontmatter, body = extract_frontmatter(markdown)

    assert frontmatter == {
        "enabled": True,
        "confidence": 0.72,
        "tags": ["source", "api"],
    }
    assert body == ""


def test_log_heading_is_parseable_shape():
    heading = build_log_heading(
        event_time=datetime(2026, 5, 30, 9, 15),
        event_type="ingest",
        parts=["doc_id=12", "API Doc"],
    )

    assert heading == "## [2026-05-30 09:15] ingest | doc_id=12 | API Doc"


def test_build_markdown_page_combines_frontmatter_heading_and_sections():
    markdown = build_markdown_page(
        {"title": "API Doc", "page_type": "source"},
        "API Doc",
        [("Summary", "Body"), ("Details", "More")],
    )

    assert markdown == (
        "---\n"
        "title: API Doc\n"
        "page_type: source\n"
        "---\n\n"
        "# API Doc\n\n"
        "## Summary\n\n"
        "Body\n\n"
        "## Details\n\n"
        "More\n"
    )
