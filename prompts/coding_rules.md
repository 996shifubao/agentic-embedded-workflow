# 工程编码约束（Agent 必须遵守）

这些是**会被 `tools/git_diff_check.py` 检查**的硬规则子集。

## 硬规则

| id | 规则 | 检查方式 |
|---|---|---|
| CR-001 | 中断/回调中禁止 `delay`/`sleep`/阻塞等待 | diff 正则 |
| CR-002 | 中断与主循环共享的变量必须 `volatile` | diff 正则 |
| CR-003 | 禁止魔法数：定时器周期、阈值、量程必须具名常量 | diff 正则（数值字面量白名单 0/1） |
| CR-004 | 浮点运算不得出现在高频中断路径 | diff 正则 |
| CR-005 | 新增外设配置必须写注释说明寄存器依据 | 人工 + review |
| CR-006 | 不得提交调试专用 `printf` 到高频路径 | diff 正则 |
| CR-007 | MATLAB/Python 脚本必须可直接运行（含 `if __name__` 入口） | 运行 |
| CR-008 | 提交信息格式：`<module>: <what> (<why>)` | `git log` |

## 软规则（Review 时看）

- 命名：`Module_Action` 风格，单位写进变量名（`_us`、`_ma`、`_deg`）。
- 每个 `done_criteria` 都要能追到一条断言或一条人工记录。
- 新增行为要附带最小复现数据（CSV/日志片段）。
