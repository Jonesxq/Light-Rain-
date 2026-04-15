"""知识库领域数据结构定义。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ChunkCandidate:
    """原始分片候选项，用于 BM25 检索与评估流程。"""

    parent_id: str
    content: str
    structured_meta: Optional[dict] = None


@dataclass
class SearchItem:
    """统一后的检索结果项。"""

    content: str
    meta: Optional[dict] = None
