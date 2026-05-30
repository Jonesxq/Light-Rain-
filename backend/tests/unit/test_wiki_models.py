import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Column, Integer, MetaData, Table, create_engine, inspect
from sqlmodel import SQLModel

WIKI_TABLE_NAMES = {
    "wiki_pages",
    "wiki_page_revisions",
    "wiki_patches",
    "wiki_links",
    "wiki_runs",
}


def _wiki_tables():
    import app.models.wiki  # noqa: F401

    return SQLModel.metadata.tables


def _foreign_key_ondelete(table_name: str, column_name: str) -> str | None:
    table = _wiki_tables()[table_name]
    foreign_keys = list(table.columns[column_name].foreign_keys)

    assert len(foreign_keys) == 1
    return foreign_keys[0].ondelete


def _load_wiki_migration():
    migration_path = (
        Path(__file__).parents[2]
        / "alembic"
        / "versions"
        / "h1i2j3k4l5m6_add_wiki_tables.py"
    )
    spec = importlib.util.spec_from_file_location(
        "wiki_migration_under_test", migration_path
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


def _run_migration_operation(migration_module, connection, operation_name: str):
    context = MigrationContext.configure(connection)
    operations = Operations(context)
    original_op = migration_module.op

    migration_module.op = operations
    try:
        getattr(migration_module, operation_name)()
    finally:
        migration_module.op = original_op


def _create_minimum_migration_parent_tables(connection):
    metadata = MetaData()
    Table("knowledge_bases", metadata, Column("id", Integer, primary_key=True))
    Table("kb_documents", metadata, Column("id", Integer, primary_key=True))
    Table("chat_messages", metadata, Column("id", Integer, primary_key=True))

    metadata.create_all(connection)


def _migration_foreign_key_ondelete(inspector, table_name: str, column_name: str):
    matches = [
        foreign_key
        for foreign_key in inspector.get_foreign_keys(table_name)
        if foreign_key["constrained_columns"] == [column_name]
    ]

    assert len(matches) == 1
    return (matches[0].get("options") or {}).get("ondelete")


def test_wiki_tables_are_registered_in_metadata():
    table_names = set(_wiki_tables().keys())

    assert WIKI_TABLE_NAMES.issubset(table_names)


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


def test_wiki_migration_creates_and_drops_expected_schema():
    migration_module = _load_wiki_migration()
    engine = create_engine("sqlite:///:memory:")

    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        _create_minimum_migration_parent_tables(connection)

        _run_migration_operation(migration_module, connection, "upgrade")

        inspector = inspect(connection)
        table_names = set(inspector.get_table_names())
        assert WIKI_TABLE_NAMES.issubset(table_names)

        wiki_page_indexes = {
            index["name"]: index for index in inspector.get_indexes("wiki_pages")
        }
        kb_path_index = wiki_page_indexes["ix_wiki_pages_kb_path"]
        assert bool(kb_path_index["unique"]) is True
        assert kb_path_index["column_names"] == ["kb_id", "path"]

        for table_name in WIKI_TABLE_NAMES:
            assert _migration_foreign_key_ondelete(
                inspector, table_name, "kb_id"
            ) == "CASCADE"

        revision_columns = {
            column["name"]: column
            for column in inspector.get_columns("wiki_page_revisions")
        }
        assert revision_columns["change_reason"]["nullable"] is False

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
            assert (
                _migration_foreign_key_ondelete(inspector, table_name, column_name)
                == ondelete
            )

        _run_migration_operation(migration_module, connection, "downgrade")

        inspector = inspect(connection)
        assert WIKI_TABLE_NAMES.isdisjoint(inspector.get_table_names())

    engine.dispose()
