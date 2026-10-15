# 评测方法

## 1. 原则

1. **评测对象是工程产物，不是模型回答。** 通过与否由编译、测试、日志、实机验收决定。
2. **分层，便宜的先跑。** 编译失败就不必上实机。
3. **可判定。** 每条断言都要能被脚本或人给出 true/false，不接受"感觉好多了"。
4. **失败要留证。** 失败用例的日志、diff、实机记录都保留，供回归与归因。

## 2. 八层评测

| 层 | 判定方式 | 自动化 | 示例 |
|---|---|---|---|
| compile | 退出码 + warning 计数 | 是 | `build_ok=true, warnings<=2` |
| unit | 测试通过率 | 是 | `passed>=8/8` |
| static | 规则匹配 diff | 是 | 无裸 `delay_ms()` 于中断、无魔法数 |
| log | 关键词/正则/数值阈值 | 是 | `zero_offset_calibrated=true` |
| algorithm | 误差指标 | 是 | `mae_deg<=1.0` |
| hardware | 仪器/现象（人工填） | 否 | `pwm_output_ok=true` |
| regression | 旧用例是否仍通过 | 是 | 修复后原 6 条仍通过 |
| agent | 过程指标 | 半自动 | 首次成功率、迭代轮数 |
| rag | 检索质量：期望文档是否在前 k 条 | 是 | `recall@3>=0.9`, `MRR>=0.8` |
| mcp | 工具层一致性：握手/工具目录/资源/真实调用 | 是 | 7 tools、`log_check=PASS` |

后两层评测的是**工具链本身**：知识库检索不准或 MCP 服务接线断了，上层 Agent 的
结论就不可信，所以它们和工程指标一起纳入同一份报告（`evals/report.md`）。

## 3. Agent 过程指标

工程指标说明"结果对不对"，过程指标说明"Agent 有没有在变好"。
用 `evals/agent_metrics_template.csv` 逐任务记录：

```
task_id,agent_iterations,build_runs,test_runs,manual_edits,first_pass,human_minutes,failure_type
adc-001,3,4,3,1,false,45,off_by_one
pwm-001,2,2,1,0,true,20,
```

推荐统计：

- 首次成功率 = `first_pass=true` 的任务数 / 总任务数
- 平均迭代轮数 = `mean(agent_iterations)`
- 人工修改比例 = `manual_edits>0` 的任务数 / 总任务数
- 失败类型分布：`off_by_one / interface / timing / config / docs`

## 4. 与验收标准的绑定

`evals/test_cases.yaml` 的每条用例声明 `layer` 与 `expect`；
`evals/expected_results.yaml` 提供数值阈值。修改阈值必须同一次提交，
否则评测会退化成"迁就实现"。

## 5. 不做什么

- 不做 LLM-as-judge 打分当主指标（最多作为补充）。
- 不把"AI 参与"当作结果指标的因果解释。
- 不在缺少历史数据时声称"效率提升 X%"。
