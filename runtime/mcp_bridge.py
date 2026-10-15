"""Route the orchestrator's tool calls through the MCP server.

`McpToolExecutor` mirrors `ToolExecutor`'s method names, so the orchestrator can
switch tool back-ends with one flag while every call still lands in the trace.
"""

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from mcp.client import McpClient  # noqa: E402
from runtime.tool_exec import ToolExecutor  # noqa: E402


class McpToolExecutor:
    def __init__(self, repo_root):
        self.repo = os.path.abspath(repo_root)
        self.local = ToolExecutor(self.repo)
        self.client = McpClient(self.repo)
        self.handshake = self.client.initialize()
        self.tools = [t["name"] for t in self.client.list_tools()]

    # ---------- same surface as ToolExecutor ----------
    def build(self, config):
        return self.client.call_tool("build", {"config": config})

    def static_diff(self, diff_path):
        return self.client.call_tool("static_diff", {"diff": diff_path})

    def log_check(self, logfile, rules):
        return self.client.call_tool("log_check", {"logfile": logfile, "rules": rules})

    def algorithm(self, cmd):
        return self.client.call_tool("run_algorithm", {"cmd": cmd})

    def run_script(self, script, args=()):
        """Repo-local scripts are executed in-process by design.

        Arbitrary script execution is deliberately NOT exposed as an MCP tool:
        the protocol boundary only carries the engineering operations above, so a
        remote client can never ask this repo to run an arbitrary path.
        """
        return self.local.run_script(script, args)

    # ---------- knowledge layer ----------
    def kb_search(self, query, k=3):
        return self.client.call_tool("kb_search", {"query": query, "k": k})

    def list_examples(self):
        return self.client.call_tool("list_examples", {})

    def close(self):
        self.client.close()
