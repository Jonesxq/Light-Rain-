import json
from pathlib import Path

import pytest
from sqlmodel import select

from app.models.knowledge import DocStatus, Document, KnowledgeBase
from app.models.wiki import WikiPage, WikiPageRevision, WikiPatch, WikiRun
from app.crud.wiki import wiki_crud
from app.services.wiki import compiler as compiler_module
from app.services.wiki.compiler import WikiCompiler
from app.services.wiki.markdown import (
    build_frontmatter,
    build_markdown_page,
    extract_frontmatter,
)
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
    assert "## 来源摘要" in source_markdown
    assert "## 原文片段" in source_markdown
    assert "文档 ID" in source_markdown
    assert "分块数" in source_markdown
    assert "Source Metadata" not in source_markdown
    assert "[source:doc=" in source_markdown
    assert "chunk_index=0]" in source_markdown
    assert "Milvus provides vector search." in source_markdown

    index_markdown = storage.read_page(kb.id, "index.md")
    assert f"]({source_path})" in index_markdown
    log_markdown = storage.read_page(kb.id, "log.md")
    log_frontmatter, _log_body = extract_frontmatter(log_markdown)
    assert log_frontmatter["page_type"] == "log"
    assert log_frontmatter["title"] == "Log"
    assert f"ingest | doc_id={doc.id} | {doc.file_name}" in log_markdown

    page_rows = (
        (await db_session.execute(select(WikiPage).where(WikiPage.kb_id == kb.id)))
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
    assert pending_patches[0].target_path == f"topics/doc-{doc.id}-topic.md"
    assert pending_patches[0].operation == "create"
    assert pending_patches[0].question == "是否将该来源整理成中文主题页？"
    assert "中文主题页候选" in pending_patches[0].answer
    assert "## 来源摘要" in pending_patches[0].patch_markdown
    assert "## 关键要点" in pending_patches[0].patch_markdown
    assert "Milvus provides vector search." in pending_patches[0].patch_markdown
    assert "请审核该来源是否适合沉淀为独立主题页" not in pending_patches[0].patch_markdown

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
async def test_compile_document_index_lists_all_compiled_sources(
    db_session,
    test_user_verified,
    tmp_path,
):
    kb = await _create_kb(db_session, test_user_verified)
    first_file = tmp_path / "中华人民共和国个人信息保护法.md"
    second_file = tmp_path / "中华人民共和国数据安全法.md"
    _write_chunks(first_file)
    _write_chunks(second_file)
    first_doc = await _create_document(
        db_session,
        kb_id=kb.id,
        file_path=first_file,
        file_name="中华人民共和国个人信息保护法.md",
    )
    second_doc = await _create_document(
        db_session,
        kb_id=kb.id,
        file_path=second_file,
        file_name="中华人民共和国数据安全法.md",
    )
    storage = WikiStorage(root_dir=tmp_path / "wiki")
    compiler = WikiCompiler(storage=storage)

    await compiler.compile_document(db_session, kb_id=kb.id, doc_id=first_doc.id)
    await compiler.compile_document(db_session, kb_id=kb.id, doc_id=second_doc.id)

    index_markdown = storage.read_page(kb.id, "index.md")

    assert "中华人民共和国个人信息保护法.md" in index_markdown
    assert "中华人民共和国数据安全法.md" in index_markdown
    assert f"sources/{first_doc.id}-md.md" in index_markdown
    assert f"sources/{second_doc.id}-md.md" in index_markdown
    assert "来源页" in index_markdown
    assert "文档 ID" in index_markdown
    assert "分块数" in index_markdown
    assert "Milvus provides vector search." in index_markdown


@pytest.mark.asyncio
async def test_compile_document_reads_project_root_relative_sidecar_chunks(
    db_session,
    test_user_verified,
    tmp_path,
    monkeypatch,
):
    project_root = tmp_path / "project"
    upload_dir = project_root / "static" / "uploads" / "kb"
    upload_dir.mkdir(parents=True)
    backend_cwd = project_root / "backend"
    backend_cwd.mkdir()
    source_file = upload_dir / "relative.md"
    _write_chunks(source_file)
    monkeypatch.setattr(compiler_module, "PROJECT_ROOT", project_root)
    monkeypatch.chdir(backend_cwd)
    kb = await _create_kb(db_session, test_user_verified)
    doc = await _create_document(
        db_session,
        kb_id=kb.id,
        file_path=Path("static/uploads/kb/relative.md"),
        file_name="relative.md",
    )
    storage = WikiStorage(root_dir=tmp_path / "wiki")
    compiler = WikiCompiler(storage=storage)

    await compiler.compile_document(db_session, kb_id=kb.id, doc_id=doc.id)

    source_markdown = storage.read_page(kb.id, f"sources/{doc.id}-relative-md.md")
    frontmatter, _body = extract_frontmatter(source_markdown)
    assert frontmatter["chunk_count"] == 2
    assert "Milvus provides vector search." in source_markdown
    assert "No chunks found" not in source_markdown


@pytest.mark.asyncio
async def test_compile_document_schema_lists_all_documents_in_chinese(
    db_session,
    test_user_verified,
    tmp_path,
):
    kb = await _create_kb(db_session, test_user_verified)
    first_file = tmp_path / "中华人民共和国个人信息保护法.md"
    second_file = tmp_path / "中华人民共和国数据安全法.md"
    _write_chunks(first_file)
    _write_chunks(second_file)
    first_doc = await _create_document(
        db_session,
        kb_id=kb.id,
        file_path=first_file,
        file_name="中华人民共和国个人信息保护法.md",
    )
    second_doc = await _create_document(
        db_session,
        kb_id=kb.id,
        file_path=second_file,
        file_name="中华人民共和国数据安全法.md",
    )
    storage = WikiStorage(root_dir=tmp_path / "wiki")
    compiler = WikiCompiler(storage=storage)

    await compiler.compile_document(db_session, kb_id=kb.id, doc_id=first_doc.id)
    await compiler.compile_document(db_session, kb_id=kb.id, doc_id=second_doc.id)

    schema_markdown = storage.read_page(kb.id, "schema.md")

    assert "# Wiki 维护协议" in schema_markdown
    assert "## 知识库边界" in schema_markdown
    assert "## 页面类型" in schema_markdown
    assert "## 已上传文档" in schema_markdown
    assert "## 回答流程" in schema_markdown
    assert "## 写回规则" in schema_markdown
    assert "一个 Wiki 只维护当前这一个知识库" in schema_markdown
    assert "先查询当前知识库 Wiki" in schema_markdown
    assert "Wiki 不足以回答时，再进入二阶段 RAG 检索" in schema_markdown
    assert "把高质量答案沉淀回 Wiki" in schema_markdown
    assert "中华人民共和国个人信息保护法.md" in schema_markdown
    assert "中华人民共和国数据安全法.md" in schema_markdown
    assert f"sources/{first_doc.id}-md.md" in schema_markdown
    assert f"sources/{second_doc.id}-md.md" in schema_markdown
    assert "Page Types" not in schema_markdown
    assert "Current Ingest" not in schema_markdown


@pytest.mark.asyncio
async def test_compile_document_does_not_recreate_applied_topic_patch(
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

    await service.compile_document(db_session, kb_id=kb.id, doc_id=doc.id)
    pending_patch = (
        (
            await db_session.execute(
                select(WikiPatch).where(
                    WikiPatch.kb_id == kb.id,
                    WikiPatch.status == "pending",
                    WikiPatch.target_path == f"topics/doc-{doc.id}-topic.md",
                )
            )
        )
        .scalars()
        .one()
    )
    await service.apply_patch(db_session, kb_id=kb.id, patch_id=pending_patch.id)

    result = await service.compile_document(db_session, kb_id=kb.id, doc_id=doc.id)

    pending_patches = (
        (
            await db_session.execute(
                select(WikiPatch).where(
                    WikiPatch.kb_id == kb.id,
                    WikiPatch.status == "pending",
                    WikiPatch.target_path == f"topics/doc-{doc.id}-topic.md",
                )
            )
        )
        .scalars()
        .all()
    )
    assert result.patches_created == 0
    assert pending_patches == []


@pytest.mark.asyncio
async def test_compile_document_refreshes_legacy_placeholder_topic_page(
    db_session,
    test_user_verified,
    tmp_path,
):
    kb = await _create_kb(db_session, test_user_verified)
    source_file = tmp_path / "API Doc.md"
    _write_chunks(source_file)
    doc = await _create_document(db_session, kb_id=kb.id, file_path=source_file)
    storage = WikiStorage(root_dir=tmp_path / "wiki")
    topic_path = f"topics/doc-{doc.id}-topic.md"
    title = f"{doc.file_name} 主题页"
    legacy_markdown = (
        build_frontmatter(
            {
                "title": title,
                "page_type": "topic",
                "status": "active",
                "source_doc_id": doc.id,
                "tags": ["topic", "中文主题页"],
            }
        )
        + "\n\n"
        + f"# {title}\n\n"
        + f"本主题页候选来自 [{doc.file_name}](sources/{doc.id}-api-doc-md.md)。\n\n"
        + "## 待整理要点\n\n"
        + "- 请审核该来源是否适合沉淀为独立主题页。\n"
    )
    storage.write_page(kb.id, topic_path, legacy_markdown)
    await wiki_crud.upsert_page(
        db_session,
        kb_id=kb.id,
        path=topic_path,
        title=title,
        page_type="topic",
        content_hash=storage.content_hash(legacy_markdown),
        source_doc_id=doc.id,
        provenance={"compiler": "wiki", "legacy_placeholder": True},
    )
    compiler = WikiCompiler(storage=storage)

    result = await compiler.compile_document(db_session, kb_id=kb.id, doc_id=doc.id)

    topic_markdown = storage.read_page(kb.id, topic_path)
    assert result.patches_created == 0
    assert "## 来源摘要" in topic_markdown
    assert "## 关键要点" in topic_markdown
    assert "Milvus provides vector search." in topic_markdown
    assert "待整理要点" not in topic_markdown
    assert "请审核该来源是否适合沉淀为独立主题页" not in topic_markdown


@pytest.mark.asyncio
async def test_compile_document_refreshes_compiler_generated_topic_page(
    db_session,
    test_user_verified,
    tmp_path,
):
    kb = await _create_kb(db_session, test_user_verified)
    source_file = tmp_path / "API Doc.md"
    _write_chunks(source_file)
    doc = await _create_document(db_session, kb_id=kb.id, file_path=source_file)
    storage = WikiStorage(root_dir=tmp_path / "wiki")
    topic_path = f"topics/doc-{doc.id}-topic.md"
    title = f"{doc.file_name} 主题页"
    generated_markdown = build_markdown_page(
        {
            "title": title,
            "page_type": "topic",
            "status": "active",
            "source_doc_id": doc.id,
            "source_count": 2,
            "tags": ["topic", "中文主题页"],
        },
        title,
        [
            (
                "来源摘要",
                f"本主题页候选来自 [{doc.file_name}](sources/{doc.id}-api-doc-md.md)，"
                "由已编译来源片段自动整理，采纳后可作为一阶段 Wiki 回答素材。",
            ),
            ("关键要点", "- 旧的自动整理内容。"),
            ("后续维护", "- 保留来源链接或来源标记。"),
        ],
    )
    storage.write_page(kb.id, topic_path, generated_markdown)
    await wiki_crud.upsert_page(
        db_session,
        kb_id=kb.id,
        path=topic_path,
        title=title,
        page_type="topic",
        content_hash=storage.content_hash(generated_markdown),
        source_doc_id=doc.id,
        provenance={"compiler": "wiki", "source_doc_id": doc.id},
    )
    compiler = WikiCompiler(storage=storage)

    await compiler.compile_document(db_session, kb_id=kb.id, doc_id=doc.id)

    topic_markdown = storage.read_page(kb.id, topic_path)
    assert "本主题页来自" in topic_markdown
    assert "本主题页候选来自" not in topic_markdown
    assert "Milvus provides vector search." in topic_markdown


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
