"""Tests for wiki-first knowledge chat behavior."""

from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.schemas.chat import KnowledgeChatRequest
from app.services.chat import rag_flow as rag_module
from app.services.chat.service import ChatService
from app.services.wiki.types import WikiSearchHit


class _FakeLLM:
    def __init__(self, content: str):
        self._content = content
        self.model_name = "demo-model"

    async def ainvoke(self, _messages):
        return SimpleNamespace(content=self._content)

    async def astream(self, _messages):
        yield SimpleNamespace(content=self._content)


def _message_from_kwargs(message_id: int, **kwargs):
    return SimpleNamespace(
        id=message_id,
        session_id=kwargs.get("session_id", 10),
        role=kwargs.get("role"),
        content=kwargs.get("content", ""),
        model_name=kwargs.get("model_name"),
        token_count=kwargs.get("token_count", 0),
        created_at=datetime(2026, 5, 30, 12, 0, 0),
        disclaimers=kwargs.get("disclaimer_codes", []),
        risk_tags=kwargs.get("risk_tags", []),
    )


def _patch_common_chat_dependencies(monkeypatch, service, *, answer: str):
    created_messages = []
    snapshots = []

    async def fake_create_session(*_args, **_kwargs):
        return SimpleNamespace(id=10)

    async def fake_get_session(*_args, **_kwargs):
        return SimpleNamespace(id=10, title="session")

    async def fake_create_message(*_args, **kwargs):
        created_messages.append(kwargs)
        return _message_from_kwargs(len(created_messages), **kwargs)

    async def fake_record_success(**_kwargs):
        return None

    async def fake_auto_rename(*_args, **_kwargs):
        return None

    async def fake_risk(*_args, **_kwargs):
        return [], []

    async def fake_snapshot(**kwargs):
        snapshots.append({"mode": kwargs["mode"], "payload": kwargs["payload"]})

    async def fake_resolve(*_args, **_kwargs):
        return {"model": "demo-model", "api_key": "key", "api_base_url": "url"}

    monkeypatch.setattr(rag_module.chat_crud, "create_session", fake_create_session)
    monkeypatch.setattr(rag_module.chat_crud, "get_session", fake_get_session)
    monkeypatch.setattr(rag_module.chat_crud, "create_message", fake_create_message)
    monkeypatch.setattr(
        rag_module.llm_runtime_service,
        "finalize_usage",
        lambda **_kwargs: {
            "total_tokens": 3,
            "prompt_tokens": 2,
            "completion_tokens": 1,
        },
    )
    monkeypatch.setattr(
        rag_module.llm_runtime_service, "record_success", fake_record_success
    )
    monkeypatch.setattr(service, "_get_risk_info", fake_risk)
    monkeypatch.setattr(service, "_save_prompt_snapshot", fake_snapshot)
    monkeypatch.setattr(service, "_resolve_user_llm_config", fake_resolve)
    monkeypatch.setattr(service, "_get_llm", lambda *_args, **_kwargs: _FakeLLM(answer))
    monkeypatch.setattr(service, "_auto_rename_session", fake_auto_rename)

    return created_messages, snapshots


@pytest.mark.asyncio
async def test_knowledge_chat_uses_wiki_first_when_hit_is_confident(monkeypatch):
    service = ChatService()
    created_messages, snapshots = _patch_common_chat_dependencies(
        monkeypatch,
        service,
        answer="wiki answer",
    )

    async def fake_search_pages(*_args, **_kwargs):
        return [
            WikiSearchHit(
                page_id=5,
                path="sources/3-md.md",
                title="个人信息保护法",
                page_type="source",
                score=2.5,
                snippet="敏感个人信息包括生物识别、宗教信仰等。",
            )
        ]

    def fake_read_page(_kb_id, page_path):
        assert page_path == "sources/3-md.md"
        return "# 个人信息保护法\n\n敏感个人信息包括生物识别、宗教信仰等。"

    async def fail_search_knowledge(*_args, **_kwargs):
        raise AssertionError("raw RAG search should not run when wiki is confident")

    monkeypatch.setattr(rag_module.wiki_service, "search_pages", fake_search_pages)
    monkeypatch.setattr(rag_module.wiki_service.storage, "read_page", fake_read_page)
    monkeypatch.setattr(
        rag_module.kb_service, "search_knowledge", fail_search_knowledge
    )

    result = await service.handle_rag_chat(
        db=None,
        user_id=1,
        req=KnowledgeChatRequest(message="什么是敏感个人信息？", kb_id=7),
    )

    assert result["content"] == "wiki answer"
    assert result["sources"][0]["source_type"] == "wiki"
    assert result["sources"][0]["file_name"] == "sources/3-md.md"
    assert snapshots[0]["mode"] == "wiki_first"
    assert snapshots[0]["payload"]["wiki"]["strategy"] == "wiki_first"
    assert snapshots[0]["payload"]["wiki"]["hits"][0]["path"] == "sources/3-md.md"
    assert len(created_messages) == 2


@pytest.mark.asyncio
async def test_stream_knowledge_chat_uses_wiki_first_snapshot(monkeypatch):
    service = ChatService()
    _created_messages, snapshots = _patch_common_chat_dependencies(
        monkeypatch,
        service,
        answer="stream wiki answer",
    )

    async def fake_search_pages(*_args, **_kwargs):
        return [
            WikiSearchHit(
                page_id=8,
                path="sources/4-md.md",
                title="数据安全法",
                page_type="source",
                score=3.0,
                snippet="开展数据处理活动应当加强风险监测。",
            )
        ]

    def fake_read_page(_kb_id, page_path):
        assert page_path == "sources/4-md.md"
        return "# 数据安全法\n\n开展数据处理活动应当加强风险监测。"

    async def fail_search_knowledge(*_args, **_kwargs):
        raise AssertionError("raw RAG search should not run in wiki-first streaming")

    monkeypatch.setattr(rag_module.wiki_service, "search_pages", fake_search_pages)
    monkeypatch.setattr(rag_module.wiki_service.storage, "read_page", fake_read_page)
    monkeypatch.setattr(
        rag_module.kb_service, "search_knowledge", fail_search_knowledge
    )

    payloads = []
    async for payload in service._rag_flow._stream_rag_with_context(
        db=None,
        user_id=1,
        session_id=10,
        kb_id=7,
        input_text="数据处理活动需要注意什么？",
        model=None,
        user_message_id=1,
        chat_history=[],
    ):
        payloads.append(payload)

    first = json.loads(payloads[0].removeprefix("data: ").strip())
    done = json.loads(payloads[-1].removeprefix("data: ").strip())
    assert first["content"] == "stream wiki answer"
    assert done["event"] == "done"
    assert done["message"]["sources"][0]["source_type"] == "wiki"
    assert snapshots[0]["mode"] == "wiki_first_stream"
    assert snapshots[0]["payload"]["wiki"]["strategy"] == "wiki_first"


@pytest.mark.asyncio
async def test_knowledge_chat_falls_back_to_rag_and_creates_pending_wiki_patch(
    monkeypatch,
):
    service = ChatService()
    created_messages, snapshots = _patch_common_chat_dependencies(
        monkeypatch,
        service,
        answer="rag answer",
    )
    patches = []

    async def fake_search_pages(*_args, **_kwargs):
        return []

    async def fake_build_rag_runtime(*_args, **_kwargs):
        return {
            "rewritten_query": "重要数据 风险评估",
            "context": "重要数据处理者应当定期开展风险评估。",
            "sources": [
                {"source_type": "kb", "doc_id": 4, "file_name": "数据安全法.md"}
            ],
            "temp_context": "",
            "system_prompt": "rag prompt",
            "messages": [],
            "resolved": {
                "model": "demo-model",
                "api_key": "key",
                "api_base_url": "url",
            },
        }

    async def fake_create_patch(*_args, **kwargs):
        patches.append(kwargs)
        return SimpleNamespace(id=1, **kwargs)

    monkeypatch.setattr(rag_module.wiki_service, "search_pages", fake_search_pages)
    monkeypatch.setattr(service._rag_flow, "_build_rag_runtime", fake_build_rag_runtime)
    monkeypatch.setattr(rag_module.wiki_crud, "create_patch", fake_create_patch)
    monkeypatch.setattr(rag_module.settings.wiki, "WIKI_WRITEBACK_MODE", "manual")

    result = await service.handle_rag_chat(
        db=None,
        user_id=1,
        req=KnowledgeChatRequest(message="重要数据处理者有什么义务？", kb_id=7),
    )

    assert result["content"] == "rag answer"
    assert result["sources"][0]["source_type"] == "kb"
    assert snapshots[0]["mode"] == "rag_fallback"
    assert snapshots[0]["payload"]["wiki"]["strategy"] == "rag_fallback"
    assert len(created_messages) == 2
    assert patches
    assert patches[0]["kb_id"] == 7
    assert patches[0]["target_path"] == "faq.md"
    assert patches[0]["operation"] == "append"
    assert patches[0]["status"] == "pending"
    assert patches[0]["question"] == "重要数据处理者有什么义务？"
    assert patches[0]["answer"] == "rag answer"
    assert "**问题：** 重要数据处理者有什么义务？" in patches[0]["patch_markdown"]
    assert "**回答：**" in patches[0]["patch_markdown"]
    assert patches[0]["rationale"] == (
        "RAG 兜底生成了可复用答案，建议人工审核后写入 Wiki。"
    )
    assert patches[0]["created_by_message_id"] == 2


@pytest.mark.asyncio
async def test_rag_fallback_patch_failure_does_not_break_answer(monkeypatch):
    service = ChatService()
    _created_messages, snapshots = _patch_common_chat_dependencies(
        monkeypatch,
        service,
        answer="answer even if patch fails",
    )

    async def fake_search_pages(*_args, **_kwargs):
        return []

    async def fake_build_rag_runtime(*_args, **_kwargs):
        return {
            "rewritten_query": None,
            "context": "兜底 RAG 上下文",
            "sources": [
                {"source_type": "kb", "doc_id": 4, "file_name": "数据安全法.md"}
            ],
            "temp_context": "",
            "system_prompt": "rag prompt",
            "messages": [],
            "resolved": {
                "model": "demo-model",
                "api_key": "key",
                "api_base_url": "url",
            },
        }

    async def fail_create_patch(*_args, **_kwargs):
        raise RuntimeError("patch table temporarily unavailable")

    monkeypatch.setattr(rag_module.wiki_service, "search_pages", fake_search_pages)
    monkeypatch.setattr(service._rag_flow, "_build_rag_runtime", fake_build_rag_runtime)
    monkeypatch.setattr(rag_module.wiki_crud, "create_patch", fail_create_patch)
    monkeypatch.setattr(rag_module.settings.wiki, "WIKI_WRITEBACK_MODE", "manual")

    result = await service.handle_rag_chat(
        db=None,
        user_id=1,
        req=KnowledgeChatRequest(message="写回失败时也要返回答案吗？", kb_id=7),
    )

    assert result["content"] == "answer even if patch fails"
    assert snapshots[0]["mode"] == "rag_fallback"


@pytest.mark.asyncio
async def test_wiki_search_failure_falls_back_to_rag(monkeypatch):
    service = ChatService()
    _created_messages, snapshots = _patch_common_chat_dependencies(
        monkeypatch,
        service,
        answer="rag still works",
    )

    async def fail_search_pages(*_args, **_kwargs):
        raise RuntimeError("wiki index unavailable")

    async def fake_build_rag_runtime(*_args, **_kwargs):
        return {
            "rewritten_query": "fallback query",
            "context": "普通 RAG 上下文",
            "sources": [
                {"source_type": "kb", "doc_id": 3, "file_name": "个人信息保护法.md"}
            ],
            "temp_context": "",
            "system_prompt": "rag prompt",
            "messages": [],
            "resolved": {
                "model": "demo-model",
                "api_key": "key",
                "api_base_url": "url",
            },
        }

    monkeypatch.setattr(rag_module.wiki_service, "search_pages", fail_search_pages)
    monkeypatch.setattr(service._rag_flow, "_build_rag_runtime", fake_build_rag_runtime)
    monkeypatch.setattr(rag_module.settings.wiki, "WIKI_WRITEBACK_MODE", "disabled")

    result = await service.handle_rag_chat(
        db=None,
        user_id=1,
        req=KnowledgeChatRequest(message="Wiki 检索失败怎么办？", kb_id=7),
    )

    assert result["content"] == "rag still works"
    assert result["sources"][0]["source_type"] == "kb"
    assert snapshots[0]["mode"] == "rag_fallback"
