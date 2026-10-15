#!/usr/bin/env python3
"""MCP server over stdio.

Run: python -m mcp.server
Implements: initialize, tools/list, tools/call, resources/list, resources/read,
prompts/list, prompts/get, ping, shutdown.
"""

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from mcp import protocol, registry  # noqa: E402

SERVER_INFO = {"name": "agentic-embedded-workflow", "version": "1.0.0"}
INSTRUCTIONS = (
    "机电/嵌入式 Agent 工程闭环的工具层：构建、日志断言、算法评测、静态检查、"
    "评测编排、知识库检索（带引用）与案例列表。所有工具输出结构化 JSON。"
)


def handle(request):
    method = request.get("method")
    params = request.get("params") or {}

    if method == "initialize":
        return {
            "protocolVersion": protocol.PROTOCOL_VERSION,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False},
                "prompts": {"listChanged": False},
            },
            "serverInfo": SERVER_INFO,
            "instructions": INSTRUCTIONS,
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        return {
            "tools": [
                {"name": t["name"], "description": t["description"], "inputSchema": t["inputSchema"]}
                for t in registry.TOOLS
            ]
        }
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        try:
            result = registry.call_tool(name, arguments)
        except KeyError as exc:
            raise protocol.RpcError(protocol.INVALID_PARAMS, str(exc))
        except TypeError as exc:
            raise protocol.RpcError(protocol.INVALID_PARAMS, "bad arguments for %s: %s" % (name, exc))
        return {
            "content": [{"type": "text", "text": _to_text(result)}],
            "isError": bool(isinstance(result, dict) and result.get("status") == "ERROR"),
        }
    if method == "resources/list":
        return {"resources": registry.list_resources()}
    if method == "resources/read":
        uri = params.get("uri")
        try:
            content = registry.read_resource(uri)
        except ValueError as exc:
            raise protocol.RpcError(protocol.INVALID_PARAMS, str(exc))
        return {"contents": [content]}
    if method == "prompts/list":
        return {"prompts": registry.list_prompts()}
    if method == "prompts/get":
        try:
            return registry.get_prompt(params.get("name"))
        except ValueError as exc:
            raise protocol.RpcError(protocol.INVALID_PARAMS, str(exc))
    if method in ("shutdown", "exit"):
        return {"ok": True}
    raise protocol.RpcError(protocol.METHOD_NOT_FOUND, "unknown method: %s" % method)


def _to_text(result):
    import json

    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False)


def main():
    while True:
        try:
            request = protocol.read_message()
        except protocol.RpcError as exc:
            protocol.write_message(protocol.failure(None, exc.code, exc.message))
            continue
        if request is None:
            return 0
        if "id" not in request:  # notification
            continue
        msg_id = request.get("id")
        try:
            result = handle(request)
            protocol.write_message(protocol.success(msg_id, result))
        except protocol.RpcError as exc:
            protocol.write_message(protocol.failure(msg_id, exc.code, exc.message, exc.data))
        except Exception as exc:  # noqa: BLE001 - report any handler failure to the client
            protocol.write_message(
                protocol.failure(msg_id, protocol.INTERNAL_ERROR, "%s: %s" % (type(exc).__name__, exc))
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())

