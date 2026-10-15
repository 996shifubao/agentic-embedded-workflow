"""Knowledge base: build/load the index and answer queries with citations."""

import json
import os
import re

from rag import chunker
from rag.index import InvertedIndex

DEFAULT_INDEX = os.path.join("rag", "index", "kb_index.json")
SNIPPET_CHARS = 220


def _snippet(text, query):
    """Return a window around the first strong query match, else the head."""
    tokens = [t for t in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_+/#.-]{3,}", query)]
    flat = re.sub(r"\s+", " ", text).strip()
    for token in tokens:
        pos = flat.lower().find(token.lower())
        if pos >= 0:
            start = max(0, pos - 60)
            return flat[start : start + SNIPPET_CHARS]
    return flat[:SNIPPET_CHARS]


class KnowledgeBase:
    def __init__(self, repo_root, index_path=None):
        self.repo = os.path.abspath(repo_root)
        self.index_path = os.path.join(self.repo, index_path or DEFAULT_INDEX)
        self.index = None

    # ---------- build / load ----------
    def build(self, sources=None):
        files = chunker.collect_sources(self.repo, sources)
        index = InvertedIndex()
        for rel in files:
            for chunk in chunker.chunk_file(self.repo, rel):
                index.add(chunk)
        index.finalize()
        self.index = index
        os.makedirs(os.path.dirname(self.index_path), exist_ok=True)
        with open(self.index_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(index.to_dict(), f, ensure_ascii=False)
        return {"files": len(files), "chunks": len(index.docs), "index_path": self.index_path}

    def load(self):
        if self.index is None:
            if not os.path.exists(self.index_path):
                raise FileNotFoundError(
                    "knowledge index missing: run `python tools/kb_build.py` first"
                )
            with open(self.index_path, "r", encoding="utf-8") as f:
                self.index = InvertedIndex.from_dict(json.load(f))
        return self.index

    # ---------- query ----------
    def search(self, query, k=3):
        index = self.load()
        hits = []
        for chunk, score in index.search(query, k=k):
            hits.append(
                {
                    "path": chunk["path"],
                    "lines": [chunk["start_line"], chunk["end_line"]],
                    "citation": "%s#L%d-L%d" % (chunk["path"], chunk["start_line"], chunk["end_line"]),
                    "title": chunk.get("title", ""),
                    "score": score,
                    "snippet": _snippet(chunk["text"], query),
                }
            )
        return hits

    def stats(self):
        index = self.load()
        return {"chunks": len(index.docs), "terms": len(index.postings), "avg_len": round(index.avg_len, 1)}

