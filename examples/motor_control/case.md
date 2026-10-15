# 案例：六脉冲二维电流增量 -> LS 连续轴线估计

## 背景

传统六脉冲法只取"电流增量最大"的那一路电压矢量，轴线估计被量化到 60° 网格；
目标是在不改变六脉冲注入流程的前提下，把六路响应连续化利用。

## 方法

对六个注入方向 `phi_k` 的响应 `s_k` 建立投影响应模型：

```
s_k = a + b*cos(2*phi_k) + c*sin(2*phi_k) + e_k
```

结构化最小二乘解出 `(a, b, c)`，再由

```
theta = 0.5 * atan2(c, b)      (mod 180 deg)
```

恢复轴线角；极性另由正/反脉冲下的磁饱和不对称性判定。

## 数据与指标

- 输入：`input/six_pulse_samples.csv`（8 个样本 × 6 个注入方向；为便于公开的**合成数据**）
- 指标：`mae_ls_deg`（本方法）与 `mae_maxch_deg`（最大通道基线）
- 阈值：`mae_deg_max`（见 `evals/expected_results.yaml`）

## 对应评测

- `motor-001-axis-estimation`：`status=PASS` 且 `metrics.mae_ls_deg <= mae_deg_max`，
  同时要求基线方法误差大于阈值（证明对比有意义）。

## 运行

```bash
python examples/motor_control/scripts/estimate_axis.py examples/motor_control/input/six_pulse_samples.csv
```
