#!/usr/bin/env python3
"""Query the knowledge base, optionally scoring a case file.

Single query:
  python tools/kb_query.py --query "ADC 采样窗口 振铃" --k 3

Retrieval quality (used by the eval harness):
  python tools/kb_query.py --cases evals/rag_cases.yaml --k 3
  -> metrics.recall_at_k / metrics.mrr / per-case rank
"""

import argparse
import os
import sys

import common

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from rag.store import KnowledgeBase  # noqa: E402


def _rank(case, hits):
    needle = (case.get("expect_path_contains") or "").lower()
    for rank, hit in enumerate(hits, start=1):
        haystack = (hit["path"] + " " + hit.get("title", "")).lower()
        if needle and needle in haystack:
            return rank
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query")
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--cases")
    ap.add_argument("--index", default=None)
    a = ap.parse_args()

    kb = KnowledgeBase(REPO, index_path=a.index)
    stats = kb.stats()

    if a.cases:
        cases = (common.load_structured(a.cases) or {}).get("cases") or []
        details, hits_at_k, rr = [], 0, 0.0
        for case in cases:
            hits = kb.search(case["query"], k=a.k)
            rank = _rank(case, hits)
            hits_at_k += 1 if rank else 0
            rr += (1.0 / rank) if rank else 0.0
            details.append(
                {
                    "id": case.get("id"),
                    "query": case["query"],
                    "expect_path_contains": case.get("expect_path_contains"),
                    "rank": rank,
                    "ok": bool(rank),
                    "top1": hits[0]["citation"] if hits else None,
                }
            )
        total = max(1, len(cases))
        result = {
            "tool": "kb_query",
            "cases": details,
            "total": len(cases),
            "hits_at_k": hits_at_k,
            "k": a.k,
            "metrics": {
                "recall_at_k": round(hits_at_k / total, 4),
                "mrr": round(rr / total, 4),
                "chunks": stats["chunks"],
            },
            "status": "PASS" if cases and hits_at_k == len(cases) else "FAIL",
        }
        common.emit(result)
        return 0

    hits = kb.search(a.query or "", k=a.k)
    common.emit(
        {
            "tool": "kb_query",
            "query": a.query,
            "k": a.k,
            "hits": hits,
            "top1": hits[0]["citation"] if hits else None,
            "status": "PASS" if hits else "EMPTY",
            "metrics": stats,
        }
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

