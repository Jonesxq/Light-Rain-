import pytest
from pathlib import Path

from app.services.wiki.storage import WikiStorage
from app.services.wiki import storage as storage_module


def _create_dir_symlink_or_skip(link_path, target_path):
    try:
        link_path.symlink_to(target_path, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlinks are unavailable on this platform: {exc}")


def test_resolve_page_path_rejects_parent_traversal(tmp_path):
    storage = WikiStorage(root_dir=tmp_path)

    with pytest.raises(ValueError):
        storage.resolve_page_path(1, "../secret.md")


def test_resolve_page_path_rejects_windows_drive_path(tmp_path):
    storage = WikiStorage(root_dir=tmp_path)

    with pytest.raises(ValueError):
        storage.resolve_page_path(1, "C:/secret.md")


@pytest.mark.parametrize(
    "page_path",
    [
        "/abs.md",
        "C:foo.md",
        "page.md:ads",
        "sources//a.md",
        "sources/./a.md",
        "sources/../a.md",
        "sources/a.md/",
    ],
)
def test_resolve_page_path_rejects_unsafe_boundaries(tmp_path, page_path):
    storage = WikiStorage(root_dir=tmp_path)

    with pytest.raises(ValueError):
        storage.resolve_page_path(1, page_path)


def test_write_page_and_read_page_roundtrip_inside_kb_root(tmp_path):
    storage = WikiStorage(root_dir=tmp_path)
    content = "# API\nBody"

    storage.write_page(7, "sources/12-api.md", content)

    assert storage.read_page(7, "sources/12-api.md") == content
    assert (tmp_path / "kb_7" / "sources" / "12-api.md").exists()


def test_default_relative_storage_dir_is_project_root_relative(monkeypatch, tmp_path):
    monkeypatch.setattr(storage_module.settings.wiki, "WIKI_STORAGE_DIR", "storage/wiki")
    monkeypatch.chdir(tmp_path)

    storage = WikiStorage()

    project_root = Path(__file__).resolve().parents[3]
    assert storage.root_dir.resolve() == (project_root / "storage" / "wiki").resolve()


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


def test_write_page_rejects_kb_root_symlink_escape(tmp_path):
    storage = WikiStorage(root_dir=tmp_path / "storage")
    storage.root_dir.mkdir()
    outside_root = tmp_path / "outside"
    outside_root.mkdir()
    _create_dir_symlink_or_skip(storage.kb_root(1), outside_root)

    with pytest.raises(ValueError):
        storage.write_page(1, "escaped.md", "nope")

    assert not (outside_root / "escaped.md").exists()


def test_list_markdown_pages_rejects_kb_root_symlink_escape(tmp_path):
    storage = WikiStorage(root_dir=tmp_path / "storage")
    storage.root_dir.mkdir()
    outside_root = tmp_path / "outside"
    outside_root.mkdir()
    (outside_root / "external.md").write_text("outside", encoding="utf-8")
    _create_dir_symlink_or_skip(storage.kb_root(1), outside_root)

    with pytest.raises(ValueError):
        storage.list_markdown_pages(1)


def test_backslash_paths_are_normalized_to_posix_paths(tmp_path):
    storage = WikiStorage(root_dir=tmp_path)

    storage.write_page(2, r"sources\12-api.md", "# API")

    assert storage.read_page(2, "sources/12-api.md") == "# API"
    assert (tmp_path / "kb_2" / "sources" / "12-api.md").exists()


def test_non_markdown_page_paths_are_rejected(tmp_path):
    storage = WikiStorage(root_dir=tmp_path)

    with pytest.raises(ValueError):
        storage.resolve_page_path(1, "sources/12-api.txt")
