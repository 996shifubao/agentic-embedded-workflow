# Agentic Engineering Workflow

> 面向真实机电/嵌入式系统的 **human‑in‑the‑loop Agent 工程闭环**：任务拆解 → 跨文件代码分析 → 实现 → 工具执行 → 软件验证 → 实机验证 → 反馈回灌 → Review → 迭代 → Git/文档。

这个仓库不是"我如何用 AI 聊天"的记录，而是一套**可运行、可评测**的骨架：

- **agents/**：Planner / Developer / Tester / Reviewer 四个角色的工作约定（不是四个独立 agent 进程，见下方"诚实边界"）。
- **tools/**：真正会被 Agent 调用的脚本（构建、日志解析、测试、diff 检查、评测编排）。
- **evals/**：用例、期望结果与评测方法——回答"你怎么知道 Agent 真的变好了"。
- **examples/**：来自真实项目的失败/修复案例（PWM 无输出、ADC 采样窗口、六脉冲轴线估计）。

---

## 1. 为什么需要它

纯软件 Agent 的闭环是：改代码 → 编译 → 跑测试。

机电系统的闭环多了一段**物理段**：MCU 烧录、电机转动、示波器/逻辑分析仪波形、串口日志。
Agent 无法直接操作示波器，所以这一段必须由人完成，并把结果**重新喂回** Agent。这个"人在环"的接口，
正是本仓库试图标准化的东西。

```
需求 / Bug / 实验目标
        │
        ▼
[Planner / Analysis]   拆任务、读代码、理清调用链与软硬件接口
        │
        ▼
[Implementation]       跨文件修改 C / Python / MATLAB / 配置
        │
        ▼
[Tool Execution]       git diff · shell · python · 编译器 · 日志解析
        │
        ▼
[Software Validation]  编译 · 静态检查 · 单元测试 · 日志断言
        │
        ▼
[Physical Validation]  人工：烧录 · 上电 · 测波形 · 采串口日志   ← human-in-the-loop
        │
        ▼
[Feedback]             日志/波形/错误现象回灌给 Agent
        │
        ▼
[Review / Iteration]   归因失败 → 改方案 → 重新验证
        │
        ▼
[Git Commit / Docs]    分阶段提交 + 记录本轮指标
```

## 2. 目录结构

```
agentic-embedded-workflow/
├── agents/                     # 角色工作约定（输入/输出/完成标准/交接格式）
│   ├── planner.md
│   ├── developer.md
│   ├── tester.md
│   └── reviewer.md
├── prompts/                    # 长期约束
│   ├── coding_rules.md
│   ├── hardware_constraints.md
│   └── project_context.md
├── runtime/                    # 执行层：状态机 + Agent 工厂 + 工具执行 + 人工 Gate
│   ├── orchestrator.py         # 代码驱动的状态机（入口）
│   ├── state.py                # 状态与允许的迁移
│   ├── agent_factory.py        # 把 agents/*.md 变成 AgentSpec（含权限）
│   ├── llm.py                  # Runtime 抽象：StubRuntime / OpenAIRuntime
│   ├── workspace.py            # 每任务隔离工作区 + 声明式编辑 + diff
│   ├── tool_exec.py            # Tool Execution 阶段
│   └── human_gate.py           # WAITING_FOR_HUMAN_HARDWARE_TEST
├── schemas/                    # 结构化协议（角色之间不传大段自然语言）
│   ├── task_plan.schema.json
│   ├── change_report.schema.json
│   ├── test_report.schema.json
│   ├── hardware_report.schema.json
│   └── validate.py             # 极简 JSON-Schema 子集校验器
├── tools/                      # Agent 真正调用的工具（无第三方依赖）
│   ├── mini_yaml.py            # 极简 YAML 子集解析器
│   ├── build.py                # 封装编译，输出结构化结果
│   ├── log_parser.py           # 串口日志断言
│   ├── test_runner.py          # 运行测试脚本并结构化结果
│   ├── git_diff_check.py       # 对 diff 做规则检查
│   └── eval_runner.py          # 评测编排：分层执行 + 汇总报告
├── evals/                      # 评测资产
│   ├── test_cases.yaml         # 用例定义（分层、是否可自动化）
│   ├── expected_results.yaml   # 期望结果与阈值
│   ├── log_rules/              # 日志断言规则
│   ├── agent_metrics_template.csv  # Agent 过程指标记录表
│   ├── runs/                   # 人工填写的实机/Agent 运行记录
│   └── regression/             # 回归用例
├── examples/                   # 真实案例
│   ├── pwm_issue/              # UCC20225 输入有 PWM、输出无波形
│   ├── adc_sampling_bug/       # 采样窗口落在开关振铃区（含 sim/ 仿真夹具）
│   └── motor_control/          # 六脉冲二维电流增量 → LS 轴线估计
├── tasks/                      # 任务输入（驱动编排器）
├── fixtures/                   # 明确标注的测试夹具（非真实测量）
├── workspaces/                 # 运行时生成的隔离工作区（.gitignore）
├── traces/                     # 每次运行的 trace.jsonl + summary.json
├── configs/                    # 构建工具链配置模板
├── docs/                       # 架构与评测方法说明
└── README.md
```

新增的工具层与检索层：

```
├── AGENTS.md                   # 给 AI 编码 Agent 的工程上下文与硬约束（Agent 先读它）
├── mcp/                        # 手写 MCP 工具层（JSON-RPC 2.0 over stdio，零依赖）
│   ├── protocol.py             # 分帧与错误码
│   ├── registry.py             # tools / resources / prompts 目录 + 处理函数
│   ├── server.py               # 服务端：initialize / tools/* / resources/* / prompts/*
│   └── client.py               # 客户端：握手 + 调用（编排器与评测共用）
├── rag/                        # 项目内知识库（分块 + 倒排索引 + BM25）
│   ├── chunker.py              # 标题/段落分块，块可回溯到 path#Lx-Ly
│   ├── index.py                # CJK 二元组 + ASCII 词，字段加权
│   └── store.py                # 建库 / 加载 / 检索（返回带引用的片段）
├── runtime/mcp_bridge.py       # McpToolExecutor：与本地 ToolExecutor 同接口
├── docs/mcp-tool-layer.md      # 工具层设计说明
├── docs/rag-knowledge-base.md  # 知识库设计说明
└── evals/rag_cases.yaml        # 检索质量用例（query → 期望命中文档）
```

## 3. 编排器（Runtime 层）

外层是**代码驱动的确定性状态机**，只有角色内部的判断交给 Agent：

```
RECEIVED → PLANNING → PLAN_VALIDATED
   → [ DEVELOPING → SOFTWARE_TESTING ]*        失败则回到 DEVELOPING（有上限）
   → HUMAN_GATE                                 需要实机时必须暂停
   → REVIEWING → DONE | 回到 DEVELOPING
```

```bash
# 1) 无人值守跑到人工 Gate 前，停下等实机证据
python -m runtime.orchestrator --task tasks/adc_sampling_fix.json     # 退出码 3

# 2) 提供结构化实机记录后继续（resume）
python -m runtime.orchestrator --task tasks/adc_sampling_fix.json \
    --hardware-report fixtures/hardware_report.fixture.json           # 退出码 0
```

退出码：`0` DONE｜`2` FAILED（含达到迭代上限）｜`3` WAITING_FOR_HUMAN_HARDWARE_TEST｜`4` runtime 不可用。

**Runtime 抽象**（`runtime/llm.py`）：

| 实现 | 行为 | 用途 |
|---|---|---|
| `StubRuntime`（默认） | 确定性、离线；编码真实工程规则（"把采样点对齐到建立时间之后"） | demo / CI |
| `OpenAIRuntime` | 调托管模型，要求同样的 JSON 契约；需 `OPENAI_API_KEY` + `OPENAI_MODEL` | 真实使用 |

两者共用同一接口 `run(spec, payload) -> dict`；**文件与工具副作用全部留在编排器里**，
所以换 runtime 不会改变某个角色"被允许碰什么"。权限在 `agent_factory` 里硬编码：
Planner 只读、Tester/Reviewer 不能写文件、只有 Developer 能改代码。

每次运行留下 `traces/<task_id>/trace.jsonl`（逐状态、逐 Agent）与 `summary.json`。

### 工具层：MCP（Model Context Protocol）

工具箱不只是"进程里几个函数"，而是一个**有协议、可发现、可被外部客户端复用**的服务：

| 类别 | 内容 |
|---|---|
| tools | `build`、`log_check`、`run_algorithm`、`static_diff`、`run_eval`、`kb_search`、`list_examples` |
| resources | `repo://docs/...`、`repo://prompts/...`、`repo://agents/...`、`repo://evals/...`、`repo://examples/...`（只读，越界路径拒绝） |
| prompts | `prompts/*.md`（编码规则、硬件约束、项目上下文） |

服务端与客户端都是**手写实现、零第三方依赖**（`mcp/protocol.py` 只做 JSON-RPC 2.0 与
`Content-Length` 分帧），保证 CI 与离线 demo 行为一致。
`runtime/mcp_bridge.py` 的 `McpToolExecutor` 与本地 `ToolExecutor` 方法名一一对应，
所以编排器只换一个开关：`--tool-layer mcp`。

### 检索层：项目内知识库（RAG）

规划不该靠"模型记忆"，而该靠**仓库里的证据**：历史故障案例、编码规则、硬件约束、评测阈值。
`kb_search` 把这些文本切成可回溯的块（`path#L12-L17`），用 BM25 检索（中文按二元组切，
不依赖分词器），返回带引用与片段的命中结果；编排器在规划前检索一次，把命中片段作为
`knowledge` 交给 Planner，并写入 `trace.jsonl`——**方案引用的每条经验都能查到出处**。

检索质量用 `evals/rag_cases.yaml` 度量：15 条查询 → `recall@3 = 1.0`、`MRR = 0.87`。

## 4. 快速开始

无需第三方依赖（仅 Python 标准库）：

```bash
git clone <this-repo> && cd agentic-embedded-workflow
python tools/eval_runner.py --cases evals/test_cases.yaml --expected evals/expected_results.yaml
```

报告输出到 `evals/report.md` 与 `evals/report.json`。

单独使用某个工具：

```bash
python tools/log_parser.py examples/adc_sampling_bug/input/serial.log --rules evals/log_rules.yaml
python tools/test_runner.py --cmd "python examples/motor_control/scripts/estimate_axis.py examples/motor_control/input/six_pulse_samples.csv"
python tools/git_diff_check.py --rules prompts/coding_rules.md --diff samples/sample.diff
python tools/build.py --config configs/keil.example.json

# 工具层与知识库
python tools/mcp_call.py --check                                     # MCP 一致性自检（7 tools / 32 resources / 3 prompts）
python tools/kb_build.py                                             # 重建知识库索引
python tools/kb_query.py --query "ADC 采样窗口 振铃" --k 3            # 带引用的检索
python tools/kb_query.py --cases evals/rag_cases.yaml --k 3          # 检索质量评测

# 编排器：换工具层 / 关掉知识库
python -m runtime.orchestrator --task tasks/adc_sampling_fix.json --tool-layer mcp
python -m runtime.orchestrator --task tasks/adc_sampling_fix.json --no-kb
```

## 5. 评测方法（核心）

评测不看"模型回答得好不好"，而看**工程是否通过验收**。分八层：

| 层级 | 看什么 | 自动化 |
|---|---|---|
| compile | 是否编译通过、warning 数量 | 是 |
| unit | 单元/脚本测试通过率 | 是 |
| static | 是否引入接口/变量/边界问题 | 是 |
| log | 指定状态是否出现、错误码是否消失 | 是 |
| algorithm | MAE / RMSE / P95 等误差指标 | 是 |
| hardware | PWM/ADC/Encoder 是否达到目标 | 否（人工填） |
| regression | 修 Bug 后旧功能是否仍通过 | 是 |
| agent | 首次成功率、迭代轮数、人工修改次数 | 半自动 |
| rag | 检索质量：期望文档是否在前 k 条（recall@3 / MRR） | 是 |
| mcp | 工具层一致性：握手、工具目录、资源、提示词与真实调用 | 是 |

`automated: true` 的用例由 `eval_runner.py` 直接执行；`automated: false` 的用例
（实机层）从 `evals/runs/<case-id>.json` 读取**人工填写**的结果，缺失就记为 `PENDING`——
不猜、不编造。

详见 [docs/eval-methodology.md](docs/eval-methodology.md)。

## 6. 诚实边界

- 本仓库当前是**单 Agent + 多角色**（同一 Agent 依次承担 Planner/Developer/Tester/Reviewer）。
  **不**声称是 Multi-Agent System。只有当每个角色拥有独立上下文、独立工具与独立任务、并由
  orchestrator 协调时，才升级为 *Multi-Agent Engineering Workflow*。
- 默认的 `StubRuntime` **不是 LLM**，它是用来验证编排与评测正确性的确定性实现；
  `OpenAIRuntime` 未在本仓库的 demo/CI 中运行过，首次使用前请对照官方文档核对。
- 实机层（hardware）无法自动判定，必须由人填写；工具只负责记录与汇总。
- 本仓库不提供"AI 让 MAE 变成 X"的因果结论；所有指标都是**工程结果**，AI 工作流只是被使用的手段。
- MCP 服务是**手写实现**，只覆盖本项目实际用到的子集（tools/resources/prompts、stdio 传输）；
  未接入官方 SDK，也未做多客户端并发与鉴权——这两点在企业环境需要补齐。
- RAG 是**词法检索**（BM25 + 中文二元组），不是向量检索；没有 embedding 模型，
  因此"同义改写"的召回有限。检索质量以 `recall@3 / MRR` 在 `evals/rag_cases.yaml` 上度量，
  不用"感觉变准了"下结论。
- 任意脚本执行（`run_script`）**故意不通过 MCP 暴露**：协议边界只承载工程动作，
  远程客户端无法要求本仓库执行任意路径。实机结论仍只能由人填写 `evals/runs/<case>.json`。

## 7. 案例来源

`examples/` 中的案例来自真实的嵌入式/机电项目（STM32H743 电机控制、ADC/编码器调试、
谐波减速器摩擦前馈补偿、PMSM 六脉冲初始位置辨识）。为便于公开，日志与数据为
**同结构脱敏/合成**样本，方法、断言与失败模式均为真实。

`examples/adc_sampling_bug/sim/` 与 `fixtures/` 是**明确标注的仿真夹具/测试夹具**：
它们让编排器的软件闭环可以离线复现，**不代表真实硬件测量**。实机记录请写入
`evals/runs/<case-id>.json`（`operator: human`）。

## 8. License

MIT，见 [LICENSE](LICENSE)。
