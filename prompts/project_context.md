# 项目上下文（模板）

> Agent 每次开始工作前读这个文件。请按你的真实项目填写。

## 系统概览

- 目标系统：<例如：STM32H743 六电机控制板 / 桌面力反馈触觉设备>
- 关键外设：<TIM/ADC/SPI/UART/编码器/驱动芯片>
- 上位链路：<USB CDC / UART / UDP / SPI>
- 数据流向：<传感器 → MCU → 上位机 → 分析>

## 目录约定

| 路径 | 内容 |
|---|---|
| `firmware/` | MCU 固件（C/Keil/CMake） |
| `tools/` | 上位机与脚本（Python/MATLAB） |
| `evals/` | 用例与期望结果 |
| `docs/` | 接口与时序文档 |

## 已知陷阱（踩过的坑）

- <例：UCC20225 输入 PWM 正常但输出无波形 → 先查焊接与驱动级>
- <例：ADC 采样落在开关振铃区 → 采样窗口后移>

## 验收偏好

- 先跑 `compile → static → log → algorithm`，通过后才安排实机。
- 实机结果写入 `evals/runs/<case-id>.json`。
