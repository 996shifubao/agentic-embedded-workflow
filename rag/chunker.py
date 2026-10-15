"""Heading-aware chunking for the knowledge base.

The corpus is the repository itself (docs, role contracts, prompts, eval rules,
example READMEs). Chunks keep their heading path so a retrieved snippet can be
cited as `path#Lstart-Lend` and traced back to the source file.
"""

import os
import re

TEXT_EXTS = {".md", ".yaml", ".yml", ".json", ".txt", ".log", ".c", ".h", ".py"}
MAX_CHARS = 900
MIN_CHARS = 120

HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


def _chunk_markdown(rel_path, text):
    """Split by heading; long sections are further split on blank lines."""
    chunks, heading_stack = [], []
    buf, start_line = [], 1

    def flush(end_line):
        nonlocal buf, start_line
        body = "\n".join(buf).strip()
        buf = []
        if len(body) < 20:
            return
        title = " > ".join(heading_stack) if heading_stack else rel_path
        for piece, piece_start in _split_long(body, start_line):
            if len(piece) < 20:
                continue
            chunks.append(
                {
                    "path": rel_path.replace("\\", "/"),
                    "start_line": piece_start,
                    "end_line": end_line,
                    "title": title,
                    "text": piece,
                }
            )

    for lineno, line in enumerate(text.splitlines(), start=1):
        m = HEADING.match(line)
        if m:
            flush(lineno - 1)
            level = len(m.group(1))
            del heading_stack[level - 1 :]
            while len(heading_stack) < level - 1:
                heading_stack.append("")
            heading_stack.append(m.group(2).strip())
            start_line = lineno
            buf = [line]
            continue
        buf.append(line)
    flush(len(text.splitlines()))
    return chunks


def _split_long(body, start_line):
    """Split an over-long section on paragraph boundaries."""
    if len(body) <= MAX_CHARS:
        return [(body, start_line)]
    pieces, current, current_start, offset = [], [], start_line, start_line
    for para in body.split("\n\n"):
        if current and sum(len(x) + 2 for x in current) + len(para) > MAX_CHARS:
            pieces.append(("\n\n".join(current), current_start))
            current_start = offset
            current = []
        current.append(para)
        offset += len(para.splitlines()) + 1
    if current:
        pieces.append(("\n\n".join(current), current_start))
    return pieces


def chunk_file(repo_root, rel_path):
    ext = os.path.splitext(rel_path)[1].lower()
    if ext not in TEXT_EXTS:
        return []
    abs_path = os.path.join(repo_root, rel_path)
    if not os.path.isfile(abs_path) or os.path.getsize(abs_path) > 2_000_000:
        return []
    with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    if not text.strip():
        return []
    if ext == ".md":
        return _chunk_markdown(rel_path, text)
    lines = text.splitlines()
    step = max(1, MAX_CHARS // 80)
    chunks = []
    for i in range(0, len(lines), step):
        body = "\n".join(lines[i : i + step]).strip()
        if len(body) < 20:
            continue
        chunks.append(
            {
                "path": rel_path.replace("\\", "/"),
                "start_line": i + 1,
                "end_line": min(i + step, len(lines)),
                "title": rel_path.replace("\\", "/"),
                "text": body[:MAX_CHARS],
            }
        )
    return chunks


DEFAULT_SOURCES = [
    "README.md",
    "AGENTS.md",
    "docs",
    "prompts",
    "agents",
    "evals/log_rules",
    "evals/test_cases.yaml",
    "evals/expected_results.yaml",
    "examples",
    "schemas",
    "configs",
]


def collect_sources(repo_root, sources=None):
    """Return the list of repo-relative files that make up the corpus."""
    found = []
    for src in sources or DEFAULT_SOURCES:
        abs_src = os.path.join(repo_root, src)
        if os.path.isfile(abs_src):
            found.append(src)
        elif os.path.isdir(abs_src):
            for root, dirs, files in os.walk(abs_src):
                dirs[:] = [d for d in dirs if d not in {"__pycache__", ".git"}]
                for name in files:
                    ext = os.path.splitext(name)[1].lower()
                    if ext in TEXT_EXTS:
                        found.append(os.path.relpath(os.path.join(root, name), repo_root))
    return sorted(set(found))

