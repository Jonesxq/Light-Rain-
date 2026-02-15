"""services/temp_context.py."""
import math
import re
from typing import List, Optional

try:
    import jieba
except Exception:
    jieba = None

from app.core.config.settings import settings
from app.crud.chat_attachment import chat_attachment_crud
from app.services.document_chunking import DocumentChunkingService, TextBlock


_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]")


def _tokenize(text: str) -> List[str]:
    """_tokenize ???"""
    if not text:
        return []
    if jieba:
        return [t.strip().lower() for t in jieba.cut(text) if t.strip()]
    return [t.lower() for t in _TOKEN_PATTERN.findall(text)]


class BM25Index:
    """BM25Index ??"""
    def __init__(self, tokenized_corpus: List[List[str]], k1: float = 1.5, b: float = 0.75):
        """__init__ ???"""
        self.k1 = k1
        self.b = b
        self.doc_freqs: List[dict[str, int]] = []
        self.doc_len: List[int] = []
        self.idf: dict[str, float] = {}
        self.avgdl: float = 0.0

        if not tokenized_corpus:
            return

        df: dict[str, int] = {}
        total_len = 0
        for doc_tokens in tokenized_corpus:
            freqs = {}
            for token in doc_tokens:
                freqs[token] = freqs.get(token, 0) + 1
            self.doc_freqs.append(freqs)
            self.doc_len.append(len(doc_tokens))
            total_len += len(doc_tokens)
            for term in freqs:
                df[term] = df.get(term, 0) + 1

        doc_count = len(tokenized_corpus)
        self.avgdl = (total_len / doc_count) if doc_count else 0.0
        self.idf = {
            term: math.log(1 + (doc_count - freq + 0.5) / (freq + 0.5))
            for term, freq in df.items()
        }

    def get_scores(self, query_tokens: List[str]) -> List[float]:
        """get_scores ???"""
        if not self.doc_freqs or not query_tokens:
            return []

        scores = [0.0] * len(self.doc_freqs)
        avgdl = self.avgdl if self.avgdl > 0 else 1.0

        for term in query_tokens:
            idf = self.idf.get(term)
            if idf is None:
                continue
            for i, freqs in enumerate(self.doc_freqs):
                f = freqs.get(term, 0)
                if not f:
                    continue
                denom = f + self.k1 * (1 - self.b + self.b * (self.doc_len[i] / avgdl))
                scores[i] += idf * (f * (self.k1 + 1)) / (denom + 1e-9)

        return scores


class TempContextService:
    """TempContextService ??"""
    def __init__(self):
        """__init__ ???"""
        self.chunker = DocumentChunkingService(
            default_chunk_size=settings.llm.RAG_CHUNK_SIZE_DEFAULT,
            default_chunk_overlap=settings.llm.RAG_CHUNK_OVERLAP_DEFAULT,
            per_type={
                ".pdf": (settings.llm.RAG_CHUNK_SIZE_PDF, settings.llm.RAG_CHUNK_OVERLAP_PDF),
                ".docx": (settings.llm.RAG_CHUNK_SIZE_DOCX, settings.llm.RAG_CHUNK_OVERLAP_DOCX),
                ".md": (settings.llm.RAG_CHUNK_SIZE_MD, settings.llm.RAG_CHUNK_OVERLAP_MD),
                ".txt": (settings.llm.RAG_CHUNK_SIZE_TXT, settings.llm.RAG_CHUNK_OVERLAP_TXT),
            },
        )

    def _chunk_text(self, text: str) -> List[str]:
        """_chunk_text ???"""
        if not text:
            return []
        normalized = self.chunker._normalize_text(text)
        if not normalized:
            return []
        paragraphs = self.chunker._split_paragraphs(normalized)
        blocks = [TextBlock(text=p, meta={}) for p in paragraphs if p]
        chunk_size, chunk_overlap = self.chunker._get_chunk_params(".txt")
        chunks = self.chunker._chunk_blocks(blocks, chunk_size, chunk_overlap)
        return [c.text for c in chunks if c.text]

    def _extract_text_from_document(self, file_path: str, file_type: str) -> tuple[str, List[str]]:
        """_extract_text_from_document ?????"""
        docs = self.chunker.load_and_split(file_path, file_type)
        chunks = [doc.page_content.strip() for doc in docs if doc.page_content and doc.page_content.strip()]
        extracted_text = "\n\n".join(chunks)
        return extracted_text, chunks

    def _extract_text_from_image(self, file_path: str) -> str:
        """_extract_text_from_image ?????"""
        try:
            from PIL import Image
        except Exception as exc:
            raise ValueError("图片解析失败：缺少 Pillow 依赖") from exc
        try:
            import pytesseract
        except Exception as exc:
            raise ValueError("图片解析失败：缺少 pytesseract 或 Tesseract") from exc

        image = Image.open(file_path)
        return pytesseract.image_to_string(image, lang="chi_sim+eng")

    async def create_attachment(
        self,
        db,
        user_id: int,
        file_name: str,
        file_type: str,
        file_size: int,
        file_path: str,
    ):
        """create_attachment ?????"""
        extracted_text = ""
        chunks: List[str] = []

        if file_type in {".png", ".jpg", ".jpeg"}:
            extracted_text = self._extract_text_from_image(file_path)
            chunks = self._chunk_text(extracted_text)
        else:
            extracted_text, chunks = self._extract_text_from_document(file_path, file_type)

        max_extract = 20000
        if extracted_text and len(extracted_text) > max_extract:
            extracted_text = extracted_text[:max_extract]

        attachment = await chat_attachment_crud.create_attachment(
            db=db,
            user_id=user_id,
            file_name=file_name,
            file_type=file_type,
            file_size=file_size,
            file_path=file_path,
            extracted_text=extracted_text,
            chunks=chunks,
        )
        return attachment

    async def get_context_for_user(
        self,
        db,
        user_id: int,
        query: str,
        top_k: int = 5,
        max_chars: int = 4000,
    ) -> str:
        """get_context_for_user ?????"""
        attachments = await chat_attachment_crud.list_attachments(db, user_id)
        if not attachments:
            return ""

        items = []
        for att in attachments:
            for chunk in (att.chunks or []):
                if not chunk:
                    continue
                text = str(chunk).strip()
                if not text:
                    continue
                items.append({"text": text, "file_name": att.file_name})

        if not items:
            return ""

        query_tokens = _tokenize(query or "")
        ranked_indices = list(range(len(items)))
        if query_tokens:
            tokenized = [_tokenize(item["text"]) for item in items]
            bm25 = BM25Index(tokenized)
            scores = bm25.get_scores(query_tokens)
            if scores:
                ranked_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

        parts: List[str] = []
        total = 0
        for idx in ranked_indices[:top_k]:
            item = items[idx]
            snippet = item["text"]
            block = f"[{item['file_name']}]\n{snippet}"
            if total + len(block) > max_chars:
                remaining = max_chars - total
                if remaining > 40:
                    parts.append(block[:remaining])
                break
            parts.append(block)
            total += len(block)

        return "\n\n".join(parts)


temp_context_service = TempContextService()
