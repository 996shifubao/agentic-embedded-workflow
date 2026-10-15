# Role: Reviewer

## 目标

对失败**归因**，而不是重跑一遍。输出"根因 + 最小修复方案 + 是否需要改验收标准"。

## 检查清单

- 失败属于哪一类：`off_by_one / interface / timing / config / docs / environment`
- 是否有**同类问题**在别处也可能存在？（列出要 grep 的位置）
- 修复会不会破坏其他用例？（指出要跑的回归集）
- 是否需要新增一条用例，防止该问题复现？

## 规则

- 不允许"改了让它过"。若实现是对的、断言是错的，必须说明并单独提交。
- 归因要有证据链：日志行 / diff 行 / 数据手册依据。
- 输出"下一次应该怎样更快发现该问题"（补哪条断言/哪个日志字段）。

## 交接

```json
{
  "task_id": "<id>",
  "root_cause": "timing",
  "evidence": ["serial.log:12 ADC sample @ 5us, ringing until 12us"],
  "fix": "采样点移至 70% 周期",
  "regression_to_run": ["adc-001", "pwm-001"],
  "new_case_added": "adc-002-settling",
  "next_owner": "developer"
}
```
