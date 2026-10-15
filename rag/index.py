"""Inverted index + BM25 scoring over CJK char bigrams and ASCII tokens.

No third-party dependencies: the same property as the rest of the harness, so
CI and offline demos behave identically.
"""

import math
import re

ASCII_TOKEN = re.compile(r"[A-Za-z0-9_./+-]{2,}")
CJK = re.compile(r"[\u4e00-\u9fff]")

K1 = 1.2
B = 0.75


def tokenize(text):
    """ASCII words (lowercased) plus CJK unigrams and bigrams."""
    tokens = [m.group(0).lower() for m in ASCII_TOKEN.finditer(text)]
    cjk_runs = re.findall(r"[\u4e00-\u9fff]+", text)
    for run in cjk_runs:
        tokens.extend(run)
        tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
    return tokens


class InvertedIndex:
    def __init__(self):
        self.docs = []          # list of chunk dicts
        self.postings = {}      # token -> {doc_index: tf}
        self.lengths = []       # doc token counts
        self.avg_len = 0.0

    # ---------- build ----------
    def add(self, chunk):
        idx = len(self.docs)
        self.docs.append(chunk)
        # field boosting: body + heading path + file path (basename weighted twice)
        path = chunk.get("path", "")
        basename = path.replace("\\", "/").split("/")[-1]
        indexed = " ".join(
            [
                chunk["text"],
                chunk.get("title", ""),
                path,
                basename,
                basename.rsplit(".", 1)[0],
            ]
        )
        tokens = tokenize(indexed)
        self.lengths.append(len(tokens))
        for token in tokens:
            self.postings.setdefault(token, {})
            self.postings[token][idx] = self.postings[token].get(idx, 0) + 1

    def finalize(self):
        self.avg_len = (sum(self.lengths) / len(self.lengths)) if self.lengths else 0.0

    # ---------- search ----------
    def search(self, query, k=3):
        tokens = tokenize(query)
        if not tokens:
            return []
        scores = {}
        n_docs = max(1, len(self.docs))
        for token in tokens:
            posting = self.postings.get(token)
            if not posting:
                continue
            df = len(posting)
            idf = math.log(1 + (n_docs - df + 0.5) / (df + 0.5))
            for doc_id, tf in posting.items():
                dl = self.lengths[doc_id] or 1
                denom = tf + K1 * (1 - B + B * dl / (self.avg_len or 1))
                scores[doc_id] = scores.get(doc_id, 0.0) + idf * (tf * (K1 + 1)) / denom
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
        return [(self.docs[i], round(score, 4)) for i, score in ranked[:k]]

    # ---------- persistence ----------
    def to_dict(self):
        return {
            "version": 1,
            "k1": K1,
            "b": B,
            "docs": self.docs,
            "lengths": self.lengths,
            "avg_len": round(self.avg_len, 4),
            "postings": {t: {str(i): c for i, c in p.items()} for t, p in self.postings.items()},
        }

    @classmethod
    def from_dict(cls, data):
        index = cls()
        index.docs = data.get("docs", [])
        index.lengths = data.get("lengths", [])
        index.avg_len = data.get("avg_len", 0.0)
        index.postings = {
            t: {int(i): c for i, c in p.items()} for t, p in (data.get("postings") or {}).items()
        }
        return index

