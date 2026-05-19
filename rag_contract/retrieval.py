from __future__ import annotations

import json
import os
from dataclasses import asdict
from typing import Any

import jieba
from rank_bm25 import BM25Okapi

from .chunking import Chunk


# 中文分词函数
def _tokenize(text: str) -> list[str]:
    # jieba for Chinese; keep alnum tokens too
    text = text.strip()
    if not text:
        return []
    return [t for t in jieba.lcut(text) if t.strip()]

# 混合检索器，结合 BM25 和向量检索
class HybridRetriever:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        corpus = [_tokenize(c.text) for c in chunks]
        self.bm25 = BM25Okapi(corpus)

    @classmethod
    def from_jsonl(cls, path: str) -> "HybridRetriever":
        chunks: list[Chunk] = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                chunks.append(Chunk(**d))
        return cls(chunks)

    def bm25_scores(self, query: str) -> list[float]:
        q = _tokenize(query)
        return list(self.bm25.get_scores(q))


    # 合并向量检索和BM25检索结果，向量检索结果权重为0.65 + BM25检索结果权重为0.35
    # 优先考虑向量检索结果，再考虑BM25检索结果
    def combine_scores(
        self,
        vector_hits: list[tuple[int, float]],
        bm25_scores: list[float],
        vector_weight: float = 0.65,
        bm25_weight: float = 0.35,
    ) -> list[tuple[int, float]]:
        """
        vector_hits: list of (chunk_idx, vector_score) where vector_score is cosine similarity-ish.
        Combine by min-max normalization inside the hit set, plus BM25 normalization.

        Weights are configurable to support hybrid-on-demand architecture:
        when vector confidence is high, set vector_weight=1.0, bm25_weight=0.0
        to skip the BM25 path entirely.
        """
        if not vector_hits:
            return []

        idxs = [i for i, _ in vector_hits]
        vec = [s for _, s in vector_hits]
        bm = [bm25_scores[i] for i in idxs]

        def norm(xs: list[float]) -> list[float]:
            lo = min(xs)
            hi = max(xs)
            if hi - lo < 1e-9:
                return [0.0 for _ in xs]
            return [(x - lo) / (hi - lo) for x in xs]

        vec_n = norm(vec)
        bm_n = norm(bm)

        combined = []
        for k, idx in enumerate(idxs):
            score = vector_weight * vec_n[k] + bm25_weight * bm_n[k]
            combined.append((idx, score))
        combined.sort(key=lambda x: x[1], reverse=True)
        return combined

    def should_activate_bm25(
        self,
        vector_hits: list[tuple[int, float]],
        confidence_threshold: float = 0.75,
    ) -> bool:
        """Hybrid-on-Demand gate: decide whether BM25 re-ranking is needed.

        Returns True when the top-1 vector cosine similarity falls below the
        confidence threshold, indicating that the semantic match may be weak
        and BM25 keyword matching should be activated as a safety net.

        This implements the architecture recommended in the IEEE paper:
        vector-only as primary path, BM25 re-ranking on demand.
        """
        if not vector_hits:
            return True  # No vector results at all — definitely need BM25
        top1_score = vector_hits[0][1]
        return top1_score < confidence_threshold

