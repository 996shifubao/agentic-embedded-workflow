#!/usr/bin/env python3
"""Code-driven orchestrator: drives Planner -> Developer -> Tester -> Human Gate -> Reviewer.

Run from the repo root:
  python -m runtime.orchestrator --task tasks/adc_sampling_fix.json

Exit codes:
  0  DONE
  2  FAILED (max iterations reached or a gate failed hard)
  3  WAITING_FOR_HUMAN_HARDWARE_TEST (run is resumable)
  4  runtime unavailable (e.g. --runtime openai without credentials)
"""

import argparse
import datetime
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from runtime import agent_factory, human_gate  # noqa: E402
from runtime import state as st  # noqa: E402
from runtime.llm import RuntimeUnavailable, get_runtime  # noqa: E402
from runtime.tool_exec import ToolExecutor  # noqa: E402
from runtime.workspace import Workspace  # noqa: E402
from schemas import validate as v  # noqa: E402


def _now():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def write_text(path, text):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


class Tracer:
    def __init__(self, repo, task_id):
        self.dir = os.path.join(repo, "traces", task_id)
        os.makedirs(self.dir, exist_ok=True)
        self.path = os.path.join(self.dir, "trace.jsonl")
        open(self.path, "w", encoding="utf-8").close()

    def log(self, state, actor, payload):
        entry = {"ts": _now(), "state": str(state), "actor": actor, "payload": payload}
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry


def run(task_path, runtime_name, hardware_report, max_iterations, tool_layer="local", use_kb=True, kb_k=3,
        use_memory=False, memory_k=3, approvals=()):
    from runtime import policy

    # The orchestrator's own pipeline is human-launched (that is what the explicit
    # human gate formalises); remote MCP callers are not, and stay unapproved.
    policy.set_approvals(["build", "run_algorithm"] + [a for a in approvals if a])
    with open(task_path, "r", encoding="utf-8") as f:
        task = json.load(f)

    runtime = get_runtime(runtime_name)
    agents = agent_factory.load_agents(REPO)
    if tool_layer == "mcp":
        from runtime.mcp_bridge import McpToolExecutor

        tools = McpToolExecutor(REPO)
    else:
        tools = ToolExecutor(REPO)
    ws = Workspace(REPO, task["task_id"], task["workspace_fixture"])
    tracer = Tracer(REPO, task["task_id"])
    trace_dir = tracer.dir

    result = {
        "task_id": task["task_id"],
        "runtime": runtime.name,
        "workspace": ws.path.replace("\\", "/"),
        "iterations": 0,
        "hardware_source": None,
        "status": None,
        "final_state": None,
        "errors": [],
        "tool_layer": tool_layer,
        "knowledge": [],
    }
    state = st.State.RECEIVED
    tracer.log(state, "orchestrator", {"task": task["task_id"], "runtime": runtime.name})

    # ---------------- Planning ----------------
    state = _transition(state, st.State.PLANNING, tracer)

    # Retrieval-augmented planning: cite repo knowledge (past faults, rules, constraints)
    knowledge = []
    if use_kb:
        query = "%s %s" % (task.get("title", ""), " ".join(task.get("risks") or []))
        try:
            if tool_layer == "mcp":
                kb_result = tools.kb_search(query, kb_k)
                knowledge = kb_result.get("hits") or []
            else:
                from rag.store import KnowledgeBase

                knowledge = KnowledgeBase(REPO).search(query, k=kb_k)
        except (FileNotFoundError, RuntimeError) as exc:
            knowledge = []
            tracer.log(state, "kb_search", {"error": str(exc)})
    result["knowledge"] = [
        {"citation": h["citation"], "score": h["score"], "title": h.get("title", "")}
        for h in knowledge
    ]
    tracer.log(state, "kb_search", {"query": query, "hits": result["knowledge"]})
    if knowledge:
        print("[kb] %d hit(s): %s" % (len(knowledge), ", ".join(h["citation"] for h in knowledge)))

    # Project memory: what happened on previous runs of this repo (decisions,
    # failed gates, which tool layer was used). Separate source from the KB above.
    memory, memory_digest = [], ""
    if use_memory:
        mem_query = "%s %s" % (task.get("title", ""), " ".join(task.get("risks") or []))
        try:
            from runtime.memory import ProjectMemory

            project_memory = ProjectMemory(REPO)
            project_memory.build()
            memory = project_memory.search(mem_query, k=memory_k)
            memory_digest = project_memory.format_for_planner(mem_query, k=memory_k)
        except Exception as exc:  # memory must never break the run
            memory = []
            tracer.log(state, "memory_search", {"error": str(exc)})
    result["memory"] = [
        {"task_id": h["task_id"], "citation": h["citation"], "score": h["score"]}
        for h in memory
    ]
    tracer.log(state, "memory_search", {"hits": result["memory"]})
    if memory:
        print("[memory] %d hit(s): %s" % (len(memory), ", ".join(h["citation"] for h in memory)))

    # Untrusted text (retrieved documents, memory excerpts) is sanitised before it
    # can reach a prompt; stripped payloads are recorded, not silently dropped.
    guard_findings = []
    for hit in knowledge:
        hit["snippet"], found = policy.sanitize(hit.get("snippet", ""), hit.get("citation", ""))
        guard_findings.extend(found)
    memory_digest, found = policy.sanitize(memory_digest, "memory")
    guard_findings.extend(found)
    if guard_findings:
        tracer.log(state, "injection_guard", {"findings": guard_findings})
        print("[guard] stripped %d instruction-like line(s) from retrieved text"
              % len(guard_findings))

    plan = runtime.run(agents["planner"], {"task": task, "knowledge": knowledge,
                                           "memory": memory, "memory_digest": memory_digest})
    errors = v.check("task_plan", plan)
    tracer.log(state, "planner", {"output": plan, "schema_errors": errors})
    if errors:
        return _fail(state, result, tracer, "task_plan schema invalid", errors)
    state = _transition(state, st.State.PLAN_VALIDATED, tracer)
    print("[planner] objective: %s" % plan["objective"])

    # ---------------- Develop / Test loop ----------------
    test_report, change_report, diff_path, static_res = None, None, None, None
    for iteration in range(1, max_iterations + 1):
        result["iterations"] = iteration
        state = _transition(state, st.State.DEVELOPING, tracer)
        sources = {rel: ws.read(rel) for rel in plan["files"]}
        proposal = runtime.run(
            agents["developer"],
            {
                "plan": plan,
                "iteration": iteration,
                "sources": sources,
                "previous_test_report": test_report,
            },
        )
        agent_factory.require_write_permission(agents["developer"])
        changed = ws.apply_edits(proposal.get("edits"))
        tracer.log(state, "developer", {"edits": proposal.get("edits"), "changed_files": changed})

        # --- tool execution: build ---
        cfg_path = os.path.join(trace_dir, "build_config.json")
        src_path = os.path.join(ws.path, "adc.c")
        write_text(
            cfg_path,
            json.dumps(
                {
                    "name": task["task_id"],
                    "toolchain": None,
                    "command": task["build"]["command"]
                    .replace("{python}", '"%s"' % sys.executable)
                    .replace("{src}", '"%s"' % src_path),
                    "cwd": ".",
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
        build_res = tools.build(cfg_path)

        change_report = {
            "task_id": plan["task_id"],
            "iteration": iteration,
            "edits": proposal.get("edits"),
            "changed_files": changed,
            "build": build_res.get("status", "FAIL"),
            "notes": proposal.get("notes", ""),
        }
        errors = v.check("change_report", change_report)
        tracer.log(state, "developer:change_report", {"output": change_report, "schema_errors": errors})
        if errors:
            return _fail(state, result, tracer, "change_report schema invalid", errors)
        print("[developer] iter %d build=%s (%d warning)" % (iteration, build_res.get("status"), build_res.get("warnings", 0)))

        state = _transition(state, st.State.SOFTWARE_TESTING, tracer)

        # --- tool execution: diff / log / algorithm ---
        diff_path = ws.diff_path(os.path.join(trace_dir, "workspace.diff"))
        static_res = tools.static_diff(diff_path)

        sim = tools.run_script(
            "examples/adc_sampling_bug/sim/simulate_log.py", ["--src", src_path]
        )
        serial_path = os.path.join(trace_dir, "serial.log")
        write_text(serial_path, sim["stdout"])
        log_res = tools.log_check(
            serial_path, task.get("log_rules", "evals/log_rules/adc_fixed.yaml")
        )

        alg_res = tools.algorithm(
            "{python} examples/motor_control/scripts/estimate_axis.py "
            "examples/motor_control/input/six_pulse_samples.csv"
        )

        tool_results = {
            "build": build_res,
            "static": static_res,
            "log": log_res,
            "algorithm": alg_res,
            "regression": {"status": "SKIPPED"},
        }
        tracer.log(state, "tools", {
            "build": build_res.get("status"),
            "static": static_res.get("status"),
            "log": log_res.get("status"),
            "algorithm": alg_res.get("status"),
            "mae_ls_deg": alg_res.get("metrics", {}).get("mae_ls_deg"),
        })

        test_report = runtime.run(agents["tester"], {"task": task, "tool_results": tool_results})
        errors = v.check("test_report", test_report)
        tracer.log(state, "tester", {"output": test_report, "schema_errors": errors})
        if errors:
            return _fail(state, result, tracer, "test_report schema invalid", errors)
        print("[tester] layers=%s overall=%s" % (json.dumps(test_report["layers"]), test_report["overall"]))

        if test_report["overall"] != "PASS":
            print("[orchestrator] software gates failed -> back to developer")
            continue

        # --- human gate ---
        if test_report.get("hardware_required"):
            state = _transition(state, st.State.HUMAN_GATE, tracer)
            case_id = (test_report.get("hardware_cases") or ["unknown"])[0]
            status, report, errs, path = human_gate.load(REPO, case_id, override=hardware_report)
            tracer.log(state, "human_gate", {"case_id": case_id, "status": status, "errors": errs})
            if status == human_gate.WAITING:
                result["status"] = st.WAITING_FOR_HUMAN
                result["final_state"] = state.value
                result["blocked_on"] = {
                    "case_id": case_id,
                    "expected_record": path.replace("\\", "/"),
                    "template": human_gate.template(case_id),
                }
                _write_summary(tracer, result)
                print("[human_gate] WAITING_FOR_HUMAN_HARDWARE_TEST -> %s" % path)
                return 3, result
            if status == human_gate.INVALID:
                return _fail(state, result, tracer, "hardware report invalid", errs)
            result["hardware_source"] = report.get("operator")
            test_report.setdefault("layers", {})["hardware"] = "PASS"
            print("[human_gate] satisfied by operator=%s" % report.get("operator"))
        else:
            result["hardware_source"] = "not_required"

        # --- review ---
        state = _transition(state, st.State.REVIEWING, tracer)
        review = runtime.run(
            agents["reviewer"],
            {
                "test_report": test_report,
                "static": static_res,
                "plan": plan,
                "changed_files": change_report["changed_files"],
            },
        )
        tracer.log(state, "reviewer", {"output": review})
        print("[reviewer] %s (%s)" % (review["decision"], "; ".join(review.get("reasons", []))))
        if review["decision"] == "APPROVED":
            state = _transition(state, st.State.DONE, tracer)
            result["status"] = "DONE"
            result["final_state"] = state.value
            result["review"] = review
            _write_summary(tracer, result)
            return 0, result

    return _fail(state, result, tracer, "max iterations reached without approval", [])


def _transition(state, dst, tracer):
    if not st.can_transition(state, dst):
        raise st.TransitionError("%s -> %s not allowed" % (state, dst))
    tracer.log(dst, "orchestrator", {"from": str(state)})
    return dst


def _fail(state, result, tracer, message, errors):
    if st.can_transition(state, st.State.FAILED):
        state = _transition(state, st.State.FAILED, tracer)
        result["final_state"] = state.value
    result["status"] = "FAILED"
    result["errors"] = [message] + list(errors or [])
    tracer.log(state, "orchestrator", {"message": message, "errors": errors})
    _write_summary(tracer, result)
    print("[orchestrator] FAILED: %s" % message)
    return 2, result


def _write_summary(tracer, result):
    write_text(os.path.join(tracer.dir, "summary.json"), json.dumps(result, ensure_ascii=False, indent=2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default="tasks/adc_sampling_fix.json")
    ap.add_argument("--runtime", default="stub", choices=["stub", "openai"])
    ap.add_argument("--hardware-report", default=None)
    ap.add_argument("--max-iterations", type=int, default=3)
    ap.add_argument("--tool-layer", default="local", choices=["local", "mcp"])
    ap.add_argument("--no-kb", action="store_true", help="skip knowledge-base retrieval")
    ap.add_argument("--kb-k", type=int, default=3)
    ap.add_argument("--memory", action="store_true", help="inject past-run memory into planning")
    ap.add_argument("--memory-k", type=int, default=3)
    ap.add_argument("--approve", default="", help="extra tool approvals, e.g. run_script")
    a = ap.parse_args()
    try:
        code, result = run(
            a.task,
            a.runtime,
            a.hardware_report,
            a.max_iterations,
            tool_layer=a.tool_layer,
        use_kb=not a.no_kb,
        kb_k=a.kb_k,
        use_memory=a.memory,
        memory_k=a.memory_k,
        approvals=[t for t in (a.approve or "").split(",") if t],
        )
    except RuntimeUnavailable as e:
        print("[orchestrator] runtime unavailable: %s" % e)
        return 4
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
