# MCP 工具层（Tool Layer）

## 为什么要有这一层

编排器内部直接调用 `tools/*.py` 也能跑，但那样 Agent 的工具集合被写死在进程里：
换一个客户端（IDE、桌面 Agent、别的编排器）就得重新接一遍；权限也没法在进程边界上收口。
MCP（Model Context Protocol）解决的就是这件事：**把工具箱变成一个有协议、可发现、可审计的服务**。

本仓库的 MCP 服务是**手写的、零第三方依赖**实现（`mcp/protocol.py` 只做 JSON-RPC 2.0 与
`Content-Length` 分帧），这样 CI 与离线 demo 行为一致。

## 服务暴露了什么

| 类别 | 内容 | 用途 |
|---|---|---|
| tools | `build`、`log_check`、`run_algorithm`、`static_diff`、`run_eval`、`kb_search`、`list_examples` | Agent 真正执行的工程动作 |
| resources | `repo://docs/...`、`repo://prompts/...`、`repo://agents/...`、`repo://evals/...`、`repo://examples/...` | 只读上下文（规格、约束、案例） |
| prompts | `prompts/*.md`（coding_rules、hardware_constraints、project_context） | 长期约束以 Prompt 形式下发 |

每个工具用 `inputSchema` 声明参数；调用返回结构化 JSON，服务把它包成 MCP `content`。

## 怎么用

```bash
# 1) 一致性自检：握手 + tools/list + resources/list + prompts/list + 真实调用
python tools/mcp_call.py --check

# 2) 单独调工具（等价于 Agent 的工具调用）
python tools/mcp_call.py --tool kb_search --args "{\"query\": \"ADC 采样窗口 振铃\", \"k\": 3}"
python tools/mcp_call.py --tool log_check --args "{\"logfile\": \"examples/adc_sampling_bug/input/serial_after.log\", \"rules\": \"evals/log_rules/adc_fixed.yaml\"}"

# 3) 读资源 / 取 Prompt
python tools/mcp_call.py --resource repo://prompts/hardware_constraints.md
python tools/mcp_call.py --prompt coding_rules

# 4) 编排器改用 MCP 工具层（默认仍是进程内直调）
python -m runtime.orchestrator --task tasks/adc_sampling_fix.json --tool-layer mcp
```

`runtime/mcp_bridge.py` 里的 `McpToolExecutor` 与本地 `ToolExecutor` **方法名一一对应**
（`build` / `static_diff` / `log_check` / `algorithm`），所以编排器只换一个开关，
角色权限与 Trace 逻辑完全不变。

## 边界

- **只读才走 MCP**：`resources/read` 只能读仓库内的相对路径，越界路径会被拒绝。
- `run_script` 这类仓库内脚本执行**故意不暴露**为 MCP 工具，避免把任意脚本执行权交出去。
- 工具返回 `status=ERROR` 时，MCP 响应置 `isError=true`，上层据此回退或重试。

## 验证

| 用例 | 层 | 断言 |
|---|---|---|
| `mcp-001-conformance` | mcp | 工具数 ≥ 6、resources/prompts 非空、`kb_search` 有命中、`log_check` 返回 PASS |

