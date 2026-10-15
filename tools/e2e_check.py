#!/usr/bin/env python3
"""End-to-end check of the orchestrator's two documented exits.

  python tools/e2e_check.py --mode gate     # no hardware record -> exit 3 (human gate)
  python tools/e2e_check.py --mode full     # with a hardware record -> exit 0 (DONE)
"""

import argparse
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import common  # noqa: E402

MODES = {
    "gate": ("runtime.orchestrator", ["--task", "tasks/adc_sampling_fix.json"], 3),
    "full": ("runtime.orchestrator", ["--task", "tasks/adc_sampling_fix.json",
                                      "--hardware-report",
                                      "fixtures/hardware_report.fixture.json"], 0),
    "mcp": ("runtime.orchestrator", ["--task", "tasks/adc_sampling_fix.json",
                                     "--hardware-report",
                                     "fixtures/hardware_report.fixture.json",
                                     "--tool-layer", "mcp", "--memory"], 0),
    # True multi-agent: isolated context + tool whitelist + task per role.
    "multi": ("runtime.multi_agent", ["--task", "tasks/adc_sampling_fix.json"], 0),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True, choices=sorted(MODES))
    ap.add_argument("--timeout", type=int, default=300)
    a = ap.parse_args()

    module, args, expected = MODES[a.mode]
    proc = subprocess.run(
        [sys.executable, "-m", module] + args,
        cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=dict(common.ENV), timeout=a.timeout,
    )
    stdout = proc.stdout or ""
    metrics = {
        "mode": a.mode,
        "exit_code": proc.returncode,
        "expected_exit": expected,
        "states": stdout.count('"state"'),
    }
    common.emit({
        "tool": "e2e_check",
        "metrics": metrics,
        "status": "PASS" if proc.returncode == expected else "FAIL",
        "stderr_tail": (proc.stderr or "").splitlines()[-4:],
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
