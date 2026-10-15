"""Hashed TF-IDF vectors + cosine similarity, plus reciprocal rank fusion.

Zero third-party dependencies, same constraint as the lexical index: the dense
layer has to run offline and in CI exactly like `rag/index.py` does. Vectors are
hashed into a fixed number of buckets, weighted by IDF, squashed and
L2-normalised, so a query is one sparse dot product per document.
"""

import json
import math
import os

import re

from rag.index import tokenize

VERSION = 2  # bump when dense_tokens or the weighting changes
DIM = 2048
RRF_K = 60


def _bucket(token, dim=DIM):
    h = 2166136261
    for ch in token:
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return h % dim


def _fields(chunk):
    """Same field boosting the lexical index applies."""
    path = chunk.get("path", "")
    basename = path.replace("\\", "/").split("/")[-1]
    return " ".join(
        [chunk.get("text", ""), chunk.get("title", ""), path, basename,
         basename.rsplit(".", 1)[0]]
    )


ASCII_TOKEN = re.compile(r"[A-Za-z0-9_./+-]{2,}")


def dense_tokens(text):
    """ASCII tokens + CJK bigrams only.

    The lexical index also keeps CJK unigrams (they help short queries), but in
    a hashed space unigrams collide far more often than they discriminate, so
    the dense layer drops them.
    """
    tokens = [m.group(0).lower() for m in ASCII_TOKEN.finditer(text)]
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
        if len(run) == 1:
            tokens.append(run)
    return tokens


def rrf(rankings, k=RRF_K):
    """Reciprocal rank fusion: merge several ranked key lists into one order."""
    fused = {}
    for ranking in rankings:
        for rank, key in enumerate(ranking, start=1):
            fused[key] = fused.get(key, 0.0) + 1.0 / (k + rank)
    return sorted(fused.items(), key=lambda kv: (-kv[1], str(kv[0])))


class VectorIndex:
    def __init__(self, dim=DIM):
        self.dim = dim
        self.version = VERSION
        self.docs = []
        self.vectors = []
        self.idf = {}

    # ---------- build ----------
    def build(self, chunks):
        self.docs = list(chunks)
        df = {}
        tokenised = []
        for chunk in self.docs:
            tokens = dense_tokens(_fields(chunk))
            tokenised.append(tokens)
            for token in set(tokens):
                df[token] = df.get(token, 0) + 1
        n = max(1, len(self.docs))
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self.vectors = [self._vector(tokens) for tokens in tokenised]
        return len(self.docs)

    def _vector(self, tokens):
        buckets = {}
        for token in tokens:
            bucket = _bucket(token, self.dim)
            buckets[bucket] = buckets.get(bucket, 0.0) + self.idf.get(token, 1.0)
        squashed = {b: x / (1.0 + x) for b, x in buckets.items()}
        norm = math.sqrt(sum(v * v for v in squashed.values())) or 1.0
        return {b: v / norm for b, v in squashed.items()}

    # ---------- search ----------
    def search(self, query, k=3):
        if not self.vectors:
            return []
        q = self._vector(dense_tokens(query))
        scored = []
        for i, vec in enumerate(self.vectors):
            dot = sum(w * vec.get(b, 0.0) for b, w in q.items())
            if dot:
                scored.append((i, dot))
        scored.sort(key=lambda kv: (-kv[1], kv[0]))
        return [(self.docs[i], round(score, 6)) for i, score in scored[:k]]

    # ---------- persistence ----------
    def to_dict(self):
        return {
            "version": VERSION,
            "dim": self.dim,
            "idf": self.idf,
            "docs": self.docs,
            "vectors": [{str(b): w for b, w in vec.items()} for vec in self.vectors],
        }

    @classmethod
    def from_dict(cls, data):
        index = cls(dim=data.get("dim", DIM))
        index.version = data.get("version", 0)
        index.idf = data.get("idf", {})
        index.docs = data.get("docs", [])
        index.vectors = [{int(b): w for b, w in vec.items()} for vec in data.get("vectors", [])]
        return index

    def save(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False)
        return path

    @classmethod
    def load_or_build(cls, path, chunks):
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    index = cls.from_dict(json.load(f))
                if index.version == VERSION and len(index.docs) == len(chunks):
                    return index
            except (ValueError, KeyError):
                pass
        index = cls()
        index.build(chunks)
        index.save(path)
        return index
