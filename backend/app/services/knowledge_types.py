"""知识库检索相关类型与 BM25 基础工具模块"""

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import List, Optional

try:
    import jieba
except Exception:
    jieba = None

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]")


def _tokenize(text: str) -> List[str]:
    """轻量分词：优先使用 jieba，否则退化为字符切分
    
    Args:
        text: 待分词的文本
        
    Returns:
        分词后的令牌列表（小写）
    """
    if not text:
        return []
    if jieba:
        return [t.strip().lower() for t in jieba.cut(text) if t.strip()]
    return [t.lower() for t in _TOKEN_PATTERN.findall(text)]


class BM25Index:
    """BM25 索引：用于快速计算文本相关性得分
    
    BM25 是一种用于信息检索的概率性排序算法，常用于搜索系统中的相关性计算
    """
    def __init__(self, tokenized_corpus: List[List[str]], k1: float = 1.5, b: float = 0.75):
        """初始化 BM25 索引（预先统计文档频率、文档长度和逆文档频率）
        
        Args:
            tokenized_corpus: 已分词的语料库列表
            k1: BM25参数，控制术语频率饱和度（默认1.5）
            b: BM25参数，控制文档长度归一化（默认0.75）
        """
        self.k1 = k1
        self.b = b
        self.doc_freqs: List[Counter] = []
        self.doc_len: List[int] = []
        self.idf: dict[str, float] = {}
        self.avgdl: float = 0.0

        if not tokenized_corpus:
            return

        df = defaultdict(int)
        total_len = 0
        for doc_tokens in tokenized_corpus:
            freqs = Counter(doc_tokens)
            self.doc_freqs.append(freqs)
            self.doc_len.append(len(doc_tokens))
            total_len += len(doc_tokens)
            for term in freqs:
                df[term] += 1

        doc_count = len(tokenized_corpus)
        self.avgdl = (total_len / doc_count) if doc_count else 0.0
        self.idf = {
            term: math.log(1 + (doc_count - freq + 0.5) / (freq + 0.5))
            for term, freq in df.items()
        }

    def get_scores(self, query_tokens: List[str]) -> List[float]:
        """计算查询词在语料中的 BM25 得分
        
        Args:
            query_tokens: 查询词的令牌列表
            
        Returns:
            每个文档的BM25得分列表，顺序与输入语料库一致
        """
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


@dataclass
class ChunkCandidate:
    """候选分片：包含原始内容和结构化元数据
    
    Attributes:
        parent_id: 父文档ID
        content: 分片内容
        structured_meta: 结构化元数据字典（可选）
    """
    parent_id: str
    content: str
    structured_meta: Optional[dict] = None


@dataclass
class SearchItem:
    """检索结果条目：包含内容和元数据
    
    Attributes:
        content: 检索到的内容
        meta: 元数据字典（可选）
    """
    content: str
    meta: Optional[dict] = None
