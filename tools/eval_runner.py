#!/usr/bin/env python3
"""Evaluation orchestrator.

Runs every case in evals/test_cases.yaml:
  automated: true   -> invoke tools/<runner>.py, compare its JSON output to `expect`
  automated: false  -> read evals/runs/<id>.json (human-filled); missing = PENDING

Usage:
  python tools/eval_runner.py --cases evals/test_cases.yaml --expected evals/expected_results.yaml

Exit code is 0 only when no case is FAIL or ERROR (PENDING is allowed).
"""

import argparse
import datetime
import json
import os
import subprocess
import sys

import common

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNNERS = {
    "build": "build.py",
    "log": "log_parser.py",
    "test": "test_runner.py",
    "static": "git_diff_check.py",
    "rag": "kb_query.py",
    "mcp": "mcp_call.py",
    "vector": "vector_eval.py",
    "memory": "memory_eval.py",
    "security": "policy_check.py",
    "budget": "budget_check.py",
    "e2e": "e2e_check.py",
    "scenario": "field_scenario.py",
}


def resolve_expectations(expect_list, thresholds):
    resolved = []
    for e in expect_list or []:
        val = e.get("value")
        if isinstance(val, str) and val.startswith("${") and val.endswith("}"):
            val = (thresholds or {}).get(val[2:-1])
        resolved.append({"path": e["path"], "op": e.get("op", "eq"), "value": val})
    return resolved


def run_case(case, thresholds, runs_dir):
    cid = case["id"]
    entry = {
        "id": cid,
        "layer": case.get("layer"),
        "name": case.get("name", ""),
        "automated": bool(case.get("automated", True)),
    }
    expects = resolve_expectations(case.get("expect"), thresholds)
    entry["expect"] = expects

    if not entry["automated"] or case.get("runner") == "manual":
        rec = os.path.join(runs_dir, "%s.json" % cid)
        if not os.path.exists(rec):
            entry.update({"status": "PENDING", "detail": "awaiting human record: %s" % rec})
            return entry
        data = common.load_structured(rec)
        checks = []
        for e in expects:
            actual = common.resolve(data, e["path"])
            checks.append(
                {
                    "path": e["path"],
                    "op": e["op"],
                    "expected": e["value"],
                    "actual": actual,
                    "ok": common.compare(e["op"], actual, e["value"]),
                }
            )
        entry.update(
            {
                "status": "PASS" if checks and all(c["ok"] for c in checks) else "FAIL",
                "checks": checks,
                "record": rec,
            }
        )
        return entry

    runner = RUNNERS.get(case.get("runner"))
    if runner is None:
        entry.update({"status": "ERROR", "detail": "unknown runner: %s" % case.get("runner")})
        return entry

    cmd = [sys.executable, os.path.join(REPO, "tools", runner)] + list(case.get("args") or [])
    p = subprocess.run(
        cmd,
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=common.ENV,
    )
    try:
        out = json.loads(p.stdout)
    except ValueError:
        entry.update(
            {
                "status": "ERROR",
                "detail": "runner produced no JSON",
                "raw_stdout_tail": (p.stdout or "").splitlines()[-10:],
                "raw_stderr_tail": (p.stderr or "").splitlines()[-10:],
            }
        )
        return entry

    checks = []
    for e in expects:
        actual = common.resolve(out, e["path"])
        checks.append(
            {
                "path": e["path"],
                "op": e["op"],
                "expected": e["value"],
                "actual": actual,
                "ok": common.compare(e["op"], actual, e["value"]),
            }
        )
    entry.update(
        {
            "status": "PASS" if checks and all(c["ok"] for c in checks) else "FAIL",
            "checks": checks,
            "observed": out.get("status"),
            "metrics": out.get("metrics"),
            "failed_assertions": [a for a in (out.get("assertions") or []) if not a.get("ok")],
            "rules_triggered": out.get("rules_triggered"),
        }
    )
    return entry


def summarize(results):
    summary = {k: 0 for k in ("PASS", "FAIL", "PENDING", "ERROR")}
    for r in results:
        summary[r["status"]] = summary.get(r["status"], 0) + 1
    summary["total"] = len(results)
    by_layer = {}
    for r in results:
        layer = r.get("layer") or "unknown"
        bucket = by_layer.setdefault(layer, {"total": 0, "PASS": 0, "FAIL": 0,
                                             "PENDING": 0, "ERROR": 0})
        bucket["total"] += 1
        bucket[r["status"]] = bucket.get(r["status"], 0) + 1
    summary["by_layer"] = by_layer
    return summary


def failure_clusters(results):
    """Group failures by layer + the assertion that broke, so patterns surface."""
    clusters = {}
    for r in results:
        if r["status"] not in ("FAIL", "ERROR"):
            continue
        paths = [c["path"] for c in (r.get("checks") or []) if not c.get("ok")]
        for path in paths or [r.get("detail") or "unknown"]:
            clusters.setdefault("%s :: %s" % (r.get("layer"), path), []).append(r["id"])
    return clusters


def write_markdown(path, report):
    lines = [
        "# Evaluation Report",
        "",
        "- generated: %s" % report["generated_at"],
        "- summary: %s" % json.dumps(report["summary"], ensure_ascii=False),
        "",
        "| case | layer | status | detail |",
        "|---|---|---|---|",
    ]
    for r in report["cases"]:
        detail = r.get("detail", "")
        if r.get("failed_assertions"):
            ids = [x.get("id") or "?" for x in r["failed_assertions"]]
            detail = "failed assertions: " + ", ".join(ids)
        elif r.get("rules_triggered"):
            detail = "rules triggered: " + ", ".join(r["rules_triggered"])
        elif r.get("metrics"):
            detail = json.dumps(r["metrics"], ensure_ascii=False)
        elif r.get("observed"):
            detail = "observed: %s" % r["observed"]
        lines.append("| %s | %s | %s | %s |" % (r["id"], r.get("layer"), r["status"], detail))
    lines += ["", "## Coverage by layer", "", "| layer | total | PASS | PENDING | FAIL | ERROR |",
              "|---|---|---|---|---|---|"]
    for layer, counts in sorted((report.get("coverage") or {}).items()):
        lines.append("| %s | %d | %d | %d | %d | %d |" % (
            layer, counts["total"], counts.get("PASS", 0), counts.get("PENDING", 0),
            counts.get("FAIL", 0), counts.get("ERROR", 0)))
    lines += ["", "## Failure clusters", ""]
    lines += ["- `%s` -> %s" % (k, ", ".join(v))
              for k, v in sorted((report.get("failure_clusters") or {}).items())] or ["- none"]
    common.write_text(path, "\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="evals/test_cases.yaml")
    ap.add_argument("--expected", default="evals/expected_results.yaml")
    ap.add_argument("--runs-dir", default="evals/runs")
    ap.add_argument("--out-json", default="evals/report.json")
    ap.add_argument("--out-md", default="evals/report.md")
    a = ap.parse_args()

    cases = (common.load_structured(a.cases) or {}).get("cases") or []
    thresholds = (common.load_structured(a.expected) or {}).get("thresholds") or {}
    runs_dir = os.path.join(REPO, a.runs_dir)

    results = [run_case(c, thresholds, runs_dir) for c in cases]
    report = {
        "generated_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "summary": summarize(results),
        "thresholds": thresholds,
        "cases": results,
        "coverage": summarize(results)["by_layer"],
        "failure_clusters": failure_clusters(results),
    }
    common.write_text(os.path.join(REPO, a.out_json), json.dumps(report, ensure_ascii=False, indent=2))
    write_markdown(os.path.join(REPO, a.out_md), report)

    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0 if report["summary"]["FAIL"] == 0 and report["summary"]["ERROR"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
