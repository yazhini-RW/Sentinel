"""Embeddings: sentence-transformers if available, else a TF-IDF hashing fallback.

Both return L2-normalized float32 matrices so downstream cosine similarity is a
plain dot product.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter

import numpy as np

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class SentenceTransformerEmbedder:
    name = "sentence-transformers/all-MiniLM-L6-v2"

    def __init__(self):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer("all-MiniLM-L6-v2")

    def embed(self, texts: list[str]) -> np.ndarray:
        return np.asarray(
            self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False),
            dtype=np.float32,
        )


class HashingTfidfEmbedder:
    """Zero-dependency fallback: hashed bag-of-words with sublinear TF and a
    fixed IDF-ish damping. Not semantic, but keeps the pipeline runnable."""

    def __init__(self, dim: int = 512):
        self.dim = dim
        self.name = f"hashing-tfidf-fallback-{dim}"  # dim in name keys the cache

    def _bucket(self, token: str) -> int:
        # Not a security use — md5 only assigns tokens to stable buckets.
        digest = hashlib.md5(token.encode(), usedforsecurity=False).hexdigest()
        return int(digest, 16) % self.dim

    def embed(self, texts: list[str]) -> np.ndarray:
        mat = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, text in enumerate(texts):
            counts = Counter(_TOKEN_RE.findall(text.lower()))
            for tok, c in counts.items():
                mat[i, self._bucket(tok)] += 1 + math.log(c)
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms[norms == 0] = 1
        return mat / norms


class CachedEmbedder:
    """SQLite-backed cache so unchanged chunks are never re-embedded.
    Keyed by sha256(model_name | text) — safe across model switches."""

    def __init__(self, inner, db_path):
        import sqlite3

        self.inner = inner
        self.name = inner.name
        self.db = sqlite3.connect(str(db_path))
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS embeddings (key TEXT PRIMARY KEY, dim INTEGER, vec BLOB)"
        )
        self.hits = 0
        self.misses = 0

    def _key(self, text: str) -> str:
        return hashlib.sha256(f"{self.name}|{text}".encode()).hexdigest()

    def embed(self, texts: list[str]) -> np.ndarray:
        import sqlite3

        try:
            return self._embed_cached(texts)
        except (sqlite3.Error, ValueError) as e:
            # Locked/corrupt db or a bad blob must never kill a run —
            # skip the cache for this call.
            import sys

            print(f"[sentinel] embedding cache bypassed ({e})", file=sys.stderr)
            self.misses += len(texts)
            return self.inner.embed(texts)

    def _embed_cached(self, texts: list[str]) -> np.ndarray:
        keys = [self._key(t) for t in texts]
        cached: dict[str, np.ndarray] = {}
        for key in set(keys):
            row = self.db.execute(
                "SELECT dim, vec FROM embeddings WHERE key = ?", (key,)
            ).fetchone()
            if row:
                vec = np.frombuffer(row[1], dtype=np.float32)
                if len(vec) == row[0]:  # a mismatched blob is treated as a miss
                    cached[key] = vec

        missing = [t for t, k in zip(texts, keys) if k not in cached]
        if missing:
            fresh = self.inner.embed(missing)
            for text, vec in zip(missing, fresh):
                key = self._key(text)
                cached[key] = np.asarray(vec, dtype=np.float32)
                self.db.execute(
                    "INSERT OR REPLACE INTO embeddings (key, dim, vec) VALUES (?, ?, ?)",
                    (key, len(vec), cached[key].tobytes()),
                )
            self.db.commit()
        self.hits += len(texts) - len(missing)
        self.misses += len(missing)
        return np.stack([cached[k] for k in keys])


_inner_singleton = None


def get_embedder(cache_path=None):
    """Prefer the real model; fall back with a warning if it isn't installed.
    Pass cache_path to wrap the embedder in a SQLite cache. The underlying
    model is a process-wide singleton so servers load it exactly once."""
    global _inner_singleton
    if _inner_singleton is None:
        try:
            _inner_singleton = SentenceTransformerEmbedder()
        except Exception as e:  # broken installs raise more than ImportError
            import sys

            print(
                f"[sentinel] WARNING: sentence-transformers unavailable ({type(e).__name__}); "
                "using hashing TF-IDF fallback embeddings (pip install -U sentence-transformers torch).",
                file=sys.stderr,
            )
            _inner_singleton = HashingTfidfEmbedder()
    embedder = _inner_singleton
    if cache_path is not None:
        try:
            return CachedEmbedder(embedder, cache_path)
        except Exception as e:  # unopenable cache db -> run uncached
            import sys

            print(f"[sentinel] embedding cache disabled ({e})", file=sys.stderr)
    return embedder
