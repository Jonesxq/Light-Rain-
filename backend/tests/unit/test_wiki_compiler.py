import json
from pathlib import Path

import pytest
from sqlmodel import select

from app.models.knowledge import DocStatus, Document, KnowledgeBase
from app.models.wiki import WikiPage, WikiPageRevision, WikiPatch, WikiRun
from app.services.wiki.compiler import WikiCompiler
from app.services.wiki.markdown import build_markdown_page, extract_frontmatter
from app.services.wiki.service import WikiService
from app.services.wiki.storage import WikiStorage


async def _create_kb(db_session, test_user_verified, name="KB"):
    kb = KnowledgeBase(user_id=test_user_verified.id, name=name)
    db_session.add(kb)
    await db_session.commit()
    await db_session.refresh(kb)
    return kb


async def _create_document(
    db_session,
    *,
    kb_id: int,
    file_path: Path,
    file_name: str = "API Doc.md",
    status: DocStatus = DocStatus.COMPLETED,
):
    doc = Document(
        kb_id=kb_id,
        file_name=file_name,
        file_path=str(file_path),
        file_type=".md",
        file_size=123,
        status=status,
        chunk_count=2,
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)
    return doc


def _write_chunks(file_path: Path):
    chunks = [
        {
            "chunk_index": 0,
            "content": "Milvus provides vector search.",
            "metadata": {"section": "Overview"},
        },
        {
            "chunk_index": 1,
            "content": "Hybrid retrieval combines sparse and dense signals.",
            "metadata": {"section": "Retrieval"},
        },
    ]
    file_path.write_text("# API Doc\n", encoding="utf-8")
    sidecar = Path(f"{file_path}.chunks.jsonl")
    sidecar.write_text(
        "\n".join(json.dumps(chunk) for chunk in chunks) + "\n\n",
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_compile_document_writes_wiki_pages_and_syncs_database(
    db_session,
    test_user_verified,
    tmp_path,
):
    kb = await _create_kb(db_session, test_user_verified)
    source_file = tmp_path / "API Doc.md"
    _write_chunks(source_file)
    doc = await _create_document(db_session, kb_id=kb.id, file_path=source_file)
    storage = WikiStorage(root_dir=tmp_path / "wiki")
    compiler = WikiCompiler(storage=storage)

    result = await compiler.compile_document(db_session, kb_id=kb.id, doc_id=doc.id)

    source_path = f"sources/{doc.id}-api-doc-md.md"
    assert result.kb_id == kb.id
    assert result.doc_id == doc.id
    assert result.pages_changed >= 4
    assert result.patches_created >= 1
    assert result.warnings == []
    assert storage.page_exists(kb.id, "schema.md")
    assert storage.page_exists(kb.id, "index.md")
    assert storage.page_exists(kb.id, "log.md")
    assert storage.page_exists(kb.id, source_path)

    source_markdown = storage.read_page(kb.id, source_path)
    frontmatter, _body = extract_frontmatter(source_markdown)
    assert frontmatter["page_type"] == "source"
    assert frontmatter["doc_id"] == doc.id
    assert frontmatter["chunk_count"] == 2
    assert frontmatter["source_count"] == 2
    assert "[source:doc=" in source_markdown
    assert f"chunk_index=0]" in source_markdown
    assert "Milvus provides vector search." in source_markdown

    index_markdown = storage.read_page(kb.id, "index.md")
    assert f"]({source_path})" in index_markdown
    log_markdown = storage.read_page(kb.id, "log.md")
    log_frontmatter, _log_body = extract_frontmatter(log_markdown)
    assert log_frontmatter["page_type"] == "log"
    assert log_frontmatter["title"] == "Log"
    assert f"ingest | doc_id={doc.id} | {doc.file_name}" in log_markdown

    page_rows = (
        (
            await db_session.execute(
                select(WikiPage).where(WikiPage.kb_id == kb.id)
            )
        )
        .scalars()
        .all()
    )
    assert {"schema.md", "index.md", "log.md", source_path}.issubset(
        {page.path for page in page_rows}
    )

    revisions = (
        (
            await db_session.execute(
                select(WikiPageRevision).where(WikiPageRevision.kb_id == kb.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(revisions) >= 4

    pending_patches = (
        (
            await db_session.execute(
                select(WikiPatch).where(
                    WikiPatch.kb_id == kb.id,
                    WikiPatch.status == "pending",
                )
            )
        )
        .scalars()
        .all()
    )
    assert pending_patches
    assert pending_patches[0].target_path == "topics/vector-search.md"
    assert pending_patches[0].operation == "create"

    runs = (
        (
            await db_session.execute(
                select(WikiRun).where(
                    WikiRun.kb_id == kb.id,
                    WikiRun.doc_id == doc.id,
                    WikiRun.run_type == "ingest_doc",
                    WikiRun.status == "succeeded",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(runs) == 1
    assert runs[0].metrics["pages_changed"] == result.pages_changed


@pytest.mark.asyncio
async def test_compile_document_appends_existing_log(
    db_session,
    test_user_verified,
    tmp_path,
):
    kb = await _create_kb(db_session, test_user_verified)
    source_file = tmp_path / "API Doc.md"
    _write_chunks(source_file)
    doc = await _create_document(db_session, kb_id=kb.id, file_path=source_file)
    storage = WikiStorage(root_dir=tmp_path / "wiki")
    storage.write_page(
        kb.id,
        "log.md",
        build_markdown_page(
            {"title": "Log", "page_type": "log", "status": "active"},
            "Log",
            [("Entries", "Existing entry")],
        ),
    )
    compiler = WikiCompiler(storage=storage)

    await compiler.compile_document(db_session, kb_id=kb.id, doc_id=doc.id)

    log_markdown = storage.read_page(kb.id, "log.md")
    log_frontmatter, _log_body = extract_frontmatter(log_markdown)
    assert log_frontmatter["page_type"] == "log"
    assert log_frontmatter["title"] == "Log"
    assert "Existing entry" in log_markdown
    assert f"ingest | doc_id={doc.id} | {doc.file_name}" in log_markdown


@pytest.mark.asyncio
async def test_compile_document_rejects_non_completed_document(
    db_session,
    test_user_verified,
    tmp_path,
):
    kb = await _create_kb(db_session, test_user_verified)
    doc = await _create_document(
        db_session,
        kb_id=kb.id,
        file_path=tmp_path / "API Doc.md",
        status=DocStatus.PROCESSING,
    )
    compiler = WikiCompiler(storage=WikiStorage(root_dir=tmp_path / "wiki"))

    with pytest.raises(ValueError, match="Document is not completed"):
        await compiler.compile_document(db_session, kb_id=kb.id, doc_id=doc.id)


@pytest.mark.asyncio
async def test_compile_document_rejects_missing_document(
    db_session,
    test_user_verified,
    tmp_path,
):
    kb = await _create_kb(db_session, test_user_verified)
    compiler = WikiCompiler(storage=WikiStorage(root_dir=tmp_path / "wiki"))

    with pytest.raises(ValueError, match="Document not found"):
        await compiler.compile_document(db_session, kb_id=kb.id, doc_id=999999)


@pytest.mark.asyncio
async def test_compile_document_rejects_wrong_kb(
    db_session,
    test_user_verified,
    tmp_path,
):
    kb = await _create_kb(db_session, test_user_verified, name="KB")
    other_kb = await _create_kb(db_session, test_user_verified, name="Other KB")
    doc = await _create_document(
        db_session,
        kb_id=other_kb.id,
        file_path=tmp_path / "API Doc.md",
    )
    compiler = WikiCompiler(storage=WikiStorage(root_dir=tmp_path / "wiki"))

    with pytest.raises(ValueError, match="Document not found"):
        await compiler.compile_document(db_session, kb_id=kb.id, doc_id=doc.id)


@pytest.mark.asyncio
async def test_wiki_service_compile_document_delegates_to_compiler(
    db_session,
    test_user_verified,
    tmp_path,
):
    kb = await _create_kb(db_session, test_user_verified)
    source_file = tmp_path / "API Doc.md"
    _write_chunks(source_file)
    doc = await _create_document(db_session, kb_id=kb.id, file_path=source_file)
    storage = WikiStorage(root_dir=tmp_path / "wiki")
    service = WikiService(storage=storage)

    result = await service.compile_document(db_session, kb_id=kb.id, doc_id=doc.id)

    assert result.pages_changed >= 4
    assert storage.page_exists(kb.id, f"sources/{doc.id}-api-doc-md.md")
