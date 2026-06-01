import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.knowledge import KnowledgeBase
from app.models.user import User
from app.models.wiki import WikiPage, WikiPageRevision, WikiPatch
from app.services.wiki import wiki_service
from app.services.wiki.storage import WikiStorage
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
        path="topics/privacy-topic.md",
        title="个人信息保护主题页",
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
            "path": "topics/privacy-topic.md",
            "title": "个人信息保护主题页",
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
        target_path="topics/privacy-topic.md",
        operation="create",
        status="pending",
        patch_markdown="# 个人信息保护主题页",
        question="是否整理个人信息保护主题页？",
        answer="整理个人信息保护法中的关键规则。",
        rationale="来源页中包含可沉淀的主题内容。",
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
            "target_path": "topics/privacy-topic.md",
            "operation": "create",
            "status": "pending",
            "question": "是否整理个人信息保护主题页？",
            "answer": "整理个人信息保护法中的关键规则。",
            "patch_markdown": "# 个人信息保护主题页",
            "rationale": "来源页中包含可沉淀的主题内容。",
            "confidence": 0.88,
            "provenance": {"source": "test"},
            "created_by_message_id": None,
            "created_at": pending.created_at.isoformat(),
            "applied_at": None,
            "rejected_at": None,
        }
    ]


@pytest.mark.asyncio
async def test_apply_append_patch_updates_page_and_marks_applied(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user_verified: User,
    auth_headers: dict,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    kb = await _create_kb(db_session, test_user_verified)
    storage = WikiStorage(root_dir=tmp_path)
    monkeypatch.setattr(wiki_service, "storage", storage)

    initial_content = (
        "---\n"
        'title: "FAQ"\n'
        'page_type: "faq"\n'
        'status: "active"\n'
        "---\n\n"
        "# FAQ\n"
    )
    storage.write_page(kb.id, "faq.md", initial_content)
    page = await _create_page(
        db_session,
        kb_id=kb.id,
        path="faq.md",
        title="FAQ",
        page_type="faq",
    )
    patch = WikiPatch(
        kb_id=kb.id,
        page_id=page.id,
        target_path="faq.md",
        operation="append",
        status="pending",
        question="什么是敏感个人信息？",
        answer="敏感个人信息包括生物识别等信息。",
        patch_markdown=(
            "## 什么是敏感个人信息？\n\n"
            "**回答：**\n\n"
            "敏感个人信息包括生物识别等信息。"
        ),
        confidence=0.91,
        provenance={"strategy": "rag_fallback"},
    )
    db_session.add(patch)
    await db_session.commit()
    await db_session.refresh(patch)

    response = await client.post(
        f"/api/v1/knowledge/{kb.id}/wiki/patches/{patch.id}/apply",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "applied"
    assert data["applied_at"] is not None
    assert data["page_id"] == page.id

    updated_content = storage.read_page(kb.id, "faq.md")
    assert updated_content.startswith("# FAQ") or "# FAQ" in updated_content
    assert "## 什么是敏感个人信息？" in updated_content
    assert "敏感个人信息包括生物识别等信息。" in updated_content

    refreshed_page = await db_session.get(WikiPage, page.id)
    assert refreshed_page.content_hash == storage.content_hash(updated_content)
    revisions = (
        (
            await db_session.execute(
                select(WikiPageRevision).where(WikiPageRevision.page_id == page.id)
            )
        )
        .scalars()
        .all()
    )
    assert revisions
    assert revisions[-1].change_reason == f"apply wiki patch {patch.id}"


@pytest.mark.asyncio
async def test_apply_create_patch_refreshes_wiki_index(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user_verified: User,
    auth_headers: dict,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    kb = await _create_kb(db_session, test_user_verified)
    storage = WikiStorage(root_dir=tmp_path)
    monkeypatch.setattr(wiki_service, "storage", storage)

    source_content = (
        "---\n"
        'title: "中华人民共和国个人信息保护法.md"\n'
        'page_type: "source"\n'
        'status: "active"\n'
        "---\n\n"
        "# 中华人民共和国个人信息保护法.md\n"
    )
    storage.write_page(kb.id, "sources/3-md.md", source_content)
    storage.write_page(
        kb.id,
        "index.md",
        "# Index\n\n## Sources\n\n- [旧条目](sources/old.md)\n",
    )
    source_page = await _create_page(
        db_session,
        kb_id=kb.id,
        path="sources/3-md.md",
        title="中华人民共和国个人信息保护法.md",
        page_type="source",
    )
    await _create_page(
        db_session,
        kb_id=kb.id,
        path="index.md",
        title="Index",
        page_type="index",
    )
    patch = WikiPatch(
        kb_id=kb.id,
        target_path="topics/doc-3-topic.md",
        operation="create",
        status="pending",
        question="是否将该来源整理成中文主题页？",
        patch_markdown=(
            "---\n"
            'title: "中华人民共和国个人信息保护法.md 主题页"\n'
            'page_type: "topic"\n'
            'status: "active"\n'
            "---\n\n"
            "# 中华人民共和国个人信息保护法.md 主题页\n\n"
            f"本主题页候选来自 [{source_page.title}](sources/3-md.md)。\n"
        ),
        confidence=0.9,
    )
    db_session.add(patch)
    await db_session.commit()
    await db_session.refresh(patch)

    response = await client.post(
        f"/api/v1/knowledge/{kb.id}/wiki/patches/{patch.id}/apply",
        headers=auth_headers,
    )

    assert response.status_code == 200
    index_content = storage.read_page(kb.id, "index.md")
    assert "中华人民共和国个人信息保护法.md" in index_content
    assert "sources/3-md.md" in index_content
    assert "中华人民共和国个人信息保护法.md 主题页" in index_content
    assert "topics/doc-3-topic.md" in index_content
    assert "旧条目" not in index_content


@pytest.mark.asyncio
async def test_apply_stale_create_patch_retires_it_when_target_exists(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user_verified: User,
    auth_headers: dict,
):
    kb = await _create_kb(db_session, test_user_verified)
    page = await _create_page(
        db_session,
        kb_id=kb.id,
        path="topics/doc-3-topic.md",
        title="中华人民共和国个人信息保护法.md 主题页",
        page_type="topic",
    )
    patch = WikiPatch(
        kb_id=kb.id,
        target_path=page.path,
        operation="create",
        status="pending",
        question="是否将该来源整理成中文主题页？",
        patch_markdown="# 已存在的主题页",
    )
    db_session.add(patch)
    await db_session.commit()
    await db_session.refresh(patch)

    response = await client.post(
        f"/api/v1/knowledge/{kb.id}/wiki/patches/{patch.id}/apply",
        headers=auth_headers,
    )

    assert response.status_code == 409
    await db_session.refresh(patch)
    assert patch.status == "rejected"
    assert patch.page_id == page.id
    assert patch.rejected_at is not None


@pytest.mark.asyncio
async def test_reject_pending_patch_marks_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user_verified: User,
    auth_headers: dict,
):
    kb = await _create_kb(db_session, test_user_verified)
    patch = WikiPatch(
        kb_id=kb.id,
        target_path="faq.md",
        operation="append",
        status="pending",
        patch_markdown="## Question\n\nAnswer",
    )
    db_session.add(patch)
    await db_session.commit()
    await db_session.refresh(patch)

    response = await client.post(
        f"/api/v1/knowledge/{kb.id}/wiki/patches/{patch.id}/reject",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "rejected"
    assert data["rejected_at"] is not None
    assert data["applied_at"] is None


@pytest.mark.asyncio
async def test_patch_transition_requires_pending_status(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user_verified: User,
    auth_headers: dict,
):
    kb = await _create_kb(db_session, test_user_verified)
    patch = WikiPatch(
        kb_id=kb.id,
        target_path="faq.md",
        operation="append",
        status="applied",
        patch_markdown="## Already handled",
    )
    db_session.add(patch)
    await db_session.commit()
    await db_session.refresh(patch)

    apply_response = await client.post(
        f"/api/v1/knowledge/{kb.id}/wiki/patches/{patch.id}/apply",
        headers=auth_headers,
    )
    reject_response = await client.post(
        f"/api/v1/knowledge/{kb.id}/wiki/patches/{patch.id}/reject",
        headers=auth_headers,
    )

    assert apply_response.status_code == 409
    assert reject_response.status_code == 409
