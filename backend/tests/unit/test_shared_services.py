"""Tests for shared service helpers."""

from __future__ import annotations

import pytest

from app.services.shared.bm25 import BM25Index, _tokenize
from app.services.shared import llm_runtime as llm_runtime_module
from app.services.shared import document_chunking as document_chunking_module
from app.services.shared.document_chunking import DocumentChunkingService


_MINIMAL_TEXT_PDF = b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj
4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj
5 0 obj << /Length 44 >> stream
BT /F1 24 Tf 72 720 Td (Hello PDF text) Tj ET
endstream endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000252 00000 n 
0000000322 00000 n 
trailer << /Size 6 /Root 1 0 R >>
startxref
415
%%EOF
"""


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


def test_pdf_uses_docling_markdown_conversion(tmp_path, monkeypatch):
    pdf_path = tmp_path / "plain.pdf"
    pdf_path.write_bytes(_MINIMAL_TEXT_PDF)

    class _FakeDoclingDocument:
        def export_to_markdown(self):
            return "# Docling PDF\n\nHello from Docling markdown"

    class _FakeDoclingResult:
        document = _FakeDoclingDocument()

    class _FakeConverter:
        def __init__(self):
            self.calls = []

        def convert(self, file_path):
            self.calls.append(file_path)
            return _FakeDoclingResult()

    converter = _FakeConverter()
    monkeypatch.setattr(document_chunking_module, "_GLOBAL_CONVERTER", converter)

    docs = DocumentChunkingService().load_and_split(str(pdf_path), ".pdf")

    assert converter.calls == [str(pdf_path)]
    assert docs
    assert "Hello from Docling markdown" in docs[0].page_content
    assert docs[0].metadata["loc"]["md_headings"] == "Docling PDF"


def test_docling_partial_pdf_recovers_missing_pages_with_page_range(tmp_path, monkeypatch):
    pdf_path = tmp_path / "partial.pdf"
    pdf_path.write_bytes(_MINIMAL_TEXT_PDF)

    class _FakeDoclingDocument:
        def __init__(self, markdown: str):
            self.markdown = markdown

        def export_to_markdown(self):
            return self.markdown

    class _FakeDoclingPage:
        def __init__(self, page_no: int):
            self.page_no = page_no

    class _FakeDoclingInput:
        page_count = 3

    class _FakeDoclingResult:
        def __init__(self, markdown: str, page_numbers: list[int]):
            self.document = _FakeDoclingDocument(markdown)
            self.pages = [_FakeDoclingPage(page_no) for page_no in page_numbers]
            self.input = _FakeDoclingInput()
            self.errors = []

    class _FakeConverter:
        def __init__(self):
            self.calls = []

        def convert(self, file_path, **kwargs):
            self.calls.append((file_path, kwargs))
            if kwargs.get("page_range") == (2, 2):
                return _FakeDoclingResult("Recovered page 2 markdown", [2])
            return _FakeDoclingResult("# Full PDF\n\nPages 1 and 3 markdown", [1, 3])

    converter = _FakeConverter()
    monkeypatch.setattr(document_chunking_module, "_GLOBAL_CONVERTER", converter)

    docs = DocumentChunkingService().load_and_split(str(pdf_path), ".pdf")
    combined = "\n".join(doc.page_content for doc in docs)

    assert converter.calls == [
        (str(pdf_path), {}),
        (str(pdf_path), {"page_range": (2, 2), "raises_on_error": False}),
    ]
    assert "Pages 1 and 3 markdown" in combined
    assert "Recovered page 2 markdown" in combined


def test_docling_pdf_pipeline_uses_low_memory_defaults():
    options = document_chunking_module._pipeline_options

    assert options.accelerator_options.device == "cpu"
    assert options.accelerator_options.num_threads == 1
    assert options.layout_batch_size == 1
    assert options.ocr_batch_size == 1
    assert options.table_batch_size == 1
    assert options.queue_max_size <= 4
    assert options.force_backend_text is True


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

