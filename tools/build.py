#!/usr/bin/env python3
"""Wrap a firmware build and return a structured result.

Usage:
  python tools/build.py --config configs/keil.example.json

If no command is configured and the toolchain is not on PATH, status is
SKIPPED (never silently PASS).
"""

import argparse
import os
import re
import shutil
import sys

import common

DEFAULT_ERROR = r"(?i)\b(error|fatal)\b"
DEFAULT_WARN = r"(?i)\bwarning\b"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--timeout", type=int, default=1200)
    a = ap.parse_args()

    cfg = common.load_structured(a.config) or {}
    command = (cfg.get("command") or "").strip()
    toolchain = cfg.get("toolchain")
    cwd = cfg.get("cwd") or "."
    err_re = cfg.get("error_pattern") or DEFAULT_ERROR
    warn_re = cfg.get("warning_pattern") or DEFAULT_WARN

    result = {
        "tool": "build",
        "name": cfg.get("name"),
        "toolchain": toolchain,
        "command": command,
        "cwd": os.path.abspath(cwd),
        "exit_code": None,
        "errors": 0,
        "warnings": 0,
        "duration_ms": 0,
        "timed_out": False,
        "evidence": [],
        "status": "SKIPPED",
    }

    if not command:
        if toolchain and shutil.which(toolchain):
            command = "%s --build" % toolchain
            result["command"] = command
            result["notes"] = "toolchain detected; set config.command for real invocation"
        else:
            result["reason"] = "no command configured and toolchain not found on PATH"
            common.emit(result)
            return 0

    run = common.run_command(command, cwd=cwd, timeout=a.timeout)
    text = (run["stdout"] or "") + "\n" + (run["stderr"] or "")
    result.update(
        {
            "exit_code": run["exit_code"],
            "duration_ms": run["duration_ms"],
            "timed_out": run["timed_out"],
            "errors": len(re.findall(err_re, text)),
            "warnings": len(re.findall(warn_re, text)),
        }
    )
    result["evidence"] = [
        ln
        for ln in text.splitlines()
        if re.search(err_re, ln) or re.search(warn_re, ln)
    ][:20]

    ok = run["exit_code"] == 0 and not run["timed_out"] and result["errors"] == 0
    result["status"] = "PASS" if ok else "FAIL"
    common.emit(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
