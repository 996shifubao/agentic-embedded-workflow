#!/usr/bin/env python3
"""Assert on a serial/UART log using a rule file.

Usage:
  python tools/log_parser.py <logfile> --rules evals/log_rules/adc_fixed.yaml

Rule types:
  must_contain / must_not_contain              pattern
  max_value / min_value                        pattern(capture g1), limit
  all_values_max                               pattern(all), limit
  regex_count_min / regex_count_max            pattern, limit
"""

import argparse
import re
import sys

import common


def evaluate(text, rule):
    t = rule["type"]
    pat = rule["pattern"]
    limit = rule.get("limit")

    if t == "must_contain":
        ok = re.search(pat, text) is not None
        return ok, "found" if ok else "pattern not found"
    if t == "must_not_contain":
        m = re.search(pat, text)
        return m is None, "absent" if m is None else "unexpected match: %s" % m.group(0)
    if t in ("max_value", "min_value"):
        vals = [float(m) for m in re.findall(pat, text)]
        if not vals:
            return False, "no value matched"
        v = max(vals) if t == "max_value" else min(vals)
        ok = v <= limit if t == "max_value" else v >= limit
        return ok, "%s=%.4f limit=%s" % (t, v, limit)
    if t == "all_values_max":
        vals = [float(m) for m in re.findall(pat, text)]
        if not vals:
            return False, "no value matched"
        v = max(vals)
        return v <= limit, "max=%.4f limit=%s n=%d" % (v, limit, len(vals))
    if t in ("regex_count_min", "regex_count_max"):
        n = len(re.findall(pat, text))
        ok = n >= limit if t == "regex_count_min" else n <= limit
        return ok, "count=%d limit=%s" % (n, limit)
    return False, "unknown rule type: %s" % t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("logfile")
    ap.add_argument("--rules", required=True)
    a = ap.parse_args()

    text = common.read_text(a.logfile)
    rules = (common.load_structured(a.rules) or {}).get("assertions") or []

    assertions, passed = [], 0
    for rule in rules:
        ok, detail = evaluate(text, rule)
        passed += 1 if ok else 0
        assertions.append(
            {"id": rule.get("id"), "type": rule.get("type"), "ok": bool(ok), "detail": detail}
        )

    result = {
        "tool": "log_parser",
        "logfile": a.logfile.replace("\\", "/"),
        "total": len(assertions),
        "passed": passed,
        "failed": len(assertions) - passed,
        "assertions": assertions,
        "stats": {"lines": len(text.splitlines())},
        "status": "PASS" if assertions and passed == len(assertions) else "FAIL",
    }
    common.emit(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
