#!/usr/bin/env python3
"""Build (or rebuild) the knowledge-base index.

Usage:
  python tools/kb_build.py [--sources docs prompts examples]

Output (JSON): {"tool": "kb_build", "status": "PASS", "files": N, "chunks": M}
"""

import argparse
import os
import sys

import common

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from rag.store import KnowledgeBase  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", nargs="*", default=None, help="repo-relative files/dirs")
    ap.add_argument("--index", default=None)
    a = ap.parse_args()

    kb = KnowledgeBase(REPO, index_path=a.index)
    stats = kb.build(a.sources)
    stats["tool"] = "kb_build"
    stats["status"] = "PASS" if stats["chunks"] else "FAIL"
    stats["index_path"] = os.path.relpath(stats["index_path"], REPO).replace("\\", "/")
    stats["metrics"] = kb.stats()
    common.emit(stats)
    return 0 if stats["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

