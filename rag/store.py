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
            if os.path.exists(self.index_path):
                with open(self.index_path, "r", encoding="utf-8") as f:
                    self.index = InvertedIndex.from_dict(json.load(f))
            else:
                # Cold checkout (the index is generated, so it is git-ignored):
                # build in-process instead of failing the whole run.
                try:
                    self.build()
                except OSError:
                    index = InvertedIndex()
                    for rel in chunker.collect_sources(self.repo, None):
                        for chunk in chunker.chunk_file(self.repo, rel):
                            index.add(chunk)
                    index.finalize()
                    self.index = index
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

    # ---------- hybrid retrieval ----------
    def vectors(self):
        from rag.vector import VectorIndex

        index = self.load()
        return VectorIndex.load_or_build(
            os.path.join(self.repo, "rag", "index", "kb_vectors.json"), index.docs
        )

    def _hit(self, chunk, score, query):
        return {
            "path": chunk["path"],
            "lines": [chunk["start_line"], chunk["end_line"]],
            "citation": "%s#L%d-L%d" % (chunk["path"], chunk["start_line"], chunk["end_line"]),
            "title": chunk.get("title", ""),
            "score": score,
            "snippet": _snippet(chunk["text"], query),
        }

    def search_hybrid(self, query, k=3):
        """BM25 + hashed-vector rankings fused with reciprocal rank fusion.

        Adopted after the comparison in `evals/rag_cases.yaml` showed the dense
        layer lifting MRR (0.82 -> 0.93) at equal recall@3; the lexical path stays
        available for the baseline comparison.
        """
        from rag.vector import rrf

        index = self.load()
        wide = max(k, 10)
        lexical = index.search(query, k=wide)
        dense = self.vectors().search(query, k=wide)
        fused = rrf([[id(doc) for doc, _ in lexical], [id(doc) for doc, _ in dense]])
        lookup = {id(doc): doc for doc, _ in lexical}
        lookup.update({id(doc): doc for doc, _ in dense})
        return [self._hit(lookup[key], round(score, 6), query) for key, score in fused[:k]]

