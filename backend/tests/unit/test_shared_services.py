"""Tests for shared service helpers."""

from __future__ import annotations

import pytest

from app.services.shared.bm25 import BM25Index, _tokenize
from app.services.shared import llm_runtime as llm_runtime_module


def test_bm25_scores_matching_document_higher():
    corpus = [
        _tokenize("今天上海下雨"),
        _tokenize("明天北京晴天"),
        _tokenize("后天深圳多云"),
    ]
    index = BM25Index(corpus)
    scores = index.get_scores(_tokenize("上海下雨"))
    assert scores[0] > scores[1]
    assert scores[0] > scores[2]


def test_finalize_usage_falls_back_to_estimation(monkeypatch):
    class _FakeLLM:
        model_name = "fake-model"

    monkeypatch.setattr(
        llm_runtime_module.usage_service,
        "extract_usage",
        lambda _payload: {"token_missing": True, "prompt_tokens": None, "completion_tokens": None, "total_tokens": None},
    )
    monkeypatch.setattr(
        llm_runtime_module,
        "estimate_usage",
        lambda _llm, _messages, _output: {"prompt_tokens": 3, "completion_tokens": 5, "total_tokens": 8, "token_missing": False},
    )

    usage = llm_runtime_module.llm_runtime_service.finalize_usage(
        llm=_FakeLLM(),
        messages=[],
        output_text="answer",
        payload={},
    )

    assert usage["prompt_tokens"] == 3
    assert usage["completion_tokens"] == 5
    assert usage["total_tokens"] == 8


@pytest.mark.asyncio
async def test_record_success_persists_usage(monkeypatch):
    recorded = {}

    monkeypatch.setattr(llm_runtime_module.usage_service, "compute_cost", lambda *_args, **_kwargs: 1.25)

    async def _fake_record_event(**kwargs):
        recorded.update(kwargs)

    monkeypatch.setattr(llm_runtime_module.usage_service, "record_event", _fake_record_event)

    await llm_runtime_module.llm_runtime_service.record_success(
        db=None,
        user_id=7,
        event_type="chat",
        model_name="demo-model",
        usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30, "token_missing": False},
        latency_ms=123,
        metadata={"session_id": 5},
    )

    assert recorded["user_id"] == 7
    assert recorded["event_type"] == "chat"
    assert recorded["model_name"] == "demo-model"
    assert recorded["prompt_tokens"] == 10
    assert recorded["completion_tokens"] == 20
    assert recorded["total_tokens"] == 30
    assert recorded["cost_usd"] == 1.25
    assert recorded["metadata"] == {"session_id": 5}

