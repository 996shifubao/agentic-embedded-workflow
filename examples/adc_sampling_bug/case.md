# 案例：ADC 采样窗口落在开关振铃区

## 现象

- PWM 频率 40 kHz、中心对齐，死区约 350 ns。
- ADC 由 `tim1_trgo` 触发，采样点在 PWM 周期约 12.5%（`sample_offset_us=5.0`）。
- 串口统计中 `adc_rms` 约 23 LSB，且反复出现 `ERR_ADC_TRIG`。

## 归因

采样窗口落在功率级开关振铃区，采样值未建立（`adc_settled=false`），
并且触发发生在开关瞬间，产生虚假触发。

## 修复

把采样点后移到周期约 30%（`sample_offset_us=12.0`），并重新校准零偏。

## 证据

| 文件 | 含义 |
|---|---|
| `input/serial_before.log` | 复现：`adc_settled=false`、`ERR_ADC_TRIG`、`adc_rms=23` |
| `input/serial_after.log` | 修复后：`adc_settled=true`、无 `ERR_ADC_TRIG`、`adc_rms=3` |

## 对应评测

- `adc-001-repro-log`（断言 Bug 可复现）
- `adc-002-fixed-log`（断言修复后通过）
- `adc-003-hardware`（人工：限流电源 + 串口统计确认有效位）

> 说明：日志为便于公开的**同结构合成样本**，故障模式与断言均来自真实调试过程。
