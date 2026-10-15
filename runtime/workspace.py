"""Per-task workspace: isolated copy of a fixture + edit application + diff."""

import difflib
import os
import re
import shutil


class Workspace:
    def __init__(self, repo_root, task_id, fixture_rel):
        self.repo_root = os.path.abspath(repo_root)
        self.task_id = task_id
        self.path = os.path.join(self.repo_root, "workspaces", task_id)
        fixture = os.path.join(self.repo_root, fixture_rel)
        if not os.path.isdir(fixture):
            raise FileNotFoundError("fixture not found: %s" % fixture)
        if os.path.isdir(self.path):
            shutil.rmtree(self.path)
        shutil.copytree(fixture, self.path)
        self.original = self._snapshot()
        self.applied = []

    # ---------- io ----------
    def _snapshot(self):
        snap = {}
        for root, _, files in os.walk(self.path):
            for fn in files:
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, self.path).replace("\\", "/")
                with open(full, "r", encoding="utf-8", errors="replace") as f:
                    snap[rel] = f.read()
        return snap

    def read(self, rel):
        with open(os.path.join(self.path, rel), "r", encoding="utf-8", errors="replace") as f:
            return f.read()

    def write(self, rel, content):
        full = os.path.join(self.path, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)

    # ---------- edits ----------
    def apply_edits(self, edits):
        """Apply declarative edits. Only this function touches files."""
        changed = set()
        for e in edits or []:
            op = e.get("op")
            rel = e.get("file")
            if op == "set_define":
                text = self.read(rel)
                name = re.escape(e["name"])
                pat = re.compile(r"(#define\s+%s\s+)(\S+)" % name)
                if not pat.search(text):
                    raise ValueError("define %s not found in %s" % (e["name"], rel))
                new_text = pat.sub(lambda m: m.group(1) + str(e["value"]), text, count=1)
                self.write(rel, new_text)
                changed.add(rel)
            elif op == "write_file":
                self.write(rel, e.get("content", ""))
                changed.add(rel)
            else:
                raise ValueError("unsupported edit op: %s" % op)
            self.applied.append(e)
        return sorted(changed)

    # ---------- diff ----------
    def diff(self):
        chunks = []
        for rel in sorted(set(list(self.original) + list(self._snapshot()))):
            before = self.original.get(rel, "").splitlines(keepends=True)
            after = self._snapshot().get(rel, "").splitlines(keepends=True)
            if before == after:
                continue
            chunks.extend(
                difflib.unified_diff(
                    before,
                    after,
                    fromfile="a/" + rel,
                    tofile="b/" + rel,
                )
            )
        return "".join(chunks)

    def diff_path(self, out_path=None):
        """Write the diff. Defaults outside the workspace so it never pollutes the diff."""
        out = out_path or os.path.join(os.path.dirname(self.path), "%s.diff" % self.task_id)
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        with open(out, "w", encoding="utf-8", newline="\n") as f:
            f.write(self.diff())
        return out

    def changed_files(self):
        snap = self._snapshot()
        return sorted(r for r in set(list(snap) + list(self.original)) if snap.get(r) != self.original.get(r))
