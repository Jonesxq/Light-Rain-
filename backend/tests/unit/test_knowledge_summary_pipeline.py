"""Tests for summary ingestion + raw chunk sidecar pipeline."""
import json
from pathlib import Path

import pytest
from langchain_core.documents import Document as LangChainDocument

from app.models.knowledge import DocStatus, Document
from app.services.knowledge import ChunkCandidate, KnowledgeService
from app.services.knowledge.ingest import KnowledgeIngest
from app.services.knowledge.retrieval import KnowledgeRetrieval
from app.services.knowledge.runtime import KnowledgeRuntime
from app.services.knowledge.storage import KnowledgeStorage
from app.services.knowledge import ingest as ingest_module


def _new_service() -> KnowledgeService:
    service = KnowledgeService.__new__(KnowledgeService)
    service._runtime = KnowledgeRuntime(service)
    service._storage = KnowledgeStorage(service)
    service._retrieval = KnowledgeRetrieval(service)
    service._ingest = KnowledgeIngest(service)
    service._ops = (service._runtime, service._storage, service._retrieval, service._ingest)
    return service


class _FakeLLMError:
    async def ainvoke(self, _messages):
        raise RuntimeError("boom")


class _FakeLLMOk:
    class _Resp:
        def __init__(self, content: str):
            self.content = content

    async def ainvoke(self, _messages):
        return self._Resp("x" * 20)


@pytest.mark.asyncio
async def test_summarize_chunk_fallback_to_raw_text():
    service = _new_service()
    summary, _usage = await service._summarize_chunk(_FakeLLMError(), "raw chunk", 10)
    assert summary == "raw chunk"


@pytest.mark.asyncio
async def test_summarize_chunk_truncates_to_max_chars():
    service = _new_service()
    summary, _usage = await service._summarize_chunk(_FakeLLMOk(), "raw chunk", 8)
    assert summary == "x" * 8


@pytest.mark.asyncio
async def test_summarize_chunks_skip_llm_for_large_documents(monkeypatch):
    service = _new_service()

    def _fail_get_summary_llm():
        raise AssertionError("large documents should not invoke summary LLM")

    monkeypatch.setattr(ingest_module.settings.llm, "RAG_SUMMARY_MAX_CHUNKS", 1)
    monkeypatch.setattr(service, "_get_summary_llm", _fail_get_summary_llm)

    summaries, usage = await service._summarize_chunks(["raw A", "raw B"])

    assert summaries == ["raw A", "raw B"]
    assert usage == {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "token_missing": 0,
    }


def test_sidecar_roundtrip_with_bad_lines(tmp_path: Path):
    service = _new_service()
    sidecar = tmp_path / "doc.txt.chunks.jsonl"
    rows = [
        {
            "parent_id": "1:0",
            "content": "raw A",
            "structured_meta": {"doc": {"doc_id": 1}, "chunk": {"index": 0}},
            "token_count": 0,
        },
        {
            "parent_id": "1:1",
            "content": "raw B",
            "structured_meta": {"doc": {"doc_id": 1}, "chunk": {"index": 1}},
            "token_count": 0,
        },
    ]
    service._write_sidecar_atomic(str(sidecar), rows)
    with sidecar.open("a", encoding="utf-8") as f:
        f.write("{bad json line}\n")

    candidates = service._read_sidecar_candidates(str(sidecar))
    assert len(candidates) == 2
    assert [c.parent_id for c in candidates] == ["1:0", "1:1"]
    assert [c.content for c in candidates] == ["raw A", "raw B"]


@pytest.mark.asyncio
async def test_items_from_documents_replace_summary_with_raw_chunk(monkeypatch):
    service = _new_service()

    async def _fake_load_meta(_vector_ids):
        return {"77": {"parent_id": "1:0", "doc": {"doc_id": 1}, "chunk": {"index": 0}}}

    monkeypatch.setattr(service, "_load_structured_meta_by_vector_ids", _fake_load_meta)

    docs = [LangChainDocument(page_content="summary text", metadata={"pk": "77"})]
    raw_lookup = {
        "1:0": ChunkCandidate(
            parent_id="1:0",
            content="raw text",
            structured_meta={"parent_id": "1:0", "doc": {"doc_id": 1}, "chunk": {"index": 0}},
        )
    }

    items = await service._items_from_documents(docs, raw_lookup=raw_lookup)
    assert len(items) == 1
    assert items[0].content == "raw text"


@pytest.mark.asyncio
async def test_items_from_documents_fallback_to_summary_when_raw_missing(monkeypatch):
    service = _new_service()

    async def _fake_load_meta(_vector_ids):
        return {"88": {"parent_id": "1:9", "doc": {"doc_id": 1}, "chunk": {"index": 9}}}

    monkeypatch.setattr(service, "_load_structured_meta_by_vector_ids", _fake_load_meta)

    docs = [LangChainDocument(page_content="summary only", metadata={"pk": "88"})]
    items = await service._items_from_documents(docs, raw_lookup={})

    assert len(items) == 1
    assert items[0].content == "summary only"


@pytest.mark.asyncio
async def test_ingest_document_store_summary_in_db_and_raw_in_sidecar(tmp_path: Path, monkeypatch):
    service = _new_service()
    service._bm25_cache = {}

    raw_file = tmp_path / "doc.txt"
    raw_file.write_text("source", encoding="utf-8")

    doc = Document(
        id=1,
        kb_id=7,
        file_name="doc.txt",
        file_path=str(raw_file),
        file_type=".txt",
        file_size=6,
        status=DocStatus.PROCESSING,
    )

    chunks = [
        LangChainDocument(page_content="raw chunk A", metadata={"doc": {"doc_id": 1}, "chunk": {"index": 0}}),
        LangChainDocument(page_content="raw chunk B", metadata={"doc": {"doc_id": 1}, "chunk": {"index": 1}}),
    ]

    class _DummyChunker:
        def load_and_split(self, *_args, **_kwargs):
            return chunks

    class _FakeVectorStore:
        def add_documents(self, _docs):
            return [101, 102]

    class _FakeDB:
        def __init__(self, _doc):
            self._doc = _doc

        async def get(self, _model, _doc_id):
            return self._doc

    class _FakeSessionCtx:
        def __init__(self, _doc):
            self._db = _FakeDB(_doc)

        async def __aenter__(self):
            return self._db

        async def __aexit__(self, exc_type, exc, tb):
            return False

    created_chunks = []
    status_updates = []
    to_thread_calls = []

    async def _fake_create_chunk(
        _db,
        doc_id,
        parent_id,
        content,
        vector_id,
        chunk_index,
        token_count=0,
        structured_meta=None,
    ):
        created_chunks.append(
            {
                "doc_id": doc_id,
                "parent_id": parent_id,
                "content": content,
                "vector_id": vector_id,
                "chunk_index": chunk_index,
                "token_count": token_count,
                "structured_meta": structured_meta,
            }
        )
        return None

    async def _fake_update_status(_db, doc_id, status, chunk_count=None, error_msg=None):
        status_updates.append(
            {
                "doc_id": doc_id,
                "status": status,
                "chunk_count": chunk_count,
                "error_msg": error_msg,
            }
        )

    async def _fake_summaries(raw_chunks):
        assert raw_chunks == ["raw chunk A", "raw chunk B"]
        return ["sum A", "sum B"], {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "token_missing": 0}

    async def _fake_get_kb(*_args, **_kwargs):
        return None

    async def _fake_to_thread(func, /, *args, **kwargs):
        to_thread_calls.append(getattr(func, "__name__", func.__class__.__name__))
        return func(*args, **kwargs)

    monkeypatch.setattr(service, "chunker", _DummyChunker(), raising=False)
    monkeypatch.setattr(service, "_summarize_chunks", _fake_summaries)
    monkeypatch.setattr(service, "_get_vector_store", lambda _kb_id: _FakeVectorStore())
    monkeypatch.setattr(service, "_invalidate_bm25_cache", lambda _kb_id: None)
    monkeypatch.setattr(ingest_module.mysql_manager, "async_session_maker", lambda: _FakeSessionCtx(doc))
    monkeypatch.setattr(ingest_module.kb_crud, "create_chunk", _fake_create_chunk)
    monkeypatch.setattr(ingest_module.kb_crud, "update_document_status", _fake_update_status)
    monkeypatch.setattr(ingest_module.kb_crud, "get_kb", _fake_get_kb)
    monkeypatch.setattr(ingest_module.asyncio, "to_thread", _fake_to_thread)

    await service.ingest_document(1)

    assert len(created_chunks) == 2
    assert [c["content"] for c in created_chunks] == ["sum A", "sum B"]
    assert [c["parent_id"] for c in created_chunks] == ["1:0", "1:1"]
    assert status_updates[-1]["status"] == DocStatus.COMPLETED
    assert status_updates[-1]["chunk_count"] == 2
    assert "load_and_split" in to_thread_calls
    assert "add_documents" in to_thread_calls

    sidecar_path = Path(f"{doc.file_path}.chunks.jsonl")
    assert sidecar_path.exists()
    lines = [json.loads(line) for line in sidecar_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 2
    assert [line["content"] for line in lines] == ["raw chunk A", "raw chunk B"]
    assert [line["parent_id"] for line in lines] == ["1:0", "1:1"]
