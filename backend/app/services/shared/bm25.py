"""共享 BM25 工具：供知识库检索与聊天附件检索复用。"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import List

try:
    import jieba
except Exception:
    jieba = None

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]")


def _tokenize(text: str) -> List[str]:
    """对中英文文本分词，优先使用 jieba，失败时走轻量正则回退。"""
    if not text:
        return []
    if jieba:
        return [token.strip().lower() for token in jieba.cut(text) if token.strip()]
    return [token.lower() for token in _TOKEN_PATTERN.findall(text)]


class BM25Index:
    """内存版 BM25 索引，用于快速相关度打分。"""

    def __init__(self, tokenized_corpus: List[List[str]], k1: float = 1.5, b: float = 0.75):
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
        """对分词后的查询计算每篇文档的 BM25 分数。"""
        if not self.doc_freqs or not query_tokens:
            return []

        scores = [0.0] * len(self.doc_freqs)
        avgdl = self.avgdl if self.avgdl > 0 else 1.0

        for term in query_tokens:
            idf = self.idf.get(term)
            if idf is None:
                continue
            for index, freqs in enumerate(self.doc_freqs):
                freq = freqs.get(term, 0)
                if not freq:
                    continue
                denom = freq + self.k1 * (1 - self.b + self.b * (self.doc_len[index] / avgdl))
                scores[index] += idf * (freq * (self.k1 + 1)) / (denom + 1e-9)

        return scores
