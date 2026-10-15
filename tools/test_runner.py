#!/usr/bin/env python3
"""Run a test/analysis command and return a structured result.

If the command prints a JSON object as its last stdout line, that object is
merged into the result under "metrics", so numeric thresholds can be asserted.

Use the literal "{python}" in --cmd to refer to the interpreter running this
tool, which keeps the command portable across Windows/Linux and venvs.

Usage:
  python tools/test_runner.py --cmd "{python} examples/motor_control/scripts/estimate_axis.py data.csv"
"""

import argparse
import json
import sys

import common


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cmd", required=True)
    ap.add_argument("--cwd", default=".")
    ap.add_argument("--timeout", type=int, default=600)
    a = ap.parse_args()

    cmd = a.cmd.replace("{python}", '"%s"' % sys.executable)
    run = common.run_command(cmd, cwd=a.cwd, timeout=a.timeout)
    metrics, tail = {}, []
    for line in (run["stdout"] or "").splitlines():
        s = line.strip()
        tail.append(s)
        if s.startswith("{") and s.endswith("}"):
            try:
                metrics = json.loads(s)
            except ValueError:
                pass

    result = {
        "tool": "test_runner",
        "cmd": cmd,
        "exit_code": run["exit_code"],
        "duration_ms": run["duration_ms"],
        "timed_out": run["timed_out"],
        "metrics": metrics,
        "tail": tail[-15:],
        "stderr_tail": (run["stderr"] or "").splitlines()[-10:],
        "status": "PASS" if run["exit_code"] == 0 and not run["timed_out"] else "FAIL",
    }
    common.emit(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
