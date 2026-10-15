#!/usr/bin/env python3
"""Project-memory check: can past trace experience be retrieved by question?

  python tools/memory_eval.py            # JSON summary for the eval harness

Each probe names the task whose history it should surface, so a hit means the
memory really points back at the run that produced the lesson.
"""

import argparse
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import common  # noqa: E402

from runtime.memory import ProjectMemory  # noqa: E402

PROBES = [
    {"id": "mem-adc-window", "query": "ADC 采样窗口 振铃 修复", "expect_task": "adc-001"},
    {"id": "mem-human-gate", "query": "人工闸门 实机验证 硬件记录", "expect_task": "adc-001"},
    {"id": "mem-tool-layer", "query": "MCP 工具层 规划 检索命中", "expect_task": "adc-001"},
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=3)
    a = ap.parse_args()

    memory = ProjectMemory(REPO)
    built = memory.build()
    if not built["tasks"]:
        # Cold checkout: `traces/` is git-ignored, so produce the evidence the
        # check needs instead of silently passing on an empty memory.
        subprocess.run(
            [sys.executable, "-m", "runtime.orchestrator",
             "--task", "tasks/adc_sampling_fix.json",
             "--hardware-report", "fixtures/hardware_report.fixture.json"],
            cwd=REPO, check=False,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env=dict(common.ENV),
        )
        built = memory.build()
    hits_at_k, rr, details = 0, 0.0, []
    for probe in PROBES:
        hits = memory.search(probe["query"], k=a.k)
        rank = 0
        for i, hit in enumerate(hits, start=1):
            if hit["task_id"] == probe["expect_task"]:
                rank = i
                break
        hits_at_k += 1 if rank else 0
        rr += (1.0 / rank) if rank else 0.0
        details.append({"id": probe["id"], "expect_task": probe["expect_task"], "rank": rank,
                        "top1": hits[0]["task_id"] if hits else None})
    total = max(1, len(PROBES))
    metrics = {
        "tasks": built["tasks"],
        "probes": len(PROBES),
        "recall_at_k": round(hits_at_k / total, 4),
        "mrr": round(rr / total, 4),
        "k": a.k,
    }
    common.emit({
        "tool": "memory_eval",
        "metrics": metrics,
        "probes": details,
        "status": "PASS" if built["tasks"] and hits_at_k == len(PROBES) else "FAIL",
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
