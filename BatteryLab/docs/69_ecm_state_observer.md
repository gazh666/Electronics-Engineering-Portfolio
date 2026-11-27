# 69 ECM 端电压残差反馈观测器（不是 EKF）

日期：2026-11-26
对应源码：`estimation/ecm_observer.py:58`（`ECMObserver`）
配置：`configs/observer_config.yaml`

## 1. 结构

```text
SOC_pred = 安时积分(SOC_k, I_k, Δt)
Vp_i,k+1 = Vp_i,k · e^{-Δt/τ_i} + I_k · R_i · (1 - e^{-Δt/τ_i})
V_pred   = OCV(SOC_pred) - R0 · I_{k+1} - Σ Vp_i,k+1
residual = V_meas - V_pred
ΔSOC     = -expm1(-Δt/τ_c) · residual / (dOCV/dSOC)
|ΔSOC|   ≤ maximum_correction_rate · Δt
SOC_corr = clip(SOC_pred + ΔSOC, 0, 1)
```

参数（`configs/observer_config.yaml`）：

| 参数 | 值 |
| --- | --- |
| R0 | 冻结模型 `r0_ohm` |
| RC 支路 | 1 条：`r1_ohm`, `tau1_s` |
| τ_c | 120 s |
| 最小 OCV 斜率 | 0.2 V/SOC |
| 最大校正速率 | 0.001 SOC/s |
| 残差门限 | 0.35 V |
| 电流阶跃门限 | 0.5 A |
| 初始极化 | 0 V（假设实验前已静置） |

## 2. 为什么不是 EKF

| EKF 要素 | 本实现 |
| --- | --- |
| 状态协方差 P | 无 |
| 过程噪声 Q | 无 |
| 测量噪声 R | 无 |
| 卡尔曼增益 K = P Hᵀ (H P Hᵀ + R)⁻¹ | 无 |
| 协方差传播 | 无 |
| 增益 | 固定时间常数 τ_c 的一阶滤波 |

因此文档、报告、代码注释一律称"固定增益/固定时间常数残差反馈观测器"，
**禁止称 EKF 或最优估计器**。

## 3. 门控顺序（决定 status）

| 顺序 | 条件 | 状态 |
| --- | --- | --- |
| 1 | SOC 积分触限 | `SOC_BOUND_REACHED` |
| 2 | `allow_voltage_correction=False` | `PREDICT_ONLY` |
| 3 | `slope < 0.2` | `LOW_OBSERVABILITY` |
| 4 | `|residual| > 0.35 V` | `RESIDUAL_GATED` |
| 5 | `|I_k+1 − I_k| > 0.5 A` | `CURRENT_STEP_HOLD` |
| 6 | 通过全部门控 | `VOLTAGE_CORRECTED` |

门控的意义：宁可只做电流预测，也不要用模型明显解释不了的残差去修正 SOC。

## 4. 独立工况结果

运行：`results/stage7/run_stage7_20261126_162211_3590e5`（`soc_method_comparison.csv`）

| 数据集 | MAE pp | RMSE pp | 最大误差 pp | 覆盖率 |
| --- | --- | --- | --- | --- |
| us06_50 | 1.483 | 1.729 | 3.051 | 1.000 |
| us06_80 | 1.811 | 1.957 | 3.004 | 1.000 |
| bjdst_50 | 1.418 | 1.609 | 2.933 | 1.000 |
| bjdst_80 | 1.806 | 2.003 | 3.087 | 1.000 |

全部满足预登记目标：RMSE ≤3 pp、最大误差 ≤5 pp、覆盖率 ≥99%。

端电压预测（us06_50，运行 `soc_estimation_20261126_161649_fe98d0`）：
RMSE 约 0.03 V 量级（详见该运行 `observer_metrics.json` 的 `voltage_prediction`），
残差大多数落在 ±0.35 V 门限内。

## 5. 初始 SOC 收敛

同一次标准运行（`initial_soc_experiments.csv`）：

| 初始误差 | 收敛状态 | 耗时 s | 收敛后最大误差 pp |
| --- | --- | --- | --- |
| −20 pp | CONVERGED | 1579.2 | 3.051 |
| −10 pp | CONVERGED | 808.7 | 3.051 |
| 0 pp | CONVERGED | 60.3 | 3.051 |
| +10 pp | CONVERGED | 254.9 | 3.051 |
| +20 pp | CONVERGED | 479.6 | 3.051 |

判据是"|误差| ≤2 pp 连续 60 s"。注意"收敛后最大误差"仍可能回到 3.05 pp，
说明 2 pp 只是首次保持判据，不是永久上界。

负偏差收敛更慢（−20 pp 需约 26 min），因为残差反馈还要对抗模型偏差。

## 6. 参数失配的实测趋势（us06_50）

运行 `model_mismatch_results.csv`：

| R0 偏差 | RMSE pp | 终值 pp |
| --- | --- | --- |
| −20% | 3.139 | 1.443 |
| −10% | 2.437 | 1.494 |
| 0% | 1.729 | 1.559 |
| +10% | 1.136 | 1.617 |
| +20% | 0.927 | 1.678 |

本数据集上增大 R0 反而降低 SOC 误差，说明冻结 R0 相对该工况的等效欧姆压降
偏小。这是**观测到的现象**，不能据此回调 R0；否则就是用测试集调参。

OCV 偏移 ±10 mV 使 RMSE 从 1.09 变到 3.75 pp，再次说明平台区可观测性差。

## 7. 设计取舍

| 取舍 | 选择 | 理由 |
| --- | --- | --- |
| 初始极化 | 0 V | 实验前满充静置；若否则必须重新初始化并标注 |
| 修正量限幅 | 0.001 SOC/s | 防止残差被模型误差放大 |
| 电流阶跃后暂停 | 5 s 等效（按门限实现） | 阶跃瞬间 RC 未更新，残差不可信 |
| 修正后重算电压 | 只用于后验展示 | 不得与一步预测误差混用 |

## 8. 常见错误

1. 把残差反馈写成 EKF，并声称"最优"。
2. 电流阶跃瞬间用旧极化电压计算残差并强修正。
3. 平台区仍强校正，导致 SOC 跳变。
4. 用修正后的电压计算"预测误差"，人为降低误差。

## 9. 运行命令

```bash
conda run -n kaifa_battery python -m scripts.ecm_observer_demo
conda run -n kaifa_battery python -m pytest tests/test_ecm_observer.py -q
```

## 10. 练习与面试题

练习：

1. 把 τ_c 从 120 s 改为 30 s，观察初始 ±20 pp 收敛时间与超调。
2. 把残差门限从 0.35 V 改为 2 V，观察平台区是否出现 SOC 跳变。

面试题：

1. 本观测器与 EKF 的数学结构差在哪三处？
2. 为什么电流阶跃后要暂停电压修正？
3. 收敛判据"连续 60 s"为什么不能保证之后不再越界？
