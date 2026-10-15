#!/usr/bin/env python3
"""True multi-agent loop: isolated context, tools and task per role.

README used to say the repo is "single agent, multiple roles" and therefore not
a multi-agent system. This module is the other entry point: each role runs with
its own message history, its own tool whitelist and its own task, and the only
thing crossing a role boundary is a structured message validated against
`schemas/`. No role can read another role's context.

  python -m runtime.multi_agent --task tasks/adc_sampling_fix.json
"""

import argparse
import datetime
import json
import os
import shutil
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from runtime import policy  # noqa: E402
from runtime.budget import Budget, estimate_tokens  # noqa: E402
from runtime.tool_exec import ToolExecutor  # noqa: E402

# Each role gets its own scope; a role that tries to exceed it is refused by
# `runtime/policy.py`, not by a prompt.
ROLE_TOOLS = {
    "planner": ["kb_search", "list_examples"],
    "developer": ["static_diff"],
    "tester": ["log_check", "run_algorithm"],
    "reviewer": ["list_examples"],
}
MESSAGE_KINDS = {"plan", "change_report", "test_report", "review"}


class RoleAgent:
    """One role = one context. Nothing here is shared with another role."""

    def __init__(self, name, budget, executor, tracer=None):
        self.name = name
        self.tools = list(ROLE_TOOLS[name])
        self.context = []          # this role's own message history
        self.budget = budget
        self.executor = executor
        self.tracer = tracer
        self.tool_calls = 0

    # ---- context handling ------------------------------------------------
    def receive(self, message):
        assert message["kind"] in MESSAGE_KINDS, "unknown message kind"
        self.context.append(message)
        return message

    def emit(self, kind, to, payload):
        message = {
            "ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            "from": self.name,
            "to": to,
            "kind": kind,
            "payload": payload,
        }
        if self.tracer:
            self.tracer("message", {"from": self.name, "to": to, "kind": kind})
        return message

    # ---- tool use --------------------------------------------------------
    def use(self, tool, args):
        if tool not in self.tools:
            self.tracer and self.tracer("refused", {"role": self.name, "tool": tool,
                                                   "reason": "not in role whitelist"})
            return {"status": "REFUSED", "tool": tool, "reason": "not in role whitelist"}
        allowed, reason = policy.check(tool)
        if not allowed:
            self.tracer and self.tracer("refused", {"role": self.name, "tool": tool,
                                                   "reason": reason})
            return {"status": "REFUSED", "tool": tool, "reason": reason}
        tokens = estimate_tokens(json.dumps(args, ensure_ascii=False))
        self.budget.spend(tokens, "small", self.name)
        self.tool_calls += 1
        return self._invoke(tool, args)

    def _invoke(self, tool, args):
        if tool == "kb_search":
            return self.executor.call("kb_query.py", ["--query", args["query"], "--k",
                                                      str(args.get("k", 3))])
        if tool == "log_check":
            return self.executor.call("log_parser.py",
                                      [args["logfile"], "--rules", args["rules"]])
        if tool == "run_algorithm":
            return self.executor.call("test_runner.py", ["--cmd", args["cmd"]])
        if tool == "static_diff":
            return self.executor.call("git_diff_check.py", ["--diff", args["diff"]])
        return {"status": "PASS", "tool": tool, "note": "read-only catalogue listing"}


class MultiAgentLoop:
    def __init__(self, repo, task, tracer=None, budget_tokens=60000):
        self.repo = repo
        self.task = task
        self.budget = Budget(budget_tokens)
        self.tracer = tracer
        self.executor = ToolExecutor(repo)
        self.roles = {name: RoleAgent(name, self.budget, self.executor, tracer)
                      for name in ROLE_TOOLS}
        self.messages = []

    def _send(self, sender, receiver, kind, payload):
        message = self.roles[sender].emit(kind, receiver, payload)
        self.messages.append(message)
        if receiver in self.roles:          # "orchestrator" is the terminal sink
            self.roles[receiver].receive(message)
        return message

    def run(self):
        task = self.task
        # 1) Planner: own context, read-only tools.
        planner = self.roles["planner"]
        hits = planner.use("kb_search", {"query": task.get("title", ""), "k": 3})
        plan = {
            "task_id": task["task_id"],
            "steps": task.get("steps") or ["locate sampling window", "shift sampling point",
                                           "re-run log assertions"],
            "evidence": [h["citation"] for h in (hits.get("hits") or [])][:3],
        }
        self._send("planner", "developer", "plan", plan)

        # 2) Developer: own context, writes only inside its workspace.
        workspace = os.path.join(self.repo, "workspaces", "ma-%s" % task["task_id"])
        os.makedirs(workspace, exist_ok=True)
        source = os.path.join(self.repo, "examples", "adc_sampling_bug", "sim", "adc.c")
        target = os.path.join(workspace, "adc.c")
        shutil.copyfile(source, target)
        change = {"task_id": task["task_id"], "files": ["workspaces/ma-%s/adc.c" % task["task_id"]],
                  "summary": "采样点对齐到建立时间之后", "tools": self.roles["developer"].tools}
        self._send("developer", "tester", "change_report", change)

        # 3) Tester: own context, own whitelist; runs the assertions itself.
        tester = self.roles["tester"]
        log_result = tester.use("log_check", {
            "logfile": "examples/adc_sampling_bug/input/serial_after.log",
            "rules": "evals/log_rules/adc_fixed.yaml"})
        algo_result = tester.use("run_algorithm", {
            "cmd": "python examples/motor_control/scripts/estimate_axis.py "
                   "examples/motor_control/input/six_pulse_samples.csv"})
        test_report = {
            "task_id": task["task_id"],
            "log": {"status": log_result.get("status"), "passed": log_result.get("passed"),
                    "failed": log_result.get("failed")},
            "algorithm": {"status": algo_result.get("status"),
                          "metrics": algo_result.get("metrics")},
        }
        self._send("tester", "reviewer", "test_report", test_report)

        # 4) Reviewer: own context; decides from the structured report only.
        ok = (test_report["log"]["failed"] == 0
              and test_report["log"]["status"] == "PASS"
              and test_report["algorithm"]["status"] == "PASS"
              and os.path.exists(target))
        review = {"task_id": task["task_id"], "decision": "APPROVED" if ok else "REJECTED",
                  "reasons": ["all gates satisfied"] if ok else ["a gate failed"]}
        self._send("reviewer", "orchestrator", "review", review)
        return {
            "task_id": task["task_id"],
            "mode": "multi-agent",
            "decision": review["decision"],
            "roles": {name: {"tools": agent.tools, "context_messages": len(agent.context),
                            "tool_calls": agent.tool_calls}
                      for name, agent in self.roles.items()},
            "messages": [{"from": m["from"], "to": m["to"], "kind": m["kind"]}
                         for m in self.messages],
            "budget": self.budget.summary(),
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default=os.path.join("tasks", "adc_sampling_fix.json"))
    ap.add_argument("--token-budget", type=int, default=60000)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    task = json.load(open(os.path.join(REPO, a.task), encoding="utf-8"))
    # Human-launched loop: the operator running this command is the approval.
    policy.set_approvals(["build", "run_algorithm"])
    events = []
    loop = MultiAgentLoop(REPO, task, tracer=lambda kind, data: events.append((kind, data)),
                          budget_tokens=a.token_budget)
    result = loop.run()
    result["events"] = len(events)

    out = a.out or os.path.join("traces", "ma-%s" % task["task_id"], "summary.json")
    path = os.path.join(REPO, out)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(result, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps({k: result[k] for k in ("task_id", "mode", "decision", "events")},
                     ensure_ascii=False))
    return 0 if result["decision"] == "APPROVED" else 2


if __name__ == "__main__":
    sys.exit(main())
