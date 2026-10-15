"""Agent factory: turn agents/*.md role contracts into AgentSpec objects.

Permission model (enforced by the orchestrator, not by prompt text):
  planner  : read only, no tools
  developer: may edit files, may build
  tester   : may NOT edit files
  reviewer : may NOT edit files
"""

import os


class AgentSpec:
    def __init__(self, name, instructions, tools, can_write, output_schema):
        self.name = name
        self.instructions = instructions
        self.tools = tools
        self.can_write = can_write
        self.output_schema = output_schema

    def __repr__(self):
        return "AgentSpec(%s, can_write=%s, tools=%s)" % (self.name, self.can_write, self.tools)


DEFS = {
    "planner": {"file": "planner.md", "tools": [], "can_write": False, "schema": "task_plan"},
    "developer": {
        "file": "developer.md",
        "tools": ["build", "git_diff_check"],
        "can_write": True,
        "schema": "change_report",
    },
    "tester": {
        "file": "tester.md",
        "tools": ["build", "log_parser", "test_runner", "eval_runner"],
        "can_write": False,
        "schema": "test_report",
    },
    "reviewer": {
        "file": "reviewer.md",
        "tools": ["git_diff_check"],
        "can_write": False,
        "schema": None,
    },
}


def load_agents(repo_root):
    agents_dir = os.path.join(repo_root, "agents")
    agents = {}
    for name, d in DEFS.items():
        path = os.path.join(agents_dir, d["file"])
        if not os.path.isfile(path):
            raise FileNotFoundError("missing role contract: %s" % path)
        with open(path, "r", encoding="utf-8") as f:
            instructions = f.read()
        agents[name] = AgentSpec(name, instructions, d["tools"], d["can_write"], d["schema"])
    return agents


def require_write_permission(spec, action="edit files"):
    if not spec.can_write:
        raise PermissionError("agent '%s' is not allowed to %s" % (spec.name, action))
