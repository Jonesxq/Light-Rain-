"""Tests for Wiki compile hook after knowledge ingest."""

import pytest

from app.services.knowledge.ingest import KnowledgeIngest
from app.services.knowledge import ingest as ingest_module


class _DummyService:
    pass


@pytest.mark.asyncio
async def test_maybe_compile_wiki_skips_when_disabled(monkeypatch):
    calls = []

    async def _compile_document(*_args, **_kwargs):
        calls.append((_args, _kwargs))

    monkeypatch.setattr(ingest_module.settings.wiki, "WIKI_AUTO_COMPILE_ON_INGEST", False)
    monkeypatch.setattr(ingest_module.wiki_service, "compile_document", _compile_document)

    await KnowledgeIngest(_DummyService())._maybe_compile_wiki(object(), kb_id=7, doc_id=11)

    assert calls == []


@pytest.mark.asyncio
async def test_maybe_compile_wiki_calls_service_with_ids_when_enabled(monkeypatch):
    calls = []
    db = object()

    async def _compile_document(received_db, **kwargs):
        calls.append((received_db, kwargs))

    monkeypatch.setattr(ingest_module.settings.wiki, "WIKI_AUTO_COMPILE_ON_INGEST", True)
    monkeypatch.setattr(ingest_module.wiki_service, "compile_document", _compile_document)

    await KnowledgeIngest(_DummyService())._maybe_compile_wiki(db, kb_id=7, doc_id=11)

    assert calls == [(db, {"kb_id": 7, "doc_id": 11})]


@pytest.mark.asyncio
async def test_maybe_compile_wiki_swallows_exception_and_logs_warning(monkeypatch):
    warnings = []

    async def _compile_document(*_args, **_kwargs):
        raise RuntimeError("compile boom")

    monkeypatch.setattr(ingest_module.settings.wiki, "WIKI_AUTO_COMPILE_ON_INGEST", True)
    monkeypatch.setattr(ingest_module.wiki_service, "compile_document", _compile_document)
    monkeypatch.setattr(ingest_module.logger, "warning", lambda message: warnings.append(message))

    await KnowledgeIngest(_DummyService())._maybe_compile_wiki(object(), kb_id=7, doc_id=11)

    assert len(warnings) == 1
    assert "Wiki compile failed" in warnings[0]
    assert "11" in warnings[0]
