#!/usr/bin/env python3
"""Static rule checks over a unified diff.

Rules (see prompts/coding_rules.md):
  CR-001  blocking call in interrupt/callback code
  CR-003  magic number (>=3 digits) outside #define
  CR-006  debug print in an interrupt/callback hunk

Usage:
  python tools/git_diff_check.py --diff samples/sample.diff
  python tools/git_diff_check.py                 # uses `git diff HEAD`

status=FAIL means the diff violates rules; a compliant diff returns PASS.
"""

import argparse
import re
import subprocess
import sys

import common

BLOCKING = re.compile(r"\b(delay_us|delay_ms|HAL_Delay|usleep|sleep|vTaskDelay)\s*\(")
MAGIC = re.compile(r"(?<![A-Za-z0-9_.])(\d{3,})(?![A-Za-z0-9_.])")
DEBUG_PRINT = re.compile(r"\b(printf|Serial\.print|std::cout)")
IRQ_CTX = re.compile(r"(IRQHandler|_Callback|interrupt|ISR)", re.I)


def get_diff(path, cwd):
    if path:
        return common.read_text(path), None
    try:
        p = subprocess.run(
            "git diff HEAD",
            cwd=cwd,
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return p.stdout or "", None
    except Exception as e:
        return "", str(e)


def check(diff_text):
    findings = []
    hunk_irq = False
    for raw in diff_text.splitlines():
        if raw.startswith("@@"):
            hunk_irq = bool(IRQ_CTX.search(raw))
            continue
        if raw.startswith(("diff --git", "+++", "---")):
            continue
        if not raw.startswith("+"):
            if IRQ_CTX.search(raw):
                hunk_irq = True
            continue
        line = raw[1:]
        if BLOCKING.search(line):
            findings.append({"rule": "CR-001", "severity": "high", "text": line.strip()})
        if "#define" not in line:
            m = MAGIC.search(line)
            if m:
                findings.append(
                    {
                        "rule": "CR-003",
                        "severity": "low",
                        "text": line.strip(),
                        "token": m.group(1),
                    }
                )
        if DEBUG_PRINT.search(line) and hunk_irq:
            findings.append({"rule": "CR-006", "severity": "medium", "text": line.strip()})
    return findings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--diff", default=None)
    ap.add_argument("--rules", default="prompts/coding_rules.md")
    ap.add_argument("--cwd", default=".")
    a = ap.parse_args()

    text, err = get_diff(a.diff, a.cwd)
    findings = check(text) if text else []
    result = {
        "tool": "git_diff_check",
        "diff": a.diff,
        "read_error": err,
        "findings": findings,
        "findings_count": len(findings),
        "rules_triggered": sorted({f["rule"] for f in findings}),
        "status": "PASS" if not findings else "FAIL",
        "notes": "status=FAIL means the diff violates rules; a compliant diff returns PASS",
    }
    common.emit(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
