"""文档分块服务模块 - 支持PDF、DOCX、PPTX、MD、TXT等多种文档格式的加载和智能分块"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional
import os
from collections import defaultdict

import fitz  # PyMuPDF - 用于PDF解析
from docx import Document as DocxDocument
from docx.text.paragraph import Paragraph
from docx.table import Table
from docx.oxml.text.paragraph import CT_P
from docx.oxml.table import CT_Tbl
from langchain_core.documents import Document

try:
    # 尝试导入unstructured库用于PPT/PPTX解析
    from unstructured.partition.pptx import partition_pptx
    from unstructured.partition.ppt import partition_ppt
except Exception:
    partition_pptx = None
    partition_ppt = None


# Markdown 标题识别正则表达式（匹配 # 到 ###### 开头的标题）
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)")
# 句子切分正则表达式（在中文或英文标点后切分）
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？.!?])\s+")


@dataclass
class TextBlock:
    """文本块数据类：用于存储文本内容及其元数据
    
    属性:
        text: 文本内容
        meta: 元数据字典（如页码、段落号、标题路径等）
    """
    text: str
    meta: Dict[str, Any]


class DocumentChunkingService:
    """文档分块服务类：负责加载各类文档并智能切分为适合RAG检索的文本块
    
    支持的文档格式:
        - PDF (.pdf): 使用PyMuPDF解析
        - Word (.docx): 使用python-docx解析
        - PowerPoint (.pptx, .ppt): 使用unstructured解析
        - Markdown (.md): 支持标题层级结构
        - 纯文本 (.txt): 通用文本处理
    """
    
    def __init__(
        self,
        default_chunk_size: int = 600,
        default_chunk_overlap: int = 60,
        per_type: Optional[Dict[str, tuple[Optional[int], Optional[int]]]] = None,
    ):
        """初始化文档分块服务
        
        Args:
            default_chunk_size: 默认分块大小（字符数），默认600
            default_chunk_overlap: 默认分块重叠大小（字符数），默认60
            per_type: 按文件类型的分块参数覆盖配置，格式为 {".pdf": (chunk_size, chunk_overlap)}
        """
        # 全局默认分块参数（按字符长度）
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
        """加载文档并分块：完整的文档处理入口函数
        
        处理流程:
            1. 根据文件类型加载文档并提取文本块
            2. 获取对应文件类型的分块参数
            3. 将文本块智能切分为适合RAG的分块
            4. 组装元数据并返回LangChain Document对象列表
        
        Args:
            file_path: 文档文件路径
            file_type: 文档类型（如.pdf、.docx等）
            base_meta: 基础元数据字典（可选，会合并到最终元数据中）
            
        Returns:
            LangChain Document对象列表，每个对象包含分块内容和元数据
        """
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
        """获取分块参数：根据文件类型返回对应的分块大小和重叠大小
        
        Args:
            file_type: 文档文件类型
            
        Returns:
            元组(chunk_size, chunk_overlap)
        """
        size_override, overlap_override = self.per_type.get(file_type, (None, None))
        chunk_size = size_override if size_override else self.default_chunk_size
        chunk_overlap = overlap_override if overlap_override is not None else self.default_chunk_overlap
        chunk_size = max(100, int(chunk_size))
        chunk_overlap = max(0, min(int(chunk_overlap), chunk_size // 2))
        return chunk_size, chunk_overlap

    def _load_blocks(self, file_path: str, file_type: str) -> List[TextBlock]:
        """根据文件类型加载文本块：分发到对应的文件类型的加载方法
        
        Args:
            file_path: 文档文件路径
            file_type: 文档文件类型
            
        Returns:
            TextBlock对象列表
        """
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
        # 回退：作为纯文本处理
        return self._load_txt(file_path)

    def _load_txt(self, file_path: str) -> List[TextBlock]:
        """加载纯文本文件
        
        Args:
            file_path: 文本文件路径
            
        Returns:
            包含完整文本的TextBlock对象列表
        """
        text = self._read_text_file(file_path)
        return [TextBlock(text=text, meta={})]

    def _load_md(self, file_path: str) -> List[TextBlock]:
        """加载Markdown文件：支持标题层级结构
        
        Args:
            file_path: Markdown文件路径
            
        Returns:
            按标题分割的TextBlock对象列表，包含标题路径元数据
        """
        text = self._read_text_file(file_path)
        return self._split_md_to_blocks(text)

    def _load_pdf(self, file_path: str) -> List[TextBlock]:
        """加载PDF文件：使用PyMuPDF解析每页文本
        
        Args:
            file_path: PDF文件路径
            
        Returns:
            按页分割的TextBlock对象列表，包含页码元数据
        """
        blocks: List[TextBlock] = []
        with fitz.open(file_path) as doc:
            for page_idx in range(doc.page_count):
                page = doc.load_page(page_idx)
                text = self._extract_pdf_page_text(page)
                if text.strip():
                    blocks.append(TextBlock(text=text, meta={"page": page_idx + 1}))
        return blocks

    def _load_docx(self, file_path: str) -> List[TextBlock]:
        """加载DOCX文件：按段落和表格顺序提取文本
        
        Args:
            file_path: Word文档文件路径
            
        Returns:
            包含段落、表格、页眉页脚的TextBlock对象列表
        """
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
        """加载PPT/PPTX文件：使用unstructured库按幻灯片聚合文本
        
        Args:
            file_path: PowerPoint文件路径
            file_type: 文件类型（.pptx或.ppt）
            
        Returns:
            按幻灯片聚合的TextBlock对象列表，包含幻灯片号元数据
            
        Raises:
            RuntimeError: 当unstructured库不可用时
        """
        if file_type == ".pptx" and partition_pptx:
            elements = partition_pptx(filename=file_path)
        elif file_type == ".ppt" and partition_ppt:
            elements = partition_ppt(filename=file_path)
        else:
            raise RuntimeError("PPT/PPTX解析需要unstructured库的pptx支持。")

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
        """将Markdown文本分割为带标题路径的块：支持标题层级结构
        
        处理逻辑:
            - 识别 # 到 ###### 的标题
            - 维护标题栈来跟踪当前标题路径
            - 遇到新标题时输出当前块并更新标题栈
            - 代码块中的 # 不被识别为标题
        
        Args:
            text: Markdown文本内容
            
        Returns:
            按标题分割的TextBlock对象列表
        """
        blocks: List[TextBlock] = []
        heading_stack: List[tuple[int, str]] = []
        current_lines: List[str] = []
        in_code_block = False

        def flush() -> None:
            """输出当前块：将缓存的内容输出为一个TextBlock"""
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
        """将文本块智能分块：支持段落合并、重叠和长文本分割
        
        分块策略:
            1. 优先按段落合并，保持内容完整性
            2. 单个段落过长时按句子分割
            3. 句子也过长时进行硬分割
            4. 分块间保持指定重叠，避免上下文断裂
        
        Args:
            blocks: 原始TextBlock对象列表
            chunk_size: 分块大小（字符数）
            chunk_overlap: 分块重叠大小（字符数）
            
        Returns:
            分块后的TextBlock对象列表
        """
        chunks: List[TextBlock] = []
        buffer = ""
        buffer_meta: List[Dict[str, Any]] = []
        buffer_has_new = False
        overlap_seed = ""
        overlap_meta: Optional[Dict[str, Any]] = None

        def emit(text: str, metas: List[Dict[str, Any]]) -> None:
            """输出一个块：将缓存的内容输出为一个TextBlock，并设置重叠种子
            
            Args:
                text: 分块文本内容
                metas: 元数据列表
            """
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
        """按段落分割文本：识别两个或以上换行符作为段落分隔
        
        Args:
            text: 待分割的文本
            
        Returns:
            段落列表
        """
        text = text.strip()
        if not text:
            return []
        return [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]

    def _split_long_text(self, text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
        """分割长文本：优先按句子分割，句子过长时使用硬分割
        
        分割策略:
            1. 按句子标点分割
            2. 尝试合并句子到不超过chunk_size
            3. 单个句子过长时使用硬分割
            4. 保持分块间重叠
        
        Args:
            text: 长文本内容
            chunk_size: 分块大小（字符数）
            chunk_overlap: 分块重叠大小（字符数）
            
        Returns:
            分块后的文本列表
        """
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
        """硬分割文本：按字符直接分割（最后的兜底策略）
        
        Args:
            text: 待分割的文本
            chunk_size: 分块大小（字符数）
            chunk_overlap: 分块重叠大小（字符数）
            
        Returns:
            分块后的文本列表
        """
        parts: List[str] = []
        step = max(1, chunk_size - chunk_overlap)
        for start in range(0, len(text), step):
            parts.append(text[start : start + chunk_size])
        return parts

    def _normalize_text(self, text: str, soft_wrap: bool = False) -> str:
        """规范化文本：统一换行符、处理软换行、压缩空白等
        
        Args:
            text: 待规范化的文本
            soft_wrap: 是否处理软换行（将单行换行替换为空格）
            
        Returns:
            规范化后的文本
        """
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if soft_wrap:
            text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
            # 英文断词修复（如 "informa-\ntion" -> "information"）
            text = re.sub(r"([A-Za-z])-\s+([A-Za-z])", r"\1\2", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _merge_meta(self, metas: List[Dict[str, Any]]) -> Dict[str, Any]:
        """合并元数据：将多个TextBlock的元数据合并为一个
        
        合并策略:
            - 页码、幻灯片号、段落号等：去重后排序
            - Markdown标题：使用最后一个块的标题
            
        Args:
            metas: 元数据字典列表
            
        Returns:
            合并后的元数据字典
        """
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
        """读取文本文件：尝试多种编码以提高兼容性
        
        尝试的编码顺序: utf-8-sig → utf-8 → gb18030 → gbk → 二进制读取（忽略错误）
        
        Args:
            file_path: 文本文件路径
            
        Returns:
            文件内容字符串
        """
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
        """提取PDF页面文本：优先使用text模式，内容过少时使用blocks模式
        
        Args:
            page: PyMuPDF页面对象
            
        Returns:
            页面文本内容
        """
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
        """遍历DOCX块：按文档原始顺序遍历段落和表格
        
        Args:
            doc: python-docx文档对象
            
        Yields:
            Paragraph或Table对象
        """
        for child in doc.element.body.iterchildren():
            if isinstance(child, CT_P):
                yield Paragraph(child, doc)
            elif isinstance(child, CT_Tbl):
                yield Table(child, doc)

    def _extract_docx_table_text(self, table: Table) -> str:
        """提取DOCX表格文本：将表格转换为文本格式
        
        表格格式:
            - 行之间用换行分隔
            - 单元格之间用" | "分隔
            
        Args:
            table: python-docx表格对象
            
        Returns:
            表格文本内容
        """
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
