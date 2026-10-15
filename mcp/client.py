"""Client for the stdio MCP server, used by the orchestrator and the evals."""

import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from mcp import protocol  # noqa: E402


class McpClient:
    """JSON-RPC client with an initialize handshake and request/response pairing."""

    def __init__(self, repo_root=None, timeout=900):
        self.repo = os.path.abspath(repo_root or REPO)
        self.timeout = timeout
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "mcp.server"],
            cwd=self.repo,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        self._next_id = 0

    # ---------- plumbing ----------
    def _request(self, method, params=None):
        self._next_id += 1
        msg_id = self._next_id
        payload = {"jsonrpc": protocol.JSONRPC, "id": msg_id, "method": method}
        if params is not None:
            payload["params"] = params
        protocol.write_message(payload, self.proc.stdin)
        while True:
            message = protocol.read_message(self.proc.stdout)
            if message is None:
                raise RuntimeError("MCP server closed the connection during %s" % method)
            if message.get("id") != msg_id:
                continue  # ignore notifications / stale ids
            if "error" in message:
                raise RuntimeError(
                    "MCP error %s: %s" % (message["error"].get("code"), message["error"].get("message"))
                )
            return message.get("result")

    def _notify(self, method, params=None):
        payload = {"jsonrpc": protocol.JSONRPC, "method": method}
        if params is not None:
            payload["params"] = params
        protocol.write_message(payload, self.proc.stdin)

    # ---------- public API ----------
    def initialize(self):
        result = self._request(
            "initialize",
            {
                "protocolVersion": protocol.PROTOCOL_VERSION,
                "capabilities": {"roots": {"listChanged": False}},
                "clientInfo": {"name": "agentic-embedded-workflow", "version": "1.0.0"},
            },
        )
        self._notify("notifications/initialized")
        return result

    def list_tools(self):
        return self._request("tools/list")["tools"]

    def call_tool(self, name, arguments=None):
        result = self._request("tools/call", {"name": name, "arguments": arguments or {}})
        text = ""
        for item in result.get("content") or []:
            if item.get("type") == "text":
                text += item.get("text", "")
        try:
            return json.loads(text)
        except ValueError:
            return {"raw": text, "isError": result.get("isError", False)}

    def list_resources(self):
        return self._request("resources/list")["resources"]

    def read_resource(self, uri):
        return self._request("resources/read", {"uri": uri})["contents"][0]

    def list_prompts(self):
        return self._request("prompts/list")["prompts"]

    def get_prompt(self, name):
        return self._request("prompts/get", {"name": name})

    def close(self):
        try:
            self._notify("shutdown")
        except Exception:  # noqa: BLE001 - best effort
            pass
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def __enter__(self):
        self.initialize()
        return self

    def __exit__(self, *exc):
        self.close()
        return False

