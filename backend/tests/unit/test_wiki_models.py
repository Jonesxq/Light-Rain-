from sqlmodel import SQLModel


def test_wiki_tables_are_registered_in_metadata():
    import app.models.wiki  # noqa: F401

    table_names = set(SQLModel.metadata.tables.keys())

    assert "wiki_pages" in table_names
    assert "wiki_page_revisions" in table_names
    assert "wiki_patches" in table_names
    assert "wiki_links" in table_names
    assert "wiki_runs" in table_names
