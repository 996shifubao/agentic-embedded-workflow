# AGENTS.md — 给 AI 编码 Agent 的工程上下文

本文件是仓库对 AI Agent（Codex 等）的**长期约束入口**：它回答"在这个仓库里做什么、怎么做、
什么不能做"。人读 `README.md`，Agent 先读本文件。

## 工作方式

1. **先查再改**：动代码前先用 `kb_search`（`python tools/mcp_call.py --tool kb_search --args ...`）
   检索历史故障案例、编码规则与硬件约束，方案里引用命中结果。
2. **改完必测**：任何修改都要跑 `python tools/eval_runner.py`（八层评测），
   `FAIL/ERROR` 必须为 0；实机层缺证据记 `PENDING`，**不许猜**。
3. **改完必留痕**：说明改了哪个文件、为什么、跑了哪些用例、结果如何。

## 硬约束

- 只改任务允许的文件；`Planner` 只读、`Tester`/`Reviewer` 不可写文件（权限在
  `runtime/agent_factory.py` 里硬编码，不靠提示词约束）。
- 禁止把敏感值（密钥、真实个人信息、未脱敏的客户日志）写进仓库或 Trace。
- 不改 `evals/expected_results.yaml` 的阈值来让用例通过；阈值调整必须与实现分开提交。
- 实机结论只能来自人填写的 `evals/runs/<case>.json`。

## 技术栈约定

- 仅标准库：不引入第三方依赖（否则 CI 与离线 demo 的复现性失效）。
- 工具输出统一结构化 JSON，便于评测断言与 Trace 记录。
- 新增能力要同时给出：实现 + 用例 + 文档，三件套缺一不可。
