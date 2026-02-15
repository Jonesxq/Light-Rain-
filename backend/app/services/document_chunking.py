"""services/document_chunking.py."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional
import os
from collections import defaultdict

import fitz  # PyMuPDF
from docx import Document as DocxDocument
from docx.text.paragraph import Paragraph
from docx.table import Table
from docx.oxml.text.paragraph import CT_P
from docx.oxml.table import CT_Tbl
from langchain_core.documents import Document

try:
    from unstructured.partition.pptx import partition_pptx
    from unstructured.partition.ppt import partition_ppt
except Exception:
    partition_pptx = None
    partition_ppt = None


# Markdown 标题识别与句子切分规则
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？.!?])\s+")


@dataclass
class TextBlock:
    """TextBlock ??"""
    text: str
    meta: Dict[str, Any]


class DocumentChunkingService:

    """DocumentChunkingService ??"""
    def __init__(
        self,
        default_chunk_size: int = 600,
        default_chunk_overlap: int = 60,
        per_type: Optional[Dict[str, tuple[Optional[int], Optional[int]]]] = None,
    ):
        # 全局默认分块参数（按字符长度）
        """__init__ ???"""
        self.default_chunk_size = max(100, default_chunk_size)
        self.default_chunk_overlap = max(0, min(default_chunk_overlap, self.default_chunk_size // 2))
        # 按文件类型覆盖配置（None 表示继承默认值）
        self.per_type = per_type or {}

    def load_and_split(
        self,
        file_path: str,
        file_type: str,
        base_meta: Optional[Dict[str, Any]] = None
    ) -> List[Document]:
        """load_and_split ???"""
        file_type = file_type.lower()
        blocks = self._load_blocks(file_path, file_type)
        chunk_size, chunk_overlap = self._get_chunk_params(file_type)
        chunks = self._chunk_blocks(blocks, chunk_size, chunk_overlap)

        source_meta = {
            "file_name": os.path.basename(file_path),
            "file_path": file_path,
            "file_type": file_type,
        }

        documents: List[Document] = []
        for idx, c in enumerate(chunks):
            # 组装结构化元数据：来源 + 位置 + 分块信息 + 业务注入
            meta: Dict[str, Any] = {}
            if base_meta:
                meta.update(base_meta)

            # 合并来源信息（base_meta 中已有 source 时优先保留）
            existing_source = meta.get("source", {}) if isinstance(meta.get("source"), dict) else {}
            for key, value in source_meta.items():
                if value is not None and key not in existing_source:
                    existing_source[key] = value
            meta["source"] = existing_source

            # 结构化位置信息（页码/段落/标题路径等）
            meta["loc"] = c.meta or {}

            # 分块统计信息
            meta["chunk"] = {
                "index": idx,
                "char_len": len(c.text),
                "size": chunk_size,
                "overlap": chunk_overlap,
            }

            documents.append(Document(page_content=c.text, metadata=meta))

        return documents

    def _get_chunk_params(self, file_type: str) -> tuple[int, int]:
        """_get_chunk_params ???"""
        size_override, overlap_override = self.per_type.get(file_type, (None, None))
        chunk_size = size_override if size_override else self.default_chunk_size
        chunk_overlap = overlap_override if overlap_override is not None else self.default_chunk_overlap
        chunk_size = max(100, int(chunk_size))
        chunk_overlap = max(0, min(int(chunk_overlap), chunk_size // 2))
        return chunk_size, chunk_overlap

    def _load_blocks(self, file_path: str, file_type: str) -> List[TextBlock]:
        """_load_blocks ???"""
        if file_type == ".pdf":
            return self._load_pdf(file_path)
        if file_type == ".docx":
            return self._load_docx(file_path)
        if file_type == ".md":
            return self._load_md(file_path)
        if file_type == ".txt":
            return self._load_txt(file_path)
        if file_type in {".pptx", ".ppt"}:
            return self._load_ppt(file_path, file_type)
        # Fallback: treat as plain text
        return self._load_txt(file_path)

    def _load_txt(self, file_path: str) -> List[TextBlock]:
        """_load_txt ???"""
        text = self._read_text_file(file_path)
        return [TextBlock(text=text, meta={})]

    def _load_md(self, file_path: str) -> List[TextBlock]:
        """_load_md ???"""
        text = self._read_text_file(file_path)
        return self._split_md_to_blocks(text)

    def _load_pdf(self, file_path: str) -> List[TextBlock]:
        """_load_pdf ???"""
        blocks: List[TextBlock] = []
        with fitz.open(file_path) as doc:
            for page_idx in range(doc.page_count):
                page = doc.load_page(page_idx)
                text = self._extract_pdf_page_text(page)
                if text.strip():
                    blocks.append(TextBlock(text=text, meta={"page": page_idx + 1}))
        return blocks

    def _load_docx(self, file_path: str) -> List[TextBlock]:
        """_load_docx ???"""
        blocks: List[TextBlock] = []
        doc = DocxDocument(file_path)
        paragraph_idx = 0
        table_idx = 0

        # 1) 按文档原始顺序遍历段落/表格
        for item in self._iter_docx_blocks(doc):
            if isinstance(item, Paragraph):
                paragraph_idx += 1
                text = self._normalize_text(item.text)
                if text.strip():
                    blocks.append(TextBlock(text=text, meta={"paragraph": paragraph_idx}))
            elif isinstance(item, Table):
                table_idx += 1
                text = self._extract_docx_table_text(item)
                if text.strip():
                    blocks.append(TextBlock(text=text, meta={"table": table_idx}))

        # 2) 补充页眉/页脚（若存在）
        for section_idx, section in enumerate(doc.sections, start=1):
            header_text = self._normalize_text(section.header.text or "")
            if header_text.strip():
                blocks.append(TextBlock(text=header_text, meta={"header": section_idx}))
            footer_text = self._normalize_text(section.footer.text or "")
            if footer_text.strip():
                blocks.append(TextBlock(text=footer_text, meta={"footer": section_idx}))
        return blocks

    def _load_ppt(self, file_path: str, file_type: str) -> List[TextBlock]:
        """_load_ppt ???"""
        if file_type == ".pptx" and partition_pptx:
            elements = partition_pptx(filename=file_path)
        elif file_type == ".ppt" and partition_ppt:
            elements = partition_ppt(filename=file_path)
        else:
            raise RuntimeError("PPT/PPTX parsing requires unstructured with pptx support.")

        # 按幻灯片聚合文本，避免碎片化
        slide_texts: Dict[int, List[str]] = defaultdict(list)
        orphan_texts: List[str] = []
        for el in elements:
            text = getattr(el, "text", None) or str(el)
            text = self._normalize_text(text)
            if not text.strip() or len(text.strip()) < 2:
                continue
            meta: Dict[str, Any] = {}
            meta_obj = getattr(el, "metadata", None)
            slide = getattr(meta_obj, "page_number", None) if meta_obj else None
            if slide:
                slide_texts[int(slide)].append(text)
            else:
                orphan_texts.append(text)

        blocks: List[TextBlock] = []
        for slide, texts in sorted(slide_texts.items(), key=lambda x: x[0]):
            merged = "\n".join(texts).strip()
            if merged:
                blocks.append(TextBlock(text=merged, meta={"slide": slide}))
        # 无页码的文本块单独追加
        for text in orphan_texts:
            blocks.append(TextBlock(text=text, meta={}))
        return blocks

    def _split_md_to_blocks(self, text: str) -> List[TextBlock]:
        """_split_md_to_blocks ???"""
        blocks: List[TextBlock] = []
        heading_stack: List[tuple[int, str]] = []
        current_lines: List[str] = []
        in_code_block = False

        def flush() -> None:
            """flush ???"""
            content = "\n".join(current_lines).strip()
            if not content:
                return
            title_path = " > ".join([t for _, t in heading_stack]) if heading_stack else ""
            meta = {"md_headings": title_path} if title_path else {}
            blocks.append(TextBlock(text=content, meta=meta))

        for line in text.splitlines():
            stripped = line.strip()
            # 处理代码块，避免误把代码中的 # 当作标题
            if stripped.startswith("```"):
                in_code_block = not in_code_block
                current_lines.append(line)
                continue
            if not in_code_block and (match := _HEADING_RE.match(stripped)):
                flush()
                current_lines = []
                level = len(match.group(1))
                title = match.group(2).strip()
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()
                heading_stack.append((level, title))
                current_lines.append(title)
            else:
                current_lines.append(line)

        flush()
        return blocks

    def _chunk_blocks(self, blocks: List[TextBlock], chunk_size: int, chunk_overlap: int) -> List[TextBlock]:
        """_chunk_blocks ???"""
        chunks: List[TextBlock] = []
        buffer = ""
        buffer_meta: List[Dict[str, Any]] = []
        buffer_has_new = False
        overlap_seed = ""
        overlap_meta: Optional[Dict[str, Any]] = None

        def emit(text: str, metas: List[Dict[str, Any]]) -> None:
            """emit ???"""
            nonlocal buffer, buffer_meta, buffer_has_new, overlap_seed, overlap_meta
            text = text.strip()
            if not text:
                return
            meta = self._merge_meta(metas)
            chunks.append(TextBlock(text=text, meta=meta))
            if chunk_overlap > 0:
                overlap_seed = text[-chunk_overlap:]
                overlap_meta = metas[-1] if metas else None
            else:
                overlap_seed = ""
                overlap_meta = None
            buffer = overlap_seed
            buffer_meta = [overlap_meta] if overlap_meta else []
            buffer_has_new = False

        for block in blocks:
            text = self._normalize_text(block.text)
            if not text.strip():
                continue
            for para in self._split_paragraphs(text):
                if not para:
                    continue
                if len(para) > chunk_size:
                    if buffer.strip() and buffer_has_new:
                        emit(buffer, buffer_meta)
                    for part in self._split_long_text(para, chunk_size, chunk_overlap):
                        emit(part, [block.meta])
                    continue

                candidate = f"{buffer}\n\n{para}".strip() if buffer else para
                if len(candidate) <= chunk_size:
                    buffer = candidate
                    buffer_meta.append(block.meta)
                    buffer_has_new = True
                else:
                    if buffer.strip() and buffer_has_new:
                        emit(buffer, buffer_meta)
                    buffer = para
                    buffer_meta = [block.meta]
                    buffer_has_new = True

        if buffer.strip() and (buffer_has_new or not overlap_seed):
            emit(buffer, buffer_meta)

        return chunks

    def _split_paragraphs(self, text: str) -> List[str]:
        """_split_paragraphs ???"""
        text = text.strip()
        if not text:
            return []
        return [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]

    def _split_long_text(self, text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
        """_split_long_text ???"""
        sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
        if not sentences:
            return [text]

        parts: List[str] = []
        current = ""
        for sent in sentences:
            candidate = f"{current} {sent}".strip() if current else sent
            if len(candidate) <= chunk_size:
                current = candidate
                continue
            if current:
                parts.append(current)
                if chunk_overlap > 0:
                    current = current[-chunk_overlap:] + " " + sent
                else:
                    current = sent
            else:
                # 单个句子长度超过块大小时，回退到硬分割
                parts.extend(self._hard_split(sent, chunk_size, chunk_overlap))
                current = ""

        if current:
            parts.append(current)

        return parts

    def _hard_split(self, text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
        """_hard_split ???"""
        parts: List[str] = []
        step = max(1, chunk_size - chunk_overlap)
        for start in range(0, len(text), step):
            parts.append(text[start : start + chunk_size])
        return parts

    def _normalize_text(self, text: str, soft_wrap: bool = False) -> str:
        """_normalize_text ???"""
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if soft_wrap:
            text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
            # 英文断词修复（如 "informa-\ntion" -> "information"）
            text = re.sub(r"([A-Za-z])-\s+([A-Za-z])", r"\1\2", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _merge_meta(self, metas: List[Dict[str, Any]]) -> Dict[str, Any]:
        """_merge_meta ???"""
        merged: Dict[str, Any] = {}
        pages = {m.get("page") for m in metas if m and m.get("page")}
        if pages:
            merged["pages"] = sorted(pages)
        slides = {m.get("slide") for m in metas if m and m.get("slide")}
        if slides:
            merged["slides"] = sorted(slides)
        paragraphs = {m.get("paragraph") for m in metas if m and m.get("paragraph")}
        if paragraphs:
            merged["paragraphs"] = sorted(paragraphs)
        tables = {m.get("table") for m in metas if m and m.get("table")}
        if tables:
            merged["tables"] = sorted(tables)
        headers = {m.get("header") for m in metas if m and m.get("header")}
        if headers:
            merged["headers"] = sorted(headers)
        footers = {m.get("footer") for m in metas if m and m.get("footer")}
        if footers:
            merged["footers"] = sorted(footers)
        headings = [m.get("md_headings") for m in metas if m and m.get("md_headings")]
        if headings:
            merged["md_headings"] = headings[-1]
        return merged

    def _read_text_file(self, file_path: str) -> str:
        """_read_text_file ???"""
        encodings = ["utf-8-sig", "utf-8", "gb18030", "gbk"]
        for enc in encodings:
            try:
                with open(file_path, "r", encoding=enc, errors="strict") as f:
                    return f.read()
            except Exception:
                continue
        # 最后兜底：二进制读取 + 忽略无法解码的字符
        with open(file_path, "rb") as f:
            raw = f.read()
        return raw.decode("utf-8", errors="ignore")

    def _extract_pdf_page_text(self, page: fitz.Page) -> str:
        """_extract_pdf_page_text ???"""
        try:
            text = page.get_text("text") or ""
        except Exception:
            text = ""

        # 若主路径文本很少，尝试使用 blocks 兜底
        if len(text.strip()) < 20:
            try:
                blocks = page.get_text("blocks") or []
                # blocks: (x0, y0, x1, y1, "text", block_no, block_type)
                blocks = sorted(blocks, key=lambda b: (b[1], b[0]))
                text = "\n".join([b[4] for b in blocks if len(b) > 4 and b[4]])
            except Exception:
                pass

        return self._normalize_text(text, soft_wrap=True)

    def _iter_docx_blocks(self, doc: DocxDocument) -> Iterable[Paragraph | Table]:
        """_iter_docx_blocks ???"""
        for child in doc.element.body.iterchildren():
            if isinstance(child, CT_P):
                yield Paragraph(child, doc)
            elif isinstance(child, CT_Tbl):
                yield Table(child, doc)

    def _extract_docx_table_text(self, table: Table) -> str:
        """_extract_docx_table_text ???"""
        rows: List[str] = []
        for row in table.rows:
            cells = []
            for cell in row.cells:
                cell_text = self._normalize_text(cell.text or "")
                if cell_text:
                    cells.append(cell_text)
            if cells:
                rows.append(" | ".join(cells))
        return "\n".join(rows).strip()
