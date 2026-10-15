"""Shared helpers for the harness tools."""

import json
import os
import subprocess
import time

ENV = dict(os.environ, PYTHONIOENCODING="utf-8")


def read_text(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def write_text(path, text):
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def load_structured(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".yaml", ".yml"):
        import mini_yaml

        return mini_yaml.load(path)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def emit(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def run_command(cmd, cwd=None, timeout=900):
    """Run a shell command, returning a structured result. Never raises on failure."""
    t0 = time.time()
    try:
        p = subprocess.run(
            cmd,
            cwd=cwd,
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=ENV,
            timeout=timeout,
        )
        out, err, code, timed_out = p.stdout or "", p.stderr or "", p.returncode, False
    except subprocess.TimeoutExpired as e:
        out, err = e.stdout or "", e.stderr or ""
        if isinstance(out, bytes):
            out = out.decode("utf-8", "replace")
        if isinstance(err, bytes):
            err = err.decode("utf-8", "replace")
        code, timed_out = None, True
    return {
        "exit_code": code,
        "stdout": out,
        "stderr": err,
        "timed_out": timed_out,
        "duration_ms": int((time.time() - t0) * 1000),
    }


def resolve(obj, path):
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return cur


def compare(op, actual, expected):
    if op == "eq":
        return actual == expected
    if op == "ne":
        return actual != expected
    if op == "lt":
        return actual is not None and actual < expected
    if op == "le":
        return actual is not None and actual <= expected
    if op == "gt":
        return actual is not None and actual > expected
    if op == "ge":
        return actual is not None and actual >= expected
    if op == "in":
        return actual in (expected or [])
    if op in ("contains", "not_contains", "contains_all"):
        try:
            if op == "contains":
                return expected in actual
            if op == "not_contains":
                return expected not in actual
            return all(x in actual for x in (expected or []))
        except TypeError:
            return op == "not_contains"
    if op == "len_ge":
        try:
            return len(actual) >= expected
        except TypeError:
            return False
    raise ValueError("unknown op: %s" % op)
