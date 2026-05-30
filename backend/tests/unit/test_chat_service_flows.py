"""Tests for chat dispatching and streaming flow stages."""

from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.schemas.chat import ChatRequest
from app.services.chat.service import ChatService
from app.services.chat import dispatch as dispatch_module
from app.services.chat import reasoning_flow as reasoning_module
from app.services.chat import tool_flow as tool_module


class _FakeStreamLLM:
    def __init__(self, tokens):
        self._tokens = tokens

    async def astream(self, _messages):
        for token in self._tokens:
            yield SimpleNamespace(content=token)


@pytest.mark.asyncio
async def test_process_chat_dispatches_modes(monkeypatch):
    service = ChatService()
    calls = []

    async def _fake_get_session(*_args, **_kwargs):
        return None

    async def _fake_create_message(*_args, **_kwargs):
        return SimpleNamespace(id=1)

    async def _fake_history(*_args, **_kwargs):
        return []

    async def _fake_risk(*_args, **_kwargs):
        return [], []

    async def _fake_tool(**kwargs):
        calls.append(("tool", kwargs["input_text"]))
        return "tool"

    async def _fake_deep_think(**kwargs):
        calls.append(("think", kwargs["question"]))
        return "think"

    async def _fake_deep_search(**kwargs):
        calls.append(("search", kwargs["question"]))
        return "search"

    monkeypatch.setattr(dispatch_module.chat_crud, "get_session", _fake_get_session)
    monkeypatch.setattr(dispatch_module.chat_crud, "create_message", _fake_create_message)
    monkeypatch.setattr(service, "_build_langchain_history", _fake_history)
    monkeypatch.setattr(service, "_get_risk_info", _fake_risk)
    monkeypatch.setattr(service, "run_tool_chat", _fake_tool)
    monkeypatch.setattr(service, "_deep_think_answer", _fake_deep_think)
    monkeypatch.setattr(service, "_deep_search_answer", _fake_deep_search)

    result_tool = await service.process_chat(None, 1, 10, ChatRequest(message="你好", deep_think=False, deep_search=False))
    result_think = await service.process_chat(None, 1, 10, ChatRequest(message="分析这个问题", deep_think=True, deep_search=False))
    monkeypatch.setattr(dispatch_module.settings.llm, "SERPER_API_KEY", "key")
    result_search = await service.process_chat(None, 1, 10, ChatRequest(message="帮我搜索", deep_think=False, deep_search=True))

    assert result_tool == "tool"
    assert result_think == "think"
    assert result_search == "search"
    assert calls == [("tool", "你好"), ("think", "分析这个问题"), ("search", "帮我搜索")]


@pytest.mark.asyncio
async def test_stream_deep_think_stage_order(monkeypatch):
    service = ChatService()
    flow = service._reasoning_flow

    async def _fake_plan(*_args, **_kwargs):
        return {"goal": "g", "steps": []}

    async def _fake_temp(*_args, **_kwargs):
        return ""

    async def _fake_resolve(*_args, **_kwargs):
        return {"model": "demo", "api_key": "k", "api_base_url": "u"}

    async def _fake_snapshot(*_args, **_kwargs):
        return None

    async def _fake_create_message(*_args, **_kwargs):
        return SimpleNamespace(
            id=99,
            content="done",
            model_name="demo",
            token_count=2,
            created_at=datetime(2026, 4, 15),
            disclaimers=[],
            risk_tags=[],
        )

    monkeypatch.setattr(flow, "_build_reasoning_plan", _fake_plan)
    monkeypatch.setattr(service, "_get_temp_context", _fake_temp)
    monkeypatch.setattr(service, "_resolve_user_llm_config", _fake_resolve)
    monkeypatch.setattr(service, "_get_llm", lambda *_args, **_kwargs: _FakeStreamLLM(["A", "B"]))
    monkeypatch.setattr(service, "_save_prompt_snapshot", _fake_snapshot)
    monkeypatch.setattr(reasoning_module.chat_crud, "create_message", _fake_create_message)
    monkeypatch.setattr(reasoning_module.llm_runtime_service, "finalize_usage", lambda **_kwargs: {"total_tokens": 2, "prompt_tokens": 1, "completion_tokens": 1, "token_missing": False})

    async def _fake_record_success(**_kwargs):
        return None

    monkeypatch.setattr(reasoning_module.llm_runtime_service, "record_success", _fake_record_success)

    payloads = []
    async for payload in flow._stream_deep_think(
        db=None,
        user_id=1,
        session_id=2,
        input_text="请推理",
        model=None,
        chat_history=[],
        user_message_id=3,
    ):
        payloads.append(payload)

    stages = [json.loads(item.removeprefix("data: ").strip())["stage"] for item in payloads[:2]]
    assert stages == ["plan", "synthesize"]
    assert json.loads(payloads[-1].removeprefix("data: ").strip())["event"] == "done"


@pytest.mark.asyncio
async def test_stream_deep_search_stage_order(monkeypatch):
    service = ChatService()
    flow = service._reasoning_flow

    async def _fake_plan(*_args, **_kwargs):
        return {"goal": "g", "steps": []}

    async def _fake_queries(*_args, **_kwargs):
        return ["q1"]

    async def _fake_search(*_args, **_kwargs):
        return [{"title": "t", "url": "u", "snippet": "s", "source_type": "web"}]

    async def _fake_temp(*_args, **_kwargs):
        return ""

    async def _fake_resolve(*_args, **_kwargs):
        return {"model": "demo", "api_key": "k", "api_base_url": "u"}

    async def _fake_snapshot(*_args, **_kwargs):
        return None

    async def _fake_fetch_web_sources(*_args, **_kwargs):
        return [{"title": "t", "url": "u", "content": "body"}]

    async def _fake_create_message(*_args, **_kwargs):
        return SimpleNamespace(
            id=100,
            content="done",
            model_name="demo",
            token_count=2,
            created_at=datetime(2026, 4, 15),
            disclaimers=[],
            risk_tags=[],
        )

    monkeypatch.setattr(flow, "_build_reasoning_plan", _fake_plan)
    monkeypatch.setattr(flow, "_build_search_queries", _fake_queries)
    monkeypatch.setattr(flow, "_search_web", _fake_search)
    monkeypatch.setattr(service, "_get_temp_context", _fake_temp)
    monkeypatch.setattr(service, "_resolve_user_llm_config", _fake_resolve)
    monkeypatch.setattr(service, "_get_llm", lambda *_args, **_kwargs: _FakeStreamLLM(["A"]))
    monkeypatch.setattr(service, "_save_prompt_snapshot", _fake_snapshot)
    monkeypatch.setattr(reasoning_module, "fetch_web_sources", _fake_fetch_web_sources)
    monkeypatch.setattr(reasoning_module, "build_search_context", lambda _sources: "ctx")
    monkeypatch.setattr(reasoning_module, "strip_source_content", lambda sources: sources)
    monkeypatch.setattr(reasoning_module.chat_crud, "create_message", _fake_create_message)
    monkeypatch.setattr(reasoning_module.llm_runtime_service, "finalize_usage", lambda **_kwargs: {"total_tokens": 1, "prompt_tokens": 1, "completion_tokens": 0, "token_missing": False})

    async def _fake_record_success(**_kwargs):
        return None

    monkeypatch.setattr(reasoning_module.llm_runtime_service, "record_success", _fake_record_success)

    payloads = []
    async for payload in flow._stream_deep_search(
        db=None,
        user_id=1,
        session_id=2,
        input_text="请搜索",
        model=None,
        chat_history=[],
        user_message_id=3,
    ):
        payloads.append(payload)

    stages = [json.loads(item.removeprefix("data: ").strip())["stage"] for item in payloads[:4]]
    assert stages == ["plan", "search", "fetch", "synthesize"]
    assert json.loads(payloads[-1].removeprefix("data: ").strip())["event"] == "done"


@pytest.mark.asyncio
async def test_tool_chat_sync_and_stream_share_persistence_shape(monkeypatch):
    service = ChatService()
    flow = service._tool_flow
    created = []
    snapshots = []

    class _FakeAgentExecutor:
        async def ainvoke(self, *_args, **kwargs):
            callbacks = (kwargs.get("config") or {}).get("callbacks") if kwargs else None
            if callbacks:
                await callbacks[0].on_llm_new_token("hi")
            return {"output": "hi"}

    async def _fake_runtime(*_args, **_kwargs):
        return {
            "resolved": {"model": "demo"},
            "llm": SimpleNamespace(model_name="demo"),
            "system_prompt": "sys",
            "temp_context": "",
            "agent_executor": _FakeAgentExecutor(),
            "usage_messages": [],
        }

    async def _fake_snapshot(**kwargs):
        snapshots.append({"mode": kwargs["mode"], "payload": kwargs["payload"]})

    async def _fake_create_message(*_args, **kwargs):
        msg = SimpleNamespace(
            id=len(created) + 1,
            session_id=kwargs["session_id"],
            role=kwargs["role"],
            content=kwargs["content"],
            model_name=kwargs["model_name"],
            token_count=kwargs["token_count"],
            created_at=datetime(2026, 4, 15),
            disclaimers=[],
            risk_tags=[],
        )
        created.append(msg)
        return msg

    monkeypatch.setattr(flow, "_build_tool_runtime", _fake_runtime)
    monkeypatch.setattr(tool_module.chat_crud, "create_message", _fake_create_message)
    monkeypatch.setattr(service, "_save_prompt_snapshot", _fake_snapshot)
    monkeypatch.setattr(tool_module.llm_runtime_service, "finalize_usage", lambda **_kwargs: {"total_tokens": 1, "prompt_tokens": 1, "completion_tokens": 0, "token_missing": False})

    async def _fake_record_success(**_kwargs):
        return None

    monkeypatch.setattr(tool_module.llm_runtime_service, "record_success", _fake_record_success)

    await flow.run_tool_chat(None, 1, 10, "普通问题", [])
    stream_payloads = []
    async for payload in flow._stream_tool_chat(None, 1, 10, "普通问题", [], user_message_id=2):
        stream_payloads.append(payload)

    assert created[0].model_name == created[1].model_name == "demo"
    assert created[0].token_count == created[1].token_count == 1
    assert snapshots[0]["mode"] == "tool_chat"
    assert snapshots[1]["mode"] == "tool_chat_stream"
    assert json.loads(stream_payloads[-1].removeprefix("data: ").strip())["event"] == "done"
