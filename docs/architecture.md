# 架构说明

## 1. 闭环的每一段

| 阶段 | 谁执行 | 输入 | 输出 | 工具 |
|---|---|---|---|---|
| Planner / Analysis | Agent | 需求/Bug/实验目标 + 代码库 | 任务列表、调用链、风险点、验收标准 | 文件读取、搜索、`git log` |
| Implementation | Agent | 任务列表 | 跨文件代码修改 | 文件编辑 |
| Tool Execution | Agent | 修改后的仓库 | 构建/测试/日志结果（JSON） | `tools/build.py`、`tools/test_runner.py`、`tools/log_parser.py`、`tools/git_diff_check.py` |
| Software Validation | Agent | 工具结果 | 通过/失败/证据 | `tools/eval_runner.py` |
| Physical Validation | **人** | 固件、测试条件 | 波形截图、串口日志、现象 | 烧录器、示波器、逻辑分析仪 |
| Feedback | 人 → Agent | 实机结果 | 新一轮任务 | `evals/runs/<case-id>.json` |
| Review / Iteration | Agent | 失败证据 | 归因 + 修改方案 | `agents/reviewer.md` |
| Git / Docs | Agent | 通过验证的改动 | 分阶段提交 + 记录 | `git` |

## 2. 为什么把"物理段"显式建模

Agent 不能读示波器，但可以读**由人转写后的结构化证据**。把实机结果写成
JSON（而不是截图），Agent 才能参与归因。`evals/runs/<case-id>.json` 就是这个接口：

```json
{
  "case_id": "pwm-issue-hardware",
  "operator": "human",
  "timestamp": "2026-01-01T10:00:00+08:00",
  "measured": {
    "pwm_input_ok": true,
    "pwm_output_ok": true,
    "reason_if_failed": ""
  },
  "attachments": ["scope_in.png", "scope_out.png"],
  "notes": "热风返修 QFN 后输出恢复"
}
```

人的职责不是"打勾"，而是提供**可被机器判定的证据**。

## 3. 交接契约

角色之间不靠自然语言长文交接，而靠固定字段，避免信息在传递中丢失：

```json
{
  "task_id": "adc-001",
  "goal": "把 ADC 采样窗口移出开关振铃区",
  "done_criteria": ["zero_offset_calibrated=true", "no ERR_ADC_TRIG", "hardware: adc_rms < 5 LSB"],
  "evidence": ["evals/report.json"],
  "blocked_by": [],
  "next_owner": "tester"
}
```

## 4. 与纯软件 Agent 的差异

| 维度 | 纯软件 | 本项目 |
|---|---|---|
| 验证 | 编译 + 测试 | 编译 + 测试 + **实机** |
| 失败信号 | 堆栈/断言 | 堆栈 + **波形/日志/现象** |
| 迭代成本 | 秒级 | 分钟级（烧录/上电） |
| 危险动作 | 数据丢失 | 烧板、堵转、过流 |
| 因此需要 | 测试套件 | 测试套件 + **安全检查 + 人在环确认** |
