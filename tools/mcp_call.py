#!/usr/bin/env python3
"""Drive the MCP tool layer from the shell (and from the eval harness).

Conformance check (default):
  python tools/mcp_call.py --check

Call one tool:
  python tools/mcp_call.py --tool kb_search --args "{\"query\": \"ADC 采样窗口\", \"k\": 3}"

Read a resource / prompt:
  python tools/mcp_call.py --resource repo://prompts/coding_rules.md
  python tools/mcp_call.py --prompt coding_rules
"""

import argparse
import json
import os
import sys
import time

import common

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from mcp.client import McpClient  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--tool")
    ap.add_argument("--args", default="{}")
    ap.add_argument("--resource")
    ap.add_argument("--prompt")
    a = ap.parse_args()

    t0 = time.time()
    with McpClient(REPO) as client:
        tools = client.list_tools()

        if a.tool:
            result = client.call_tool(a.tool, json.loads(a.args))
            result.setdefault("tool", "mcp_call")
            result["mcp"] = {"requested_tool": a.tool}
            result["duration_ms"] = int((time.time() - t0) * 1000)
            common.emit(result)
            return 0

        if a.resource:
            content = client.read_resource(a.resource)
            common.emit(
                {
                    "tool": "mcp_call",
                    "status": "PASS",
                    "resource": a.resource,
                    "chars": len(content.get("text", "")),
                    "head": content.get("text", "")[:120],
                }
            )
            return 0

        if a.prompt:
            prompt = client.get_prompt(a.prompt)
            common.emit(
                {
                    "tool": "mcp_call",
                    "status": "PASS",
                    "prompt": a.prompt,
                    "messages": len(prompt.get("messages", [])),
                }
            )
            return 0

        # conformance check: handshake + tools + resources + prompts + real calls
        resources = client.list_resources()
        prompts = client.list_prompts()
        kb_sample = client.call_tool("kb_search", {"query": "ADC 采样窗口 振铃", "k": 3})
        log_sample = client.call_tool(
            "log_check",
            {
                "logfile": "examples/adc_sampling_bug/input/serial_after.log",
                "rules": "evals/log_rules/adc_fixed.yaml",
            },
        )
        tool_names = [t["name"] for t in tools]
        kb_hits = kb_sample.get("hits") or []
        common.emit(
            {
                "tool": "mcp_call",
                "tools": tool_names,
                "tools_count": len(tool_names),
                "resources_count": len(resources),
                "prompts_count": len(prompts),
                "kb_hits": len(kb_hits),
                "kb_top1": kb_hits[0].get("citation") if kb_hits else None,
                "log_check_status": log_sample.get("status"),
                "duration_ms": int((time.time() - t0) * 1000),
                "status": "PASS"
                if len(tool_names) >= 6
                and resources
                and prompts
                and kb_hits
                and log_sample.get("status") == "PASS"
                else "FAIL",
            }
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

