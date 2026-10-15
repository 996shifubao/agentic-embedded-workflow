"""Tool Execution stage: run the harness tools and return structured results."""

import json
import os
import subprocess
import sys

from runtime import policy


class ToolExecutor:
    def __init__(self, repo_root):
        self.repo = os.path.abspath(repo_root)

    def call(self, tool, args, timeout=900):
        """Run tools/<tool>.py and parse its JSON stdout."""
        # Every execution is audited; policy enforcement for remote callers lives
        # at the MCP boundary (see runtime/mcp_bridge.py).
        gate_tool = policy.SCRIPT_TO_TOOL.get(os.path.basename(tool), os.path.basename(tool))
        policy.AuditLog(self.repo).record(gate_tool, "allow", "local executor", {"args": list(args)})
        cmd = [sys.executable, os.path.join(self.repo, "tools", tool)] + list(args)
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        p = subprocess.run(
            cmd,
            cwd=self.repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=timeout,
        )
        try:
            return json.loads(p.stdout)
        except ValueError:
            return {
                "status": "ERROR",
                "tool": tool,
                "raw_stdout_tail": (p.stdout or "").splitlines()[-10:],
                "raw_stderr_tail": (p.stderr or "").splitlines()[-10:],
            }

    # ---------- concrete layers ----------
    def build(self, config):
        return self.call("build.py", ["--config", config])

    def static_diff(self, diff_path):
        return self.call("git_diff_check.py", ["--diff", diff_path])

    def log_check(self, logfile, rules):
        return self.call("log_parser.py", [logfile, "--rules", rules])

    def algorithm(self, cmd):
        return self.call("test_runner.py", ["--cmd", cmd])

    def run_script(self, script, args=()):
        """Run a repo script (e.g. the simulation fixture) and return stdout."""
        cmd = [sys.executable, os.path.join(self.repo, script)] + list(args)
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        p = subprocess.run(
            cmd,
            cwd=self.repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=300,
        )
        return {"exit_code": p.returncode, "stdout": p.stdout, "stderr": p.stderr}
