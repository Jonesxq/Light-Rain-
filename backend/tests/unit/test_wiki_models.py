import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Column, Integer, MetaData, Table, create_engine, inspect
from sqlmodel import SQLModel, select

from app.models.knowledge import KnowledgeBase
from app.models.wiki import WikiLink

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
            assert (
                _migration_foreign_key_ondelete(inspector, table_name, "kb_id")
                == "CASCADE"
            )

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


@pytest.mark.asyncio
async def test_wiki_crud_roundtrip(db_session, test_user_verified):
    from app.crud.wiki import wiki_crud

    kb = KnowledgeBase(
        user_id=test_user_verified.id,
        name="Wiki CRUD KB",
        description="Exercises wiki CRUD helpers",
    )
    db_session.add(kb)
    await db_session.commit()
    await db_session.refresh(kb)

    page = await wiki_crud.upsert_page(
        db_session,
        kb_id=kb.id,
        path="index.md",
        title="Index",
        page_type="overview",
        content_hash="hash-1",
        provenance={"source": "test"},
    )
    assert page.id is not None
    assert page.path == "index.md"

    updated_page = await wiki_crud.upsert_page(
        db_session,
        kb_id=kb.id,
        path="index.md",
        title="Index Updated",
        page_type="overview",
        content_hash="hash-2",
        status="active",
    )
    assert updated_page.id == page.id
    assert updated_page.title == "Index Updated"
    assert updated_page.content_hash == "hash-2"

    deleted_page = await wiki_crud.upsert_page(
        db_session,
        kb_id=kb.id,
        path="deleted.md",
        title="Deleted",
        page_type="note",
        content_hash="hash-deleted",
        status="deleted",
    )
    assert deleted_page.status == "deleted"

    revision = await wiki_crud.create_revision(
        db_session,
        page_id=page.id,
        kb_id=kb.id,
        path="index.md",
        content_hash="hash-2",
        content_snapshot="# Index",
        change_reason="initial snapshot",
        provenance={"source": "test"},
    )
    assert revision.id is not None

    found_by_path = await wiki_crud.get_page_by_path(db_session, kb.id, "index.md")
    found_by_id = await wiki_crud.get_page(db_session, kb.id, page.id)
    assert found_by_path.id == page.id
    assert found_by_id.id == page.id

    active_pages = await wiki_crud.list_pages(db_session, kb.id)
    assert [item.path for item in active_pages] == ["index.md"]

    revisions = await wiki_crud.list_revisions(db_session, page.id)
    assert [item.content_snapshot for item in revisions] == ["# Index"]

    patch = await wiki_crud.create_patch(
        db_session,
        kb_id=kb.id,
        page_id=page.id,
        target_path="index.md",
        operation="append",
        question="What changed?",
        answer="A snapshot was added.",
        patch_markdown="## Update",
        rationale="test coverage",
        confidence=0.75,
        provenance={"source": "test"},
    )
    assert patch.status == "pending"

    patches = await wiki_crud.list_patches(db_session, kb.id, status="pending")
    assert [item.id for item in patches] == [patch.id]

    await wiki_crud.replace_links(
        db_session,
        kb_id=kb.id,
        from_path="index.md",
        links=[
            WikiLink(
                kb_id=kb.id,
                from_page_id=page.id,
                from_path="index.md",
                to_page_id=None,
                to_path="guide.md",
                link_type="related_to",
                anchor_text="Guide",
                provenance={"source": "test"},
            )
        ],
    )
    await wiki_crud.replace_links(
        db_session,
        kb_id=kb.id,
        from_path="index.md",
        links=[
            WikiLink(
                kb_id=kb.id,
                from_page_id=page.id,
                from_path="index.md",
                to_page_id=None,
                to_path="faq.md",
                link_type="related_to",
                anchor_text="FAQ",
            )
        ],
    )
    link_rows = (
        (
            await db_session.execute(
                select(WikiLink).where(
                    WikiLink.kb_id == kb.id,
                    WikiLink.from_path == "index.md",
                )
            )
        )
        .scalars()
        .all()
    )
    assert [item.to_path for item in link_rows] == ["faq.md"]

    run = await wiki_crud.create_run(
        db_session,
        kb_id=kb.id,
        run_type="compile",
        status="succeeded",
        metrics={"pages": 1},
    )
    assert run.finished_at is not None
    assert run.metrics == {"pages": 1}
