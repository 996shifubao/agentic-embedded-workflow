"""Tool-level policy: scopes, human approval, prompt-injection sanitising, audit.

Role permissions in `agent_factory` answer "which agent may act"; this module
answers "which *tool* may run, and with whose approval". Both executors (local
`ToolExecutor` and the MCP bridge) go through `check()` so a tool cannot be
reached by switching the back-end.
"""

import datetime
import hashlib
import json
import os
import re

# scope: read / execute / write. require_human: needs explicit approval.
TOOL_POLICY = {
    "kb_search": {"scope": "read", "require_human": False},
    "list_examples": {"scope": "read", "require_human": False},
    "log_check": {"scope": "read", "require_human": False},
    "static_diff": {"scope": "read", "require_human": False},
    "run_eval": {"scope": "execute", "require_human": False},
    "build": {"scope": "execute", "require_human": True},
    "run_algorithm": {"scope": "execute", "require_human": True},
}

DEFAULT_POLICY = {"scope": "read", "require_human": False}

# The local executor addresses tools by script name; the MCP catalogue by tool name.
SCRIPT_TO_TOOL = {
    "build.py": "build",
    "log_parser.py": "log_check",
    "test_runner.py": "run_algorithm",
    "git_diff_check.py": "static_diff",
    "eval_runner.py": "run_eval",
    "kb_query.py": "kb_search",
}

# Anything that arrives from a retrieved document, a log or a ticket is
# untrusted text; these patterns are the ones that try to take over the agent.
INJECTION_PATTERNS = [
    r"ignore (all )?(previous|above) instructions?",
    r"disregard (the )?(system|previous) prompt",
    r"you are now\b",
    r"new instructions?:",
    r"忽略(以上|上述|之前)(的)?(所有)?(指令|提示|规则)",
    r"无视(以上|上述|之前)",
    r"你现在是",
    r"新的指令[:：]",
    r"(请)?执行以下(命令|脚本|代码)",
    r"(泄露|导出).{0,6}(系统提示|system prompt)",
]
_INJECTION = re.compile("|".join(INJECTION_PATTERNS), re.I)

_APPROVED = set()


def set_approvals(tools):
    """Human approval, e.g. from `--approve build,run_algorithm`."""
    _APPROVED.clear()
    for t in tools or ():
        if t:
            _APPROVED.add(t.strip())
    return sorted(_APPROVED)


def approvals():
    return sorted(_APPROVED)


def policy_for(tool):
    return TOOL_POLICY.get(tool, DEFAULT_POLICY)


def check(tool):
    """-> (allowed, reason). Unknown tools are refused rather than defaulted."""
    if tool not in TOOL_POLICY:
        return False, "unknown tool: %s" % tool
    policy = TOOL_POLICY[tool]
    if policy["require_human"] and tool not in _APPROVED:
        return False, "requires human approval: %s (pass --approve %s)" % (tool, tool)
    return True, "ok (%s)" % policy["scope"]


def sanitize(text, source=""):
    """Strip instruction-like lines from untrusted text.

    -> (clean_text, findings). Findings are human-readable and go to the trace,
    so a stripped injection is evidence, not a silent edit.
    """
    if not text:
        return text, []
    kept, findings = [], []
    for line in str(text).splitlines():
        match = _INJECTION.search(line)
        if match:
            findings.append({
                "source": source,
                "pattern": match.group(0)[:60],
                "line": line.strip()[:120],
            })
            kept.append("[stripped: instruction-like content from untrusted source]")
        else:
            kept.append(line)
    return "\n".join(kept), findings


class AuditLog:
    """Append-only record of every tool decision (allowed and refused)."""

    def __init__(self, repo, path=None):
        self.path = os.path.join(repo, path or os.path.join("traces", "audit.jsonl"))

    def record(self, tool, decision, reason, args=None, actor="orchestrator"):
        entry = {
            "ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            "actor": actor,
            "tool": tool,
            "decision": decision,
            "reason": reason,
            "args_digest": hashlib.sha256(
                json.dumps(args or {}, ensure_ascii=False, sort_keys=True).encode()
            ).hexdigest()[:16],
        }
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def entries(self):
        if not os.path.exists(self.path):
            return []
        out = []
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        continue
        return out
