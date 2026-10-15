"""Runtime abstraction: how a role actually gets executed.

Two implementations behind one interface:

  StubRuntime   deterministic, rule-based, offline. Default for demo/CI.
                It encodes real engineering rules (e.g. "align the ADC sample
                offset with the settling time"), not random output.

  OpenAIRuntime calls a hosted model and asks for the same JSON contract.
                Requires OPENAI_API_KEY and OPENAI_MODEL. NOT exercised by the
                in-repo demo/CI -- verify it against official OpenAI docs before
                first real use.

The interface is deliberately narrow: `run(spec, payload) -> dict`.
All filesystem and tool side effects stay in the orchestrator, so a runtime
swap cannot change what an agent is *allowed* to touch.
"""

import json
import os
import re
import urllib.error
import urllib.request


class RuntimeUnavailable(RuntimeError):
    pass


class AgentRuntime:
    name = "base"

    def run(self, spec, payload):
        raise NotImplementedError


# --------------------------------------------------------------------------
# Stub runtime: deterministic role behaviour
# --------------------------------------------------------------------------
def _define(text, name):
    m = re.search(r"#define\s+%s\s+(\S+)" % re.escape(name), text)
    if not m:
        raise ValueError("define %s not found" % name)
    return m.group(1)


class StubRuntime(AgentRuntime):
    name = "stub"

    def run(self, spec, payload):
        fn = getattr(self, "_" + spec.name, None)
        if fn is None:
            raise RuntimeUnavailable("stub has no behaviour for role %s" % spec.name)
        return fn(spec, payload)

    def _planner(self, spec, payload):
        task = payload["task"]
        return {
            "task_id": task["task_id"],
            "objective": task["title"],
            "files": task.get("files", ["adc.c"]),
            "constraints": task.get("constraints", []),
            "acceptance": task.get("acceptance", {"build": "PASS", "regression": "PASS"}),
            "hardware_layers": task.get("hardware_layers", []),
            "risks": task.get("risks", []),
        }

    def _developer(self, spec, payload):
        text = payload["sources"].get("adc.c", "")
        settle = _define(text, "SETTLING_US")
        current = _define(text, "SAMPLE_OFFSET_US")
        # change_report.build is filled by the orchestrator from the real build tool
        return {
            "task_id": payload["plan"]["task_id"],
            "iteration": payload["iteration"],
            "edits": [
                {
                    "op": "set_define",
                    "file": "adc.c",
                    "name": "SAMPLE_OFFSET_US",
                    "value": int(settle),
                }
            ],
            "changed_files": ["adc.c"],
            "build": "PASS",
            "notes": "Align ADC sample offset (%s us) with settling time (%s us)."
            % (current, settle),
        }

    def _tester(self, spec, payload):
        tr = payload["tool_results"]
        layers = {
            "build": tr["build"].get("status", "FAIL"),
            "static": tr["static"].get("status", "FAIL"),
            "log": tr["log"].get("status", "FAIL"),
            "algorithm": tr["algorithm"].get("status", "FAIL"),
            "regression": tr.get("regression", {}).get("status", "SKIPPED"),
        }
        overall = "FAIL" if any(v == "FAIL" for v in layers.values()) else "PASS"
        return {
            "task_id": payload["task"]["task_id"],
            "layers": layers,
            "overall": overall,
            "hardware_required": bool(payload["task"].get("hardware_required")),
            "hardware_cases": payload["task"].get("hardware_cases", []),
            "evidence": [
                "build: %s" % tr["build"].get("status"),
                "static: %s" % tr["static"].get("status"),
                "log: %s" % tr["log"].get("status"),
                "algorithm: %s" % tr["algorithm"].get("metrics", {}).get("mae_ls_deg"),
            ],
        }

    def _reviewer(self, spec, payload):
        reasons = []
        if payload["test_report"].get("overall") != "PASS":
            reasons.append("test report overall=%s" % payload["test_report"].get("overall"))
        high = [f for f in payload["static"].get("findings", []) if f.get("severity") == "high"]
        if high:
            reasons.append("static high-severity findings: %d" % len(high))
        allowed = set(payload["plan"].get("files", []))
        unexpected = sorted(set(payload.get("changed_files", [])) - allowed)
        if unexpected:
            reasons.append("changed files outside plan: %s" % unexpected)
        return {
            "task_id": payload["test_report"].get("task_id"),
            "decision": "APPROVED" if not reasons else "REQUEST_CHANGES",
            "reasons": reasons or ["all gates satisfied"],
        }


# --------------------------------------------------------------------------
# Hosted runtime (not exercised by the in-repo demo)
# --------------------------------------------------------------------------
def _first_json_object(text):
    depth, start = 0, None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    return json.loads(text[start : i + 1])
                except ValueError:
                    start = None
    raise ValueError("no JSON object found in model output")


class OpenAIRuntime(AgentRuntime):
    name = "openai"

    def __init__(self, model=None, api_key=None, base_url=None):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.model = model or os.environ.get("OPENAI_MODEL")
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        if not self.api_key:
            raise RuntimeUnavailable("OPENAI_API_KEY is not set")
        if not self.model:
            raise RuntimeUnavailable("OPENAI_MODEL is not set")

    def run(self, spec, payload):
        prompt = (
            "You are the %s agent. Follow your instructions exactly.\n"
            "Return ONLY a JSON object matching the required output contract.\n\n"
            "## Instructions\n%s\n\n## Input payload\n%s\n"
            % (spec.name, spec.instructions, json.dumps(payload, ensure_ascii=False, indent=2))
        )
        body = json.dumps({"model": self.model, "input": prompt}).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + "/responses",
            data=body,
            headers={
                "Authorization": "Bearer %s" % self.api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise RuntimeUnavailable("HTTP %s from model endpoint: %s" % (e.code, e.read()[:200]))

        text = data.get("output_text")
        if not text:
            parts = []
            for item in data.get("output", []) or []:
                for c in item.get("content", []) or []:
                    if isinstance(c, dict) and isinstance(c.get("text"), str):
                        parts.append(c["text"])
            text = "\n".join(parts)
        if not text:
            raise RuntimeUnavailable("empty model output")
        return _first_json_object(text)


def get_runtime(name="stub"):
    if name in (None, "", "stub"):
        return StubRuntime()
    if name == "openai":
        return OpenAIRuntime()
    raise RuntimeUnavailable("unknown runtime: %s" % name)
