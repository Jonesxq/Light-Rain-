"""聊天附件上下文服务：负责提取附件文本并按查询检索临时上下文。"""

from __future__ import annotations

from typing import List

from app.core.config.settings import settings
from app.crud.chat_attachment import chat_attachment_crud
from app.services.shared.bm25 import BM25Index, _tokenize
from app.services.shared.document_chunking import DocumentChunkingService, TextBlock


class AttachmentContextService:
    """处理附件文本提取与临时上下文构建。"""

    def __init__(self):
        """初始化按文件类型分块的文档切分器。"""
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
        """将纯文本切分为可检索的小片段。"""
        if not text:
            return []
        normalized = self.chunker._normalize_text(text)
        if not normalized:
            return []
        paragraphs = self.chunker._split_paragraphs(normalized)
        blocks = [TextBlock(text=paragraph, meta={}) for paragraph in paragraphs if paragraph]
        chunk_size, chunk_overlap = self.chunker._get_chunk_params(".txt")
        chunks = self.chunker._chunk_blocks(blocks, chunk_size, chunk_overlap)
        return [chunk.text for chunk in chunks if chunk.text]

    def _extract_text_from_document(self, file_path: str, file_type: str) -> tuple[str, List[str]]:
        """从文档类附件提取全文与分块结果。"""
        docs = self.chunker.load_and_split(file_path, file_type)
        chunks = [doc.page_content.strip() for doc in docs if doc.page_content and doc.page_content.strip()]
        extracted_text = "\n\n".join(chunks)
        return extracted_text, chunks

    def _extract_text_from_image(self, file_path: str) -> str:
        """通过 OCR 从图片附件中抽取文本。"""
        try:
            from PIL import Image
        except Exception as exc:
            raise ValueError("Image parsing failed: Pillow is required.") from exc
        try:
            import pytesseract
        except Exception as exc:
            raise ValueError("Image parsing failed: pytesseract/Tesseract is required.") from exc

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
        """创建附件记录，并预处理可用于检索的文本内容。"""
        extracted_text = ""
        chunks: List[str] = []

        if file_type in {".png", ".jpg", ".jpeg"}:
            extracted_text = self._extract_text_from_image(file_path)
            chunks = self._chunk_text(extracted_text)
        else:
            extracted_text, chunks = self._extract_text_from_document(file_path, file_type)

        if extracted_text and len(extracted_text) > 20000:
            extracted_text = extracted_text[:20000]

        return await chat_attachment_crud.create_attachment(
            db=db,
            user_id=user_id,
            file_name=file_name,
            file_type=file_type,
            file_size=file_size,
            file_path=file_path,
            extracted_text=extracted_text,
            chunks=chunks,
        )

    async def get_context_for_user(
        self,
        db,
        user_id: int,
        query: str,
        top_k: int = 5,
        max_chars: int = 4000,
    ) -> str:
        """根据用户查询从附件分片中召回上下文。"""
        attachments = await chat_attachment_crud.list_attachments(db, user_id)
        if not attachments:
            return ""

        items = []
        for attachment in attachments:
            for chunk in attachment.chunks or []:
                if not chunk:
                    continue
                text = str(chunk).strip()
                if not text:
                    continue
                items.append({"text": text, "file_name": attachment.file_name})

        if not items:
            return ""

        ranked_indices = list(range(len(items)))
        query_tokens = _tokenize(query or "")
        if query_tokens:
            bm25 = BM25Index([_tokenize(item["text"]) for item in items])
            scores = bm25.get_scores(query_tokens)
            if scores:
                ranked_indices = sorted(range(len(scores)), key=lambda index: scores[index], reverse=True)

        parts: List[str] = []
        total = 0
        for index in ranked_indices[:top_k]:
            item = items[index]
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


temp_context_service = AttachmentContextService()
