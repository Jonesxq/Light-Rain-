import pytest

from app.crud.wiki import wiki_crud
from app.models.knowledge import KnowledgeBase
from app.services.wiki.retriever import WikiRetriever
from app.services.wiki.service import WikiService
from app.services.wiki.storage import WikiStorage


async def _create_kb(db_session, test_user_verified, name="Retriever KB"):
    kb = KnowledgeBase(user_id=test_user_verified.id, name=name)
    db_session.add(kb)
    await db_session.commit()
    await db_session.refresh(kb)
    return kb


async def _upsert_page(
    db_session,
    storage: WikiStorage,
    *,
    kb_id: int,
    path: str,
    title: str,
    page_type: str,
    content: str | None = None,
    status: str = "active",
):
    if content is not None:
        storage.write_page(kb_id, path, content)

    return await wiki_crud.upsert_page(
        db_session,
        kb_id=kb_id,
        path=path,
        title=title,
        page_type=page_type,
        content_hash=storage.content_hash(content or ""),
        status=status,
    )


def _page_markdown(title: str, page_type: str, body: str, **frontmatter):
    metadata = {
        "title": title,
        "page_type": page_type,
        "status": "active",
        **frontmatter,
    }
    lines = ["---"]
    lines.extend(f'{key}: "{value}"' for key, value in metadata.items())
    lines.extend(["---", "", f"# {title}", "", body])
    return "\n".join(lines)


@pytest.mark.asyncio
async def test_search_ranks_bm25_retrieval_page_first(
    db_session,
    test_user_verified,
    tmp_path,
):
    kb = await _create_kb(db_session, test_user_verified)
    storage = WikiStorage(root_dir=tmp_path)
    await _upsert_page(
        db_session,
        storage,
        kb_id=kb.id,
        path="index.md",
        title="Index",
        page_type="index",
        content=(
            "# Index\n"
            "- [Retrieval](topics/retrieval.md)\n"
            "- [External](https://example.com)\n"
            "- [Anchor](#local)\n"
            "[source:doc=1;chunk=0]\n"
        ),
    )
    retrieval = await _upsert_page(
        db_session,
        storage,
        kb_id=kb.id,
        path="topics/retrieval.md",
        title="Retrieval",
        page_type="topic",
        content=_page_markdown(
            "Retrieval",
            "topic",
            "BM25 rerank combines sparse scoring with rerank signals.",
            tags="search",
        ),
    )
    await _upsert_page(
        db_session,
        storage,
        kb_id=kb.id,
        path="topics/other.md",
        title="Other",
        page_type="topic",
        content=_page_markdown(
            "Other",
            "topic",
            "Vector indexes help semantic lookup for unrelated material.",
        ),
    )

    hits = await WikiRetriever(storage=storage).search(
        db_session,
        kb_id=kb.id,
        query="BM25 rerank",
        top_k=2,
    )

    assert hits
    assert hits[0].page_id == retrieval.id
    assert hits[0].path == "topics/retrieval.md"
    assert hits[0].title == "Retrieval"
    assert hits[0].page_type == "topic"
    assert hits[0].score > 0
    assert "BM25 rerank combines sparse scoring" in hits[0].snippet


@pytest.mark.asyncio
async def test_search_boosts_index_linked_page_when_relevance_is_close(
    db_session,
    test_user_verified,
    tmp_path,
):
    kb = await _create_kb(db_session, test_user_verified)
    storage = WikiStorage(root_dir=tmp_path)
    await _upsert_page(
        db_session,
        storage,
        kb_id=kb.id,
        path="index.md",
        title="Index",
        page_type="index",
        content="# Index\n- [Primary](topics/primary.md)\n",
    )
    linked = await _upsert_page(
        db_session,
        storage,
        kb_id=kb.id,
        path="topics/primary.md",
        title="Primary",
        page_type="topic",
        content=_page_markdown("Primary", "topic", "Shared term appears here."),
    )
    await _upsert_page(
        db_session,
        storage,
        kb_id=kb.id,
        path="topics/unlinked.md",
        title="Unlinked",
        page_type="topic",
        content=_page_markdown("Unlinked", "topic", "Shared term appears here."),
    )

    hits = await WikiRetriever(storage=storage).search(
        db_session,
        kb_id=kb.id,
        query="shared term",
        top_k=2,
    )

    assert hits[0].page_id == linked.id
    assert hits[0].path == "topics/primary.md"
    assert hits[0].score > hits[1].score


@pytest.mark.asyncio
async def test_search_skips_missing_files(db_session, test_user_verified, tmp_path):
    kb = await _create_kb(db_session, test_user_verified)
    storage = WikiStorage(root_dir=tmp_path)
    await _upsert_page(
        db_session,
        storage,
        kb_id=kb.id,
        path="index.md",
        title="Index",
        page_type="index",
        content="# Index\n- [Missing](topics/missing.md)\n",
    )
    existing = await _upsert_page(
        db_session,
        storage,
        kb_id=kb.id,
        path="topics/existing.md",
        title="Existing",
        page_type="topic",
        content=_page_markdown("Existing", "topic", "BM25 content exists."),
    )
    await _upsert_page(
        db_session,
        storage,
        kb_id=kb.id,
        path="topics/missing.md",
        title="Missing",
        page_type="topic",
    )

    hits = await WikiRetriever(storage=storage).search(
        db_session,
        kb_id=kb.id,
        query="BM25",
        top_k=5,
    )

    assert [hit.page_id for hit in hits] == [existing.id]


@pytest.mark.asyncio
async def test_service_search_pages_delegates(db_session, tmp_path, monkeypatch):
    storage = WikiStorage(root_dir=tmp_path)
    service = WikiService(storage=storage)
    calls = []

    async def fake_search(db, *, kb_id: int, query: str, top_k: int):
        calls.append((db, kb_id, query, top_k))
        return ["hit"]

    monkeypatch.setattr(service.retriever, "search", fake_search)

    result = await service.search_pages(
        db_session,
        kb_id=42,
        query="needle",
        top_k=3,
    )

    assert result == ["hit"]
    assert calls == [(db_session, 42, "needle", 3)]


@pytest.mark.asyncio
async def test_empty_kb_returns_empty_hits(db_session, test_user_verified, tmp_path):
    kb = await _create_kb(db_session, test_user_verified)

    hits = await WikiRetriever(storage=WikiStorage(root_dir=tmp_path)).search(
        db_session,
        kb_id=kb.id,
        query="anything",
        top_k=10,
    )

    assert hits == []
