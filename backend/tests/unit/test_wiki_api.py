import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeBase
from app.models.user import User
from app.models.wiki import WikiPage, WikiPatch
from app.services.wiki import wiki_service
from app.services.wiki.types import WikiLintWarning, WikiSearchHit


async def _create_kb(
    db_session: AsyncSession,
    user: User,
    name: str = "Wiki KB",
) -> KnowledgeBase:
    kb = KnowledgeBase(user_id=user.id, name=name)
    db_session.add(kb)
    await db_session.commit()
    await db_session.refresh(kb)
    return kb


async def _create_page(
    db_session: AsyncSession,
    *,
    kb_id: int,
    path: str = "index.md",
    title: str = "Index",
    page_type: str = "index",
    status: str = "active",
) -> WikiPage:
    page = WikiPage(
        kb_id=kb_id,
        path=path,
        title=title,
        page_type=page_type,
        status=status,
        content_hash="hash",
        provenance={"source": "test"},
    )
    db_session.add(page)
    await db_session.commit()
    await db_session.refresh(page)
    return page


@pytest.mark.asyncio
async def test_list_pages_returns_owned_pages(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user_verified: User,
    auth_headers: dict,
):
    kb = await _create_kb(db_session, test_user_verified)
    page = await _create_page(
        db_session,
        kb_id=kb.id,
        path="topics/vector-search.md",
        title="Vector Search",
        page_type="topic",
    )

    response = await client.get(
        f"/api/v1/knowledge/{kb.id}/wiki/pages",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": page.id,
            "kb_id": kb.id,
            "path": "topics/vector-search.md",
            "title": "Vector Search",
            "page_type": "topic",
            "status": "active",
            "content_hash": "hash",
            "source_doc_id": None,
            "provenance": {"source": "test"},
            "created_at": page.created_at.isoformat(),
            "updated_at": page.updated_at.isoformat(),
        }
    ]


@pytest.mark.asyncio
async def test_list_pages_returns_404_for_other_users_kb(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user_verified: User,
    auth_headers: dict,
):
    other_user = User(
        email="other@example.com",
        username="other",
        hashed_password="hashed",
        is_active=True,
        is_verified=True,
    )
    db_session.add(other_user)
    await db_session.commit()
    await db_session.refresh(other_user)
    kb = await _create_kb(db_session, other_user)

    response = await client.get(
        f"/api/v1/knowledge/{kb.id}/wiki/pages",
        headers=auth_headers,
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_page_returns_metadata_and_content(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user_verified: User,
    auth_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    kb = await _create_kb(db_session, test_user_verified)
    page = await _create_page(db_session, kb_id=kb.id, path="index.md")

    def read_page(kb_id: int, path: str) -> str:
        assert kb_id == kb.id
        assert path == "index.md"
        return "# Index\n\nHello wiki."

    monkeypatch.setattr(wiki_service.storage, "read_page", read_page)

    response = await client.get(
        f"/api/v1/knowledge/{kb.id}/wiki/pages/{page.id}",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == page.id
    assert data["path"] == "index.md"
    assert data["content"] == "# Index\n\nHello wiki."


@pytest.mark.asyncio
async def test_get_page_returns_404_for_missing_content_file(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user_verified: User,
    auth_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    kb = await _create_kb(db_session, test_user_verified)
    page = await _create_page(db_session, kb_id=kb.id, path="missing.md")

    def read_page(_kb_id: int, _path: str) -> str:
        raise FileNotFoundError("missing")

    monkeypatch.setattr(wiki_service.storage, "read_page", read_page)

    response = await client.get(
        f"/api/v1/knowledge/{kb.id}/wiki/pages/{page.id}",
        headers=auth_headers,
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_search_returns_serialized_hits(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user_verified: User,
    auth_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    kb = await _create_kb(db_session, test_user_verified)

    async def search_pages(
        db: AsyncSession,
        *,
        kb_id: int,
        query: str,
        top_k: int,
    ) -> list[WikiSearchHit]:
        assert db is db_session
        assert kb_id == kb.id
        assert query == "milvus"
        assert top_k > 0
        return [
            WikiSearchHit(
                page_id=3,
                path="topics/milvus.md",
                title="Milvus",
                page_type="topic",
                score=0.91,
                snippet="Milvus provides vector search.",
            )
        ]

    monkeypatch.setattr(wiki_service, "search_pages", search_pages)

    response = await client.get(
        f"/api/v1/knowledge/{kb.id}/wiki/search",
        params={"q": "milvus"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json() == [
        {
            "page_id": 3,
            "path": "topics/milvus.md",
            "title": "Milvus",
            "page_type": "topic",
            "score": 0.91,
            "snippet": "Milvus provides vector search.",
        }
    ]


@pytest.mark.asyncio
async def test_lint_returns_serialized_warnings(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user_verified: User,
    auth_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    kb = await _create_kb(db_session, test_user_verified)
    page = await _create_page(db_session, kb_id=kb.id)

    def lint_files(*, kb_id: int, db_pages: list[WikiPage]) -> list[WikiLintWarning]:
        assert kb_id == kb.id
        assert [db_page.id for db_page in db_pages] == [page.id]
        return [
            WikiLintWarning(
                code="missing_frontmatter",
                message="Missing frontmatter",
                path="index.md",
                severity="warning",
            )
        ]

    monkeypatch.setattr(wiki_service.lint, "lint_files", lint_files)

    response = await client.post(
        f"/api/v1/knowledge/{kb.id}/wiki/lint",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json() == {
        "warnings": [
            {
                "code": "missing_frontmatter",
                "message": "Missing frontmatter",
                "path": "index.md",
                "severity": "warning",
            }
        ]
    }


@pytest.mark.asyncio
async def test_list_patches_supports_status_filter(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user_verified: User,
    auth_headers: dict,
):
    kb = await _create_kb(db_session, test_user_verified)
    pending = WikiPatch(
        kb_id=kb.id,
        target_path="topics/vector-search.md",
        operation="create",
        status="pending",
        patch_markdown="# Vector Search",
        question="What is vector search?",
        answer="Vector search finds similar embeddings.",
        rationale="Gap detected.",
        confidence=0.88,
        provenance={"source": "test"},
    )
    applied = WikiPatch(
        kb_id=kb.id,
        target_path="topics/old.md",
        operation="append",
        status="applied",
        patch_markdown="More text",
    )
    db_session.add(pending)
    db_session.add(applied)
    await db_session.commit()
    await db_session.refresh(pending)

    response = await client.get(
        f"/api/v1/knowledge/{kb.id}/wiki/patches",
        params={"status": "pending"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": pending.id,
            "kb_id": kb.id,
            "page_id": None,
            "target_path": "topics/vector-search.md",
            "operation": "create",
            "status": "pending",
            "question": "What is vector search?",
            "answer": "Vector search finds similar embeddings.",
            "patch_markdown": "# Vector Search",
            "rationale": "Gap detected.",
            "confidence": 0.88,
            "provenance": {"source": "test"},
            "created_by_message_id": None,
            "created_at": pending.created_at.isoformat(),
            "applied_at": None,
            "rejected_at": None,
        }
    ]
