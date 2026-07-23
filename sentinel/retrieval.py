"""Hybrid retrieval: BM25 (implemented from scratch) + dense cosine similarity.

Scores are min-max normalized per query and combined with a weighted sum.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

import numpy as np

from .chunker import Chunk

_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)  # letters+digits, any language
_NUM_COMMA_RE = re.compile(r"(?<=\d),(?=\d)")  # '1,200' -> '1200' before tokenizing

_STOPWORDS = frozenset(
    """a an the and or but if then is are was were be been being of in on at to for
    from by with as it its this that these those he she they them his her their
    i you we us our your my me not no do does did done has have had having will
    would can could should may might must about into over under between there
    here what which who whom whose when where why how all any both each few more
    most other some such only own same so than too very s t just don now""".split()
)


def tokenize(text: str) -> list[str]:
    text = _NUM_COMMA_RE.sub("", text.lower())
    return [t for t in _TOKEN_RE.findall(text) if t not in _STOPWORDS]


class BM25:
    """Okapi BM25 built from scratch (k1/b defaults per Robertson et al.)."""

    def __init__(self, corpus_tokens: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_freqs = [Counter(toks) for toks in corpus_tokens]
        self.doc_lens = np.array([len(toks) for toks in corpus_tokens], dtype=float)
        self.avgdl = float(self.doc_lens.mean()) or 1.0 if len(corpus_tokens) else 1.0
        self.n_docs = len(corpus_tokens)
        df: Counter = Counter()
        for freqs in self.doc_freqs:
            df.update(freqs.keys())
        # BM25+-style floor at 0 via the 0.5 smoothing in standard idf
        self.idf = {
            term: math.log(1 + (self.n_docs - n + 0.5) / (n + 0.5))
            for term, n in df.items()
        }

    def score(self, query_tokens: list[str]) -> np.ndarray:
        scores = np.zeros(self.n_docs)
        for term in query_tokens:
            idf = self.idf.get(term)
            if idf is None:
                continue
            tf = np.array([freqs.get(term, 0) for freqs in self.doc_freqs], dtype=float)
            denom = tf + self.k1 * (1 - self.b + self.b * self.doc_lens / self.avgdl)
            scores += idf * (tf * (self.k1 + 1)) / np.where(denom == 0, 1, denom)
        return scores


@dataclass
class EvidenceHit:
    chunk: Chunk
    bm25_score: float
    vector_score: float
    hybrid_score: float


def _minmax(x: np.ndarray) -> np.ndarray:
    span = x.max() - x.min()
    if span == 0:
        return np.zeros_like(x)
    return (x - x.min()) / span


class HybridIndex:
    def __init__(self, chunks: list[Chunk], embedder, bm25_weight: float = 0.4):
        self.chunks = chunks
        self.bm25_weight = bm25_weight
        self.bm25 = BM25([tokenize(c.text) for c in chunks])
        self.embedder = embedder
        self.embeddings = embedder.embed([c.text for c in chunks])  # (n, d), L2-normalized

    def search(self, query: str, top_k: int = 3) -> list[EvidenceHit]:
        bm25_raw = self.bm25.score(tokenize(query))
        q_vec = self.embedder.embed([query])[0]
        vec_raw = self.embeddings @ q_vec  # cosine similarity (normalized vectors)

        hybrid = self.bm25_weight * _minmax(bm25_raw) + (1 - self.bm25_weight) * _minmax(vec_raw)
        order = np.argsort(hybrid)[::-1][:top_k]
        return [
            EvidenceHit(
                chunk=self.chunks[i],
                bm25_score=round(float(bm25_raw[i]), 4),
                vector_score=round(float(vec_raw[i]), 4),
                hybrid_score=round(float(hybrid[i]), 4),
            )
            for i in order
        ]
