#!/usr/bin/env python3
"""Agent metrics dashboard: aggregate `traces/*` into engineering KPIs.

  python tools/metrics.py                 # JSON on stdout + evals/metrics.md

Reported per task and in aggregate: first-pass rate (task finished without a
retry), iteration count, tool-call latency, gate/review outcome, tool layer,
and a token/cost estimate derived from the trace payload sizes.
"""

import argparse
import glob
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import common  # noqa: E402

CHARS_PER_TOKEN = 3.5


def _read_jsonl(path):
    events = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except ValueError:
                    continue
    return events


def collect(repo):
    tasks = []
    for summary_path in sorted(glob.glob(os.path.join(repo, "traces", "*", "summary.json"))):
        task_dir = os.path.dirname(summary_path)
        try:
            with open(summary_path, "r", encoding="utf-8") as f:
                summary = json.load(f)
        except ValueError:
            continue
        events = _read_jsonl(os.path.join(task_dir, "trace.jsonl"))
        durations = [e["duration_ms"] for e in events
                     if isinstance(e.get("duration_ms"), (int, float))]
        chars = sum(len(json.dumps(e, ensure_ascii=False)) for e in events)
        tasks.append({
            "task_id": os.path.basename(task_dir),
            "status": summary.get("status"),
            "iterations": summary.get("iterations") or 0,
            "tool_layer": summary.get("tool_layer") or "local",
            "hardware_source": summary.get("hardware_source"),
            "events": len(events),
            "knowledge_citations": len(summary.get("knowledge") or []),
            "review": (summary.get("review") or {}).get("decision"),
            "errors": len(summary.get("errors") or []),
            "tool_calls": len(durations),
            "tool_ms_total": round(sum(durations), 1),
            "tool_ms_mean": round(sum(durations) / len(durations), 1) if durations else 0.0,
            "trace_chars": chars,
            "tokens_est": int(chars / CHARS_PER_TOKEN),
        })
    return tasks


def summarize(tasks):
    done = [t for t in tasks if t["status"] == "DONE"]
    first_pass = [t for t in done if t["iterations"] <= 1]
    return {
        "tasks": len(tasks),
        "done": len(done),
        "first_pass_rate": round(len(first_pass) / len(done), 4) if done else 0.0,
        "iterations_mean": round(sum(t["iterations"] for t in tasks) / len(tasks), 2) if tasks else 0.0,
        "tool_calls": sum(t["tool_calls"] for t in tasks),
        "tool_ms_total": round(sum(t["tool_ms_total"] for t in tasks), 1),
        "tokens_est_total": sum(t["tokens_est"] for t in tasks),
        "tokens_est_mean": int(sum(t["tokens_est"] for t in tasks) / len(tasks)) if tasks else 0,
        "errors": sum(t["errors"] for t in tasks),
    }


def write_markdown(path, tasks, summary):
    lines = [
        "# Agent Metrics Dashboard",
        "",
        "- tasks: %d (DONE %d)" % (summary["tasks"], summary["done"]),
        "- first-pass rate: %.0f%%" % (100 * summary["first_pass_rate"]),
        "- iterations mean: %s" % summary["iterations_mean"],
        "- tool calls: %d (%.1f ms total)" % (summary["tool_calls"], summary["tool_ms_total"]),
        "- tokens (estimated): %d total, %d per task" % (summary["tokens_est_total"],
                                                         summary["tokens_est_mean"]),
        "",
        "| task | status | iterations | tool layer | tool calls | tool ms | tokens est | review |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for t in tasks:
        lines.append("| %s | %s | %d | %s | %d | %.1f | %d | %s |" % (
            t["task_id"], t["status"], t["iterations"], t["tool_layer"], t["tool_calls"],
            t["tool_ms_total"], t["tokens_est"], t["review"]))
    common.write_text(path, "\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-md", default=os.path.join("evals", "metrics.md"))
    ap.add_argument("--out-json", default=os.path.join("evals", "metrics.json"))
    a = ap.parse_args()

    tasks = collect(REPO)
    summary = summarize(tasks)
    common.write_text(os.path.join(REPO, a.out_json),
                      json.dumps({"summary": summary, "tasks": tasks},
                                 ensure_ascii=False, indent=2))
    write_markdown(os.path.join(REPO, a.out_md), tasks, summary)
    common.emit({
        "tool": "metrics",
        "tasks": tasks,
        "metrics": summary,
        "status": "PASS" if tasks else "EMPTY",
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
