"""文档分块服务模块 - 支持PDF、DOCX、PPTX、MD、TXT等多种文档格式的加载和智能分块"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional
import os
from collections import defaultdict

from app.core.logger import logger_manager

logger = logger_manager.get_logger(__name__)

from langchain_core.documents import Document

try:
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, AcceleratorOptions, AcceleratorDevice
    from docling.datamodel.settings import settings as docling_settings

    def _env_bool(name: str, default: bool) -> bool:
        value = os.getenv(name)
        if value is None:
            return default
        return value.strip().lower() in {"1", "true", "yes", "on"}

    def _env_int(name: str, default: int, minimum: int = 1) -> int:
        try:
            return max(minimum, int(os.getenv(name, str(default))))
        except ValueError:
            return default

    _docling_num_threads = _env_int("DOCLING_NUM_THREADS", 1)
    _docling_page_batch_size = _env_int("DOCLING_PAGE_BATCH_SIZE", 1)
    docling_settings.perf.page_batch_size = _docling_page_batch_size
    docling_settings.perf.page_batch_concurrency = _env_int("DOCLING_PAGE_BATCH_CONCURRENCY", 1)
    docling_settings.perf.doc_batch_concurrency = _env_int("DOCLING_DOC_BATCH_CONCURRENCY", 1)

    _docling_device = AcceleratorDevice.CUDA if _env_bool("DOCLING_USE_CUDA", False) else AcceleratorDevice.CPU
    _pipeline_options = PdfPipelineOptions(
        accelerator_options=AcceleratorOptions(num_threads=_docling_num_threads, device=_docling_device),
        images_scale=max(0.5, float(os.getenv("DOCLING_IMAGES_SCALE", "1.0"))),
        do_table_structure=_env_bool("DOCLING_TABLE_STRUCTURE", False),
        do_ocr=_env_bool("DOCLING_OCR", False),
        force_backend_text=_env_bool("DOCLING_FORCE_BACKEND_TEXT", True),
        ocr_batch_size=_env_int("DOCLING_OCR_BATCH_SIZE", 1),
        layout_batch_size=_env_int("DOCLING_LAYOUT_BATCH_SIZE", 1),
        table_batch_size=_env_int("DOCLING_TABLE_BATCH_SIZE", 1),
        queue_max_size=_env_int("DOCLING_QUEUE_MAX_SIZE", 4),
    )
    _pipeline_options.generate_page_images = False 
    
    _GLOBAL_CONVERTER = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=_pipeline_options)
        }
    )
except ImportError:
    DocumentConverter = None
    _GLOBAL_CONVERTER = None


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
        - PDF (.pdf): 使用 Docling 转换为 Markdown 后解析
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
        logger.info(f"开始加载和解析文件: {file_path} (类型: {file_type})")
        
        blocks = self._load_blocks(file_path, file_type)
        chunk_size, chunk_overlap = self._get_chunk_params(file_type)
        
        logger.info(f"成功提取 {len(blocks)} 个文本块，开始智能分块 (size={chunk_size}, overlap={chunk_overlap})")
        chunks = self._chunk_blocks(blocks, chunk_size, chunk_overlap)
        
        logger.info(f"智能分块完成，共生成 {len(chunks)} 个 Chunk。开始组装元数据...")

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
        if file_type == ".md":
            return self._load_md(file_path)
        if file_type == ".txt":
            return self._load_txt(file_path)
        if file_type in {".pdf", ".docx", ".pptx", ".ppt"}:
            return self._load_via_docling_to_md(file_path)
        # 回退：作为纯文本处理
        return self._load_txt(file_path)

    def _load_via_docling_to_md(self, file_path: str) -> List[TextBlock]:
        """使用Docling统一解析为Markdown文本块
        
        Args:
            file_path: 文档文件路径
            
        Returns:
            按Markdown标题分割的TextBlock对象列表
        """
        if not _GLOBAL_CONVERTER:
            raise RuntimeError("docling 库未安装或初始化失败，无法处理该类型文档")
        
        logger.info(f"使用 Docling 转换文档: {file_path}")
        result = _GLOBAL_CONVERTER.convert(file_path)
        md_text = result.document.export_to_markdown()
        recovered_pages = self._recover_missing_docling_pages(file_path, result)
        if recovered_pages:
            md_text = "\n\n".join([md_text.strip(), *recovered_pages])
        logger.info(f"Docling 转换文档完成，将其交接给 Markdown 切块算法处理...")
        return self._split_md_to_blocks(md_text)

    def _recover_missing_docling_pages(self, file_path: str, result: Any) -> List[str]:
        missing_pages = self._missing_docling_page_numbers(result)
        if not missing_pages:
            return []

        logger.warning(f"Docling 整篇转换缺失页面 {missing_pages}，开始使用 page_range 单页恢复")
        recovered_markdown: List[str] = []
        for page_no in missing_pages:
            try:
                page_result = _GLOBAL_CONVERTER.convert(
                    file_path,
                    page_range=(page_no, page_no),
                    raises_on_error=False,
                )
            except TypeError:
                page_result = _GLOBAL_CONVERTER.convert(file_path, page_range=(page_no, page_no))
            except Exception as exc:
                logger.warning(f"Docling 单页恢复失败: page={page_no}, error={exc}")
                continue

            page_md = page_result.document.export_to_markdown().strip()
            if not page_md:
                logger.warning(f"Docling 单页恢复未返回内容: page={page_no}")
                continue

            logger.info(f"Docling 单页恢复成功: page={page_no}")
            recovered_markdown.append(f"<!-- Docling page recovery: {page_no} -->\n\n{page_md}")
        return recovered_markdown

    @staticmethod
    def _missing_docling_page_numbers(result: Any) -> List[int]:
        page_count = getattr(getattr(result, "input", None), "page_count", None)
        if not page_count:
            return []

        successful_pages = set()
        for page in getattr(result, "pages", []) or []:
            page_no = getattr(page, "page_no", None)
            if page_no is None:
                continue
            try:
                successful_pages.add(int(page_no))
            except (TypeError, ValueError):
                continue
        return [page_no for page_no in range(1, int(page_count) + 1) if page_no not in successful_pages]

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

    def _merge_short_paragraphs(self, paragraphs: List[str], min_len: int = 80) -> List[str]:
        """将过短的段落向下合并，减少碎片化文本块

        策略：若当前段落长度不足 min_len，则与下一段落合并（用双换行连接），
        直到达到 min_len 或没有更多段落为止。

        Args:
            paragraphs: 段落列表
            min_len: 短段落最小字符数阈值，默认80

        Returns:
            合并后的段落列表
        """
        if not paragraphs:
            return []
        merged: List[str] = []
        buf = paragraphs[0]
        for para in paragraphs[1:]:
            if len(buf) < min_len:
                buf = buf + "\n\n" + para
            else:
                merged.append(buf)
                buf = para
        if buf:
            merged.append(buf)
        return merged

    def _load_txt(self, file_path: str) -> List[TextBlock]:
        """加载纯文本文件为文本块列表

        处理策略:
            1. 启用软换行合并（单个换行 → 空格），避免每行被割裂为独立段落
            2. 对段落做预合并，将过短的段落归并入下一段，减少碎片 chunk

        Args:
            file_path: 文本文件路径

        Returns:
            TextBlock 列表（每段为一个块，后续由分块算法进一步切分）
        """
        text = self._read_text_file(file_path)
        # soft_wrap=True：将段内的单个换行视为空格，保留双换行作为段落分隔
        text = self._normalize_text(text, soft_wrap=True)
        if not text:
            return []
        # 按双换行切段，并合并过短段落
        raw_paras = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
        merged_paras = self._merge_short_paragraphs(raw_paras, min_len=80)
        return [TextBlock(text=p, meta={}) for p in merged_paras]

    def _load_md(self, file_path: str) -> List[TextBlock]:
        """加载 Markdown 文件为带标题层级的文本块列表

        Args:
            file_path: Markdown 文件路径

        Returns:
            按标题层级分割的 TextBlock 列表
        """
        text = self._read_text_file(file_path)
        return self._split_md_to_blocks(text)
