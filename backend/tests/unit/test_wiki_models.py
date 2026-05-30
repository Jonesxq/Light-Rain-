from sqlmodel import SQLModel


def _wiki_tables():
    import app.models.wiki  # noqa: F401

    return SQLModel.metadata.tables


def _foreign_key_ondelete(table_name: str, column_name: str) -> str | None:
    table = _wiki_tables()[table_name]
    foreign_keys = list(table.columns[column_name].foreign_keys)

    assert len(foreign_keys) == 1
    return foreign_keys[0].ondelete


def test_wiki_tables_are_registered_in_metadata():
    table_names = set(_wiki_tables().keys())

    assert "wiki_pages" in table_names
    assert "wiki_page_revisions" in table_names
    assert "wiki_patches" in table_names
    assert "wiki_links" in table_names
    assert "wiki_runs" in table_names


def test_wiki_pages_have_unique_kb_path_index():
    wiki_pages = _wiki_tables()["wiki_pages"]

    kb_path_index = next(
        index for index in wiki_pages.indexes if index.name == "ix_wiki_pages_kb_path"
    )

    assert kb_path_index.unique is True
    assert [column.name for column in kb_path_index.columns] == ["kb_id", "path"]


def test_wiki_tables_cascade_when_knowledge_base_is_deleted():
    for table_name in (
        "wiki_pages",
        "wiki_page_revisions",
        "wiki_patches",
        "wiki_links",
        "wiki_runs",
    ):
        assert _foreign_key_ondelete(table_name, "kb_id") == "CASCADE"


def test_wiki_page_revision_change_reason_is_required():
    wiki_page_revisions = _wiki_tables()["wiki_page_revisions"]

    assert wiki_page_revisions.columns["change_reason"].nullable is False


def test_wiki_optional_foreign_keys_use_expected_delete_actions():
    expected_ondelete = {
        ("wiki_pages", "source_doc_id"): "SET NULL",
        ("wiki_page_revisions", "page_id"): "SET NULL",
        ("wiki_patches", "page_id"): "SET NULL",
        ("wiki_patches", "created_by_message_id"): "SET NULL",
        ("wiki_links", "from_page_id"): "CASCADE",
        ("wiki_links", "to_page_id"): "SET NULL",
        ("wiki_runs", "doc_id"): "SET NULL",
    }

    for (table_name, column_name), ondelete in expected_ondelete.items():
        assert _foreign_key_ondelete(table_name, column_name) == ondelete
