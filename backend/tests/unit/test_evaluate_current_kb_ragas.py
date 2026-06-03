"""Tests for the RAGas evaluation maintenance script."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


def _load_eval_module():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "evaluate_current_kb_ragas.py"
    spec = importlib.util.spec_from_file_location("evaluate_current_kb_ragas", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_run_with_retries_recovers_from_transient_error(monkeypatch):
    eval_module = _load_eval_module()
    attempts = 0
    sleeps: list[float] = []

    async def _fake_sleep(seconds: float):
        sleeps.append(seconds)

    async def _flaky_operation():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("temporary network break")
        return "ok"

    monkeypatch.setattr(eval_module.asyncio, "sleep", _fake_sleep)

    result = await eval_module._run_with_retries(
        _flaky_operation,
        label="answer generation",
        attempts=4,
        base_delay=0.5,
    )

    assert result == "ok"
    assert attempts == 3
    assert sleeps == [0.5, 1.0]


def test_answer_checkpoint_restores_completed_rows():
    eval_module = _load_eval_module()
    checkpoint = Path.cwd() / ".tmp_ragas_answers_checkpoint_test.json"
    records = [
        {"doc": "doc-a.pdf", "question": "q1", "reference": "r1"},
        {"doc": "doc-b.pdf", "question": "q2", "reference": "r2"},
    ]

    try:
        checkpoint.write_text(
            json.dumps(
                [
                    {
                        "doc": "doc-a.pdf",
                        "question": "q1",
                        "rewritten_query": "q1 rewritten",
                        "answer": "a1",
                        "reference": "r1",
                        "sources": [{"source": "doc-a.pdf"}],
                        "contexts": ["NIST framework context with enough semantic information."],
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        raw_rows, eval_rows, completed = eval_module._load_answer_checkpoint(checkpoint, records)
    finally:
        checkpoint.unlink(missing_ok=True)

    assert completed == {"q1"}
    assert raw_rows[0]["question"] == "q1"
    assert eval_rows == [
        {
            "user_input": "q1",
            "response": "a1",
            "retrieved_contexts": ["NIST framework context with enough semantic information."],
            "reference": "r1",
        }
    ]
    assert eval_module._remaining_records(records, completed) == [records[1]]
