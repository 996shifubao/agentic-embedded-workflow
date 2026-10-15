"""Tool / resource / prompt catalogue exposed over MCP.

Every tool returns a JSON-serialisable dict; the server wraps it into MCP
`content` items. Handlers reuse the same scripts the local ToolExecutor calls,
so the MCP path and the in-process path cannot drift apart.
"""

import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from rag.store import KnowledgeBase  # noqa: E402

ENV = dict(os.environ, PYTHONIOENCODING="utf-8")

RESOURCE_ROOTS = ["docs", "prompts", "agents", "evals", "examples", "schemas", "configs"]
RESOURCE_FILES = ["README.md", "AGENTS.md"]
RESOURCE_EXTS = {".md", ".yaml", ".yml", ".json", ".c", ".h", ".txt", ".diff"}


def _run_script(script, args, timeout=900):
    cmd = [sys.executable, os.path.join(REPO, "tools", script)] + [str(a) for a in args]
    proc = subprocess.run(
        cmd,
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=ENV,
        timeout=timeout,
    )
    try:
        return json.loads(proc.stdout)
    except ValueError:
        return {
            "status": "ERROR",
            "tool": script,
            "raw_stdout_tail": (proc.stdout or "").splitlines()[-10:],
            "raw_stderr_tail": (proc.stderr or "").splitlines()[-10:],
        }


# --------------------------------------------------------------------------- #
# tool handlers
# --------------------------------------------------------------------------- #
def tool_build(config):
    return _run_script("build.py", ["--config", config])


def tool_log_check(logfile, rules):
    return _run_script("log_parser.py", [logfile, "--rules", rules])


def tool_run_algorithm(cmd):
    return _run_script("test_runner.py", ["--cmd", cmd])


def tool_static_diff(diff):
    return _run_script("git_diff_check.py", ["--diff", diff])


def tool_run_eval(cases="evals/test_cases.yaml", expected="evals/expected_results.yaml"):
    return _run_script(
        "eval_runner.py",
        ["--cases", cases, "--expected", expected, "--runs-dir", "evals/runs"],
    )


def tool_kb_search(query, k=3):
    kb = KnowledgeBase(REPO)
    hits = kb.search(query, k=int(k))
    return {"status": "PASS" if hits else "EMPTY", "query": query, "hits": hits, "k": int(k)}


def tool_list_examples():
    root = os.path.join(REPO, "examples")
    items = []
    if os.path.isdir(root):
        for name in sorted(os.listdir(root)):
            path = os.path.join(root, name)
            if os.path.isdir(path):
                items.append({"name": name, "files": sorted(os.listdir(path))})
    return {"status": "PASS", "examples": items, "count": len(items)}


TOOLS = [
    {
        "name": "build",
        "description": "编译/构建封装：执行构建配置并返回结构化结果（无工具链时返回 SKIPPED）。",
        "inputSchema": {
            "type": "object",
            "properties": {"config": {"type": "string", "description": "构建配置 JSON 路径"}},
            "required": ["config"],
        },
        "handler": tool_build,
    },
    {
        "name": "log_check",
        "description": "串口/日志断言：按规则文件校验日志，返回逐条断言结果。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "logfile": {"type": "string"},
                "rules": {"type": "string", "description": "断言规则 YAML 路径"},
            },
            "required": ["logfile", "rules"],
        },
        "handler": tool_log_check,
    },
    {
        "name": "run_algorithm",
        "description": "算法层评测：运行脚本（如轴线估计）并返回 MAE/RMSE 等指标。",
        "inputSchema": {
            "type": "object",
            "properties": {"cmd": {"type": "string", "description": "要执行的命令"}},
            "required": ["cmd"],
        },
        "handler": tool_run_algorithm,
    },
    {
        "name": "static_diff",
        "description": "diff 静态规则检查：检查编码规则/边界/魔法数等问题。",
        "inputSchema": {
            "type": "object",
            "properties": {"diff": {"type": "string"}},
            "required": ["diff"],
        },
        "handler": tool_static_diff,
    },
    {
        "name": "run_eval",
        "description": "评测编排：跑全部评测用例并按层汇总（compile/unit/static/log/algorithm/hardware/regression/agent）。",
        "inputSchema": {
            "type": "object",
            "properties": {"cases": {"type": "string"}, "expected": {"type": "string"}},
        },
        "handler": tool_run_eval,
    },
    {
        "name": "kb_search",
        "description": "知识库检索：在项目文档、角色契约、评测规则与历史故障案例中检索，返回带引用的片段。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "k": {"type": "integer", "description": "返回条数，默认 3"},
            },
            "required": ["query"],
        },
        "handler": tool_kb_search,
    },
    {
        "name": "list_examples",
        "description": "列出 examples/ 下的真实故障案例与文件，供规划时选择参考。",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": tool_list_examples,
    },
]

TOOL_MAP = {t["name"]: t for t in TOOLS}


def call_tool(name, arguments):
    tool = TOOL_MAP.get(name)
    if tool is None:
        raise KeyError("unknown tool: %s" % name)
    return tool["handler"](**(arguments or {}))


# --------------------------------------------------------------------------- #
# resources & prompts
# --------------------------------------------------------------------------- #
def list_resources():
    resources = []
    for rel in RESOURCE_FILES:
        if os.path.isfile(os.path.join(REPO, rel)):
            resources.append({"uri": "repo://%s" % rel, "name": rel, "mimeType": "text/markdown"})
    for root in RESOURCE_ROOTS:
        abs_root = os.path.join(REPO, root)
        if not os.path.isdir(abs_root):
            continue
        for dirpath, dirnames, filenames in os.walk(abs_root):
            dirnames[:] = [d for d in dirnames if d not in {"__pycache__", "runs", "index"}]
            for name in sorted(filenames):
                if os.path.splitext(name)[1].lower() not in RESOURCE_EXTS:
                    continue
                rel = os.path.relpath(os.path.join(dirpath, name), REPO).replace("\\", "/")
                resources.append(
                    {
                        "uri": "repo://%s" % rel,
                        "name": rel,
                        "mimeType": "text/markdown" if rel.endswith(".md") else "text/plain",
                    }
                )
    return resources


def read_resource(uri):
    if not uri.startswith("repo://"):
        raise ValueError("unsupported uri scheme: %s" % uri)
    rel = uri[len("repo://") :]
    abs_path = os.path.normpath(os.path.join(REPO, rel))
    if not abs_path.startswith(REPO) or not os.path.isfile(abs_path):
        raise ValueError("resource not found: %s" % rel)
    with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
        return {"uri": uri, "mimeType": "text/markdown", "text": f.read()}


def list_prompts():
    prompts_dir = os.path.join(REPO, "prompts")
    items = []
    if os.path.isdir(prompts_dir):
        for name in sorted(os.listdir(prompts_dir)):
            if name.endswith(".md"):
                items.append(
                    {
                        "name": name[:-3],
                        "description": "长期约束：%s" % name,
                        "arguments": [],
                    }
                )
    return items


def get_prompt(name):
    path = os.path.join(REPO, "prompts", "%s.md" % name)
    if not os.path.isfile(path):
        raise ValueError("prompt not found: %s" % name)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    return {
        "description": "长期约束：%s.md" % name,
        "messages": [{"role": "user", "content": {"type": "text", "text": text}}],
    }


# Every catalogue entry carries the same policy the executors enforce, so a
# remote client can see which tools are read-only and which need human approval.
from runtime.policy import TOOL_POLICY, DEFAULT_POLICY  # noqa: E402

for _tool in TOOLS:
    _tool["policy"] = dict(TOOL_POLICY.get(_tool["name"], DEFAULT_POLICY))

