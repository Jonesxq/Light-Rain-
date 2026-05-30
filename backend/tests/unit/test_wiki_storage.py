import pytest

from app.services.wiki.storage import WikiStorage


def test_resolve_page_path_rejects_parent_traversal(tmp_path):
    storage = WikiStorage(root_dir=tmp_path)

    with pytest.raises(ValueError):
        storage.resolve_page_path(1, "../secret.md")


def test_resolve_page_path_rejects_windows_drive_path(tmp_path):
    storage = WikiStorage(root_dir=tmp_path)

    with pytest.raises(ValueError):
        storage.resolve_page_path(1, "C:/secret.md")


def test_write_page_and_read_page_roundtrip_inside_kb_root(tmp_path):
    storage = WikiStorage(root_dir=tmp_path)
    content = "# API\nBody"

    storage.write_page(7, "sources/12-api.md", content)

    assert storage.read_page(7, "sources/12-api.md") == content
    assert (tmp_path / "kb_7" / "sources" / "12-api.md").exists()


def test_content_hash_uses_sha256_hex_digest():
    storage = WikiStorage(root_dir="unused")

    assert storage.content_hash("alpha") != storage.content_hash("beta")
    assert len(storage.content_hash("alpha")) == 64


def test_list_markdown_pages_returns_sorted_posix_paths_only(tmp_path):
    storage = WikiStorage(root_dir=tmp_path)
    storage.write_page(1, "zeta.md", "z")
    storage.write_page(1, "sources/b.md", "b")
    storage.write_page(1, "sources/a.md", "a")
    (tmp_path / "kb_1" / "notes.txt").write_text("nope", encoding="utf-8")

    assert storage.list_markdown_pages(1) == [
        "sources/a.md",
        "sources/b.md",
        "zeta.md",
    ]


def test_backslash_paths_are_normalized_to_posix_paths(tmp_path):
    storage = WikiStorage(root_dir=tmp_path)

    storage.write_page(2, r"sources\12-api.md", "# API")

    assert storage.read_page(2, "sources/12-api.md") == "# API"
    assert (tmp_path / "kb_2" / "sources" / "12-api.md").exists()


def test_non_markdown_page_paths_are_rejected(tmp_path):
    storage = WikiStorage(root_dir=tmp_path)

    with pytest.raises(ValueError):
        storage.resolve_page_path(1, "sources/12-api.txt")
