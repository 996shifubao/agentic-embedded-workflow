#!/usr/bin/env python3
"""Cost-governance check: routing, budget refusal, prompt cache, cost estimate.

  python tools/budget_check.py            # JSON summary for the eval harness
"""

import argparse
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import common  # noqa: E402

from runtime.budget import Budget, BudgetedRuntime, PromptCache, estimate_tokens, route_for  # noqa: E402


class _Spec:
    def __init__(self, name):
        self.name = name


class _FakeRuntime:
    name = "fake"

    def __init__(self):
        self.calls = 0

    def run(self, spec, payload):
        self.calls += 1
        return {"role": spec.name, "calls": self.calls}


def main():
    ap = argparse.ArgumentParser()
    a = ap.parse_args()

    checks = []

    def expect(name, ok, detail=""):
        checks.append({"id": name, "ok": bool(ok), "detail": detail})

    # 1. routing puts small and large payloads on different routes
    small = estimate_tokens("x" * 700)
    large = estimate_tokens("x" * 40000)
    expect("route-small", route_for(small) == "small", "tokens=%d" % small)
    expect("route-large", route_for(large) == "large", "tokens=%d" % large)

    # 2. identical calls hit the cache instead of the runtime
    runtime = _FakeRuntime()
    cache = PromptCache()
    budget = Budget(limit_tokens=100000)
    events = []
    wrapped = BudgetedRuntime(runtime, budget, cache, on_event=lambda k, d: events.append((k, d)))
    payload = {"task": "adc-001", "detail": "same input twice"}
    first = wrapped.run(_Spec("developer"), payload)
    second = wrapped.run(_Spec("developer"), payload)
    expect("cache-hit", first == second and runtime.calls == 1,
           "runtime calls=%d" % runtime.calls)
    expect("cache-rate", cache.summary()["hit_rate"] >= 0.5, str(cache.summary()))

    # 3. the budget refuses once it is gone (never silently overspends)
    tight = Budget(limit_tokens=small)
    tight.spend(small, "small")
    refused = tight.spend(small, "small") is False
    expect("budget-refuses", refused, str(tight.summary()))
    raised = False
    try:
        BudgetedRuntime(runtime, Budget(limit_tokens=1), PromptCache()).run(_Spec("tester"), {"x": "y"})
    except Exception as exc:                     # BudgetExceeded bubbles up
        raised = exc.__class__.__name__ == "BudgetExceeded"
    expect("budget-raises", raised, "BudgetExceeded raised")

    # 4. cost and trace events are produced
    expect("cost-estimated", budget.summary()["cost_estimate_usd"] > 0, str(budget.summary()))
    expect("events-logged", any(k == "budget" for k, _ in events), "events=%d" % len(events))

    failed = [c for c in checks if not c["ok"]]
    metrics = {
        "checks": len(checks),
        "passed": len(checks) - len(failed),
        "cache_hit_rate": cache.summary()["hit_rate"],
        "cache_saved_tokens": cache.summary()["saved_tokens"],
        "cost_estimate_usd": budget.summary()["cost_estimate_usd"],
        "routes_used": sorted(budget.summary()["routes"].keys()) or ["small"],
        "budget_refusals": tight.summary()["refused"],
    }
    common.emit({
        "tool": "budget_check",
        "checks": checks,
        "failed": failed,
        "metrics": metrics,
        "status": "PASS" if not failed else "FAIL",
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
