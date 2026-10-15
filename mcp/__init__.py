"""Minimal, dependency-free MCP (Model Context Protocol) tool layer.

Exposes the harness tools, the repo knowledge base and the role contracts as
MCP tools / resources / prompts over stdio (JSON-RPC 2.0, Content-Length
framing) so any MCP-capable client can drive the same toolbox the orchestrator
uses internally.
"""

