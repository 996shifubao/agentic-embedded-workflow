# 案例：UCC20225 输入 PWM 正常、输出无波形

## 现象

- 驱动方案由 FD6288Q 改为 UCC20225 后首次上电。
- 示波器测 MCU 侧输入：40 kHz、占空比正常（`pwm_input_ok=true`）。
- 测驱动输出（相 A）：无波形（`pwm_output_ok=false`），日志反复报 `ERR_DRV`。

## 排查顺序（收敛范围）

1. 确认 PWM 输入存在 → 排除 MCU 侧与定时器配置。
2. 确认供电与使能引脚 → 排除电源与逻辑使能。
3. 检查驱动级焊接 → 热风返修 QFN 后输出恢复。

## 结论

焊接不良（QFN 存在冷焊），不是控制逻辑问题。

## 证据

| 文件 | 含义 |
|---|---|
| `input/serial_before.log` | 复现：`pwm_input_ok=true` + `pwm_output_ok=false` + `ERR_DRV` |
| `input/serial_after.log` | 返修后：`pwm_output_ok=true`、输出频率 40 kHz、无 `ERR_DRV` |

## 对应评测

- `pwm-001-repro-log` / `pwm-002-fixed-log`（日志层）
- `pwm-003-hardware`（人工：示波器确认相 A 输出，写入 `evals/runs/pwm-003-hardware.json`）

## 为什么这条适合做 Harness 案例

它体现了"软件层全绿但硬件层失败"的典型情形：
编译通过、日志正常，但物理输出为 0。**这正是必须保留人工验证层的原因。**
