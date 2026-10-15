"""Human Gate: the one place where the agent loop must stop.

An agent cannot drive a scope or strap a board. So the workflow pauses in
WAITING_FOR_HUMAN_HARDWARE_TEST until a *structured* hardware record appears.
Missing record -> PENDING (never silently PASS).
"""

import datetime
import json
import os

from schemas import validate as v

SATISFIED = "SATISFIED"
WAITING = "WAITING"
INVALID = "INVALID"


def record_path(repo_root, case_id):
    return os.path.join(repo_root, "evals", "runs", "%s.json" % case_id)


def load(repo_root, case_id, override=None):
    """Return (status, report_or_None, errors, source_path)."""
    path = override or record_path(repo_root, case_id)
    if not os.path.exists(path):
        return WAITING, None, ["no hardware record at %s" % path], path
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except ValueError as e:
        return INVALID, None, ["invalid JSON: %s" % e], path
    errors = v.check("hardware_report", data)
    if errors:
        return INVALID, data, errors, path
    if data.get("case_id") != case_id:
        return INVALID, data, ["case_id mismatch: %s != %s" % (data.get("case_id"), case_id)], path
    return SATISFIED, data, [], path


def template(case_id, measured_hint=None):
    return {
        "case_id": case_id,
        "operator": "human",
        "timestamp": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "measured": measured_hint or {"example_metric": 0},
        "attachments": [],
        "notes": "填写：接了什么线、怎么测、看到什么现象",
    }
