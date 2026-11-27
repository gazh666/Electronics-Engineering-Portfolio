# 29 第三阶段最终验收报告（真实 CALCE 数据）

本报告汇总第三阶段全部真实运行结果。所有数值来自 `results/` 下已保存的运行记录；
未达标项保留 `FAIL`，无真实数据的项目保留 `NOT_VERIFIED`。

- 综合验收运行：`results/stage3/run_stage3_20261126_132618_219953/acceptance.json`
- 最新辨识运行：`results/identification/run_identification_20261126_131901_fb66db/`
- 最新验证运行：`results/dynamic_validation/run_dynamic_validation_20261126_131720_0e4677/`
- 数据来源：CALCE 公开数据，INR18650-20R，25 ℃，**不是本人硬件实测**

## 1. 专业原理与公式推导（含单位）

端电压由 OCV、欧姆压降与 RC 极化组成：

```text
V_t = OCV(SOC) − I·R0 − Σ_i V_i
V_i,k+1 = V_i,k·exp(−Δt/τ_i) + I_k·R_i·(1 − exp(−Δt/τ_i))
SOC_{k+1} = SOC_k − I_k·Δt/(3600Q)
```

| 量 | 含义 | 单位 |
| --- | --- | --- |
| `V_t` | 端电压 | V |
| `OCV` | 开路电压 | V |
| `I` | 归一化电流（放电为正） | A |
| `R0` | 欧姆内阻 | Ω |
| `R_i/C_i/τ_i` | 极化电阻/电容/时间常数 | Ω / F / s |
| `Q` | 实测容量 | Ah |
| `Δt` | 采样间隔 | s |
| `SOC` | 荷电状态 | 1 |

辨识在 DST 50% 上完成，参数冻结后在 FUDS 上开环验证；实现一致性由真实 ngspice 交叉校核。
公式推导、参数物理意义与单位分别见 docs/21–28。

## 2. 验收标准与结果

### A. 数学与数据正确性

| 检查 | 结果 | 判定 |
| --- | --- | --- |
| 容量积分与文件记录差 | 1.996×10⁻⁵ Ah（阈值 1×10⁻³） | PASS |
| SOC 符号（放电为正） | 回归测试 + 归一化校验 | PASS |
| OCV 查表覆盖 | [0.0, 1.0]，禁止外推 | PASS |
| RC 状态更新 | 解析解对照 < 10⁻¹² V | PASS |
| 正参数约束 | 构造期拒绝非正/非有限 | PASS |
| 数据泄漏 | 训练/开发/验证分离；验证不调参 | PASS |
| 无依据状态修正 | 验证 `stop_on_limits=False`，无逐点修正 | PASS |

### B. 参数辨识质量

| 检查 | 结果 | 判定 |
| --- | --- | --- |
| 优化器状态记录 | `optimization_trials.csv`、`parameter_quality.json` | PASS |
| 参数有限且为正 | 全部满足 | PASS |
| 边界报告 | 二阶 τ2=100.0 s 触下界 → `BOUND_LIMITED` | PASS（如实标记） |
| 多初值一致性 | 一阶一致；二阶 R2 离散 46.7%、τ2 202.9% → 弱可辨识 | PASS（如实标记） |
| 参数来源 | 全部来自真实 DST 数据 | PASS |

### C. 真实独立工况验证（预先登记：RMSE ≤ 30 mV、MAE ≤ 25 mV、Max ≤ 100 mV）

| 检查 | 结果 | 判定 |
| --- | --- | --- |
| FUDS 最大 RMSE | 28.45 mV | PASS |
| FUDS 最大 MAE | 21.97 mV | PASS |
| FUDS 最大瞬时误差 | 375.84 mV | **FAIL** |
| 整体 | 保留 `FAIL` | **FAIL** |

### D. SPICE 实现一致性（目标 ≤ 1 mV）

| 模型 | Python vs ngspice 最大差 | 判定 |
| --- | --- | --- |
| Rint | 0.0000 mV | PASS |
| 一阶 RC | 0.001247 mV | PASS |
| 二阶 RC | 0.001600 mV | PASS |

**综合验收：FAIL**（唯一失败项为 FUDS 空电区最大瞬时误差；其余检查通过）。

## 3. 核心结果对照表

| 模型 | R0 | R1 | C1 | R2 | C2 | tau1 | tau2 | DST训练RMSE | 独立验证RMSE |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Rint | 88.43 mΩ | N/A | N/A | N/A | N/A | N/A | N/A | 28.83 mV | 26.70 mV |
| 一阶 RC | 77.07 mΩ | 22.84 mΩ | 788.6 F | N/A | N/A | 18.02 s | N/A | 25.99 mV | 22.38 mV |
| 二阶 RC | 75.86 mΩ | 18.25 mΩ | 638.0 F | 7.38 mΩ | 13555.6 F | 11.64 s | 100.0 s | 25.94 mV | 22.18 mV |

（独立验证 RMSE 为 FUDS 50%/80% 平均；无条件支路使用 N/A，不用 0 冒充。）

## 4. 实际结果：关键真实数据

| 项目 | 数值 |
| --- | --- |
| 公开实验文件 | 9 个 |
| 电芯 | INR18650-20R，样品 SP1/SP2/SP3 |
| 温度 | 仅 25 ℃ |
| 实测容量 | SP2 2.028083 Ah；SP1 2.009165 Ah |
| OCV 实测点 | 147659 → 201 点查表 |
| OCV 覆盖 | SOC 0–1（共同区间 0–0.89） |
| 最大迟滞 | 129 mV @ SOC 0.87 |
| 跨样品 OCV | 平均 6.36 mV，最大 23.23 mV |
| 增量 OCV | 22 段仅 1 段通过 → NOT_VERIFIED |
| 有效 R0 样本 | 281（DST50）+ 446（DST80）= 727 |
| 表观 R0 | 71.56 / 71.61 mΩ（1 s 窗口） |
| 静置二阶拟合 | RMSE 0.318 / 0.243 mV；τ2 2245 / 1583 s |
| FUDS MAE | 12.03–21.97 mV |
| FUDS RMSE | 21.73–28.45 mV |
| 最大瞬时误差 | 375.84 mV（SOC 1.1–1.5%，4 A） |
| P95 绝对误差 | 33.14–49.71 mV |
| 额外工况 | US06 51.10–53.60 mV；BJDST 40.65–48.91 mV |
| SPICE 一致性 | 0.0016 mV |
| 3S1P | 11.1645 → 11.1195 V，压差 0.000 mV |
| 温度 | NOT_VERIFIED |
| 测试 | 168 passed |
| 模型运行时间 | 24.4 s（复用冻结模型，未重跑优化器） |

## 5. 工程图表（23 项）

| 编号 | 图表 | 实际文件（相对 run 目录） | 状态 |
| --- | --- | --- | --- |
| 1 | 原始容量实验曲线 | `capacity/plots/sp2_discharge_voltage_current.png` | 已生成 |
| 2 | 容量积分结果 | `capacity/plots/sp2_capacity_integration.png` | 已生成 |
| 3 | SOC 参考轨迹 | `identification/plots/03_soc_reference_trajectory.png` | 已生成 |
| 4 | 低电流充电 OCV | `ocv/plots/04_low_current_charge_ocv.png` | 已生成 |
| 5 | 低电流放电 OCV | `ocv/plots/05_low_current_discharge_ocv.png` | 已生成 |
| 6 | 增量 OCV 静置点 | `ocv/plots/06b_incremental_ocv_points.png` | 已生成（质量标注） |
| 7 | OCV 查表插值 | `ocv/plots/07_ocv_table_interpolation.png` | 已生成 |
| 8 | 充放电迟滞 | `ocv/plots/08_ocv_hysteresis.png` | 已生成 |
| 9 | 电流阶跃局部波形 | `pulse_identification/plots/09_current_step_zoom_*.png` | 已生成 |
| 10 | R0 分布 | `pulse_identification/plots/11_r0_histogram_*.png` | 已生成 |
| 11 | R0-SOC | `pulse_identification/plots/10_r0_vs_soc_*.png` | 已生成 |
| 12 | 一阶 RC 静置拟合 | `pulse_identification/plots/12_relaxation_fit_1order_*.png` | 已生成 |
| 13 | 二阶 RC 静置拟合 | `pulse_identification/plots/13_relaxation_fit_2order_*.png` | 已生成 |
| 14 | 快慢极化分量 | `identification/plots/14_polarization_components.png` | 已生成 |
| 15 | DST 训练电流及电压 | `identification/plots/15b_dst_training_current_voltage.png` | 已生成（双轴） |
| 16 | DST 训练残差 | `identification/plots/16_dst_training_residual.png` | 已生成 |
| 17 | FUDS 电压对照 | `dynamic_validation/plots/17_18_fuds_*_voltage.png` | 已生成 |
| 18 | FUDS 残差 | `dynamic_validation/plots/18_residual_fuds_*.png` | 已生成 |
| 19 | 三模型 RMSE 对照 | `dynamic_validation/plots/19_validation_rmse_comparison.png` | 已生成 |
| 20 | 各 SOC 区间误差 | `dynamic_validation/plots/20_soc_bucket_rmse_*.png` | 已生成 |
| 21 | 温度-参数关系 | — | `NOT_VERIFIED`，无 0/45 ℃ 数据，不画假曲线 |
| 22 | Python/SPICE 对照 | `identified_spice/plots/22_python_spice_*.png` | 已生成 |
| 23 | 3S 单体/组端电压 | `identified_spice/plots/23_3s_pack_voltage.png`、`23b_3s_individual_cell_voltage.png` | 已生成 |

每张图注均包含数据来源、实验条件、模型类型、Run ID、原始文件、单位与训练/验证角色。

## 6. 测试体系

| 类别 | 覆盖 |
| --- | --- |
| 基础数学 | 容量积分、符号、SOC 积分、OCV 插值、R0、单/双指数恢复、RC 单位、RMSE/MAE |
| 异常边界 | 无效脉冲、小电流、重复时间、时间缺口、缺失数据、非有限参数、不合理电阻/时间常数、优化失败状态、触界、弱可辨识、初始 SOC 未知、验证重复使用、预测提前终止、评价区间不一致 |
| 真实集成 | CALCE 容量/OCV 解析、真实动态工况、真实辨识、真实独立验证、真实 ngspice |

新增 `tests/test_stage3_edge_cases.py`（8 项）。全量：**168 passed**。

## 7. 已知局限与未验证事项

1. 仅 25 ℃，温度特性 `NOT_VERIFIED`；
2. OCV 与动态数据来自不同样品，属跨样品参考模型；
3. 二阶 RC 的 τ2 触下界，第二个时间常数不可辨识；
4. FUDS 最大瞬时误差 375.84 mV 超标，空电区大电流预测不可靠；
5. 3S 均匀参数不能证明均衡算法；
6. 未开发 EKF/AFE/保护电路，参数辨识不等于 BMS 硬件验证；
7. 公开数据不是本人实测。

## 8. 实际文件路径、实际类与函数、关键源码与运行命令

### 实际类与函数

| 名称 | 作用 |
| --- | --- |
| `IdentifiedECMParameters` | 参数数据结构与构造期校验 |
| `run_open_loop_validation` | 冻结参数开环验证 |
| `multi_start_fit` | 多初值最小二乘 |
| `freeze_model / load_frozen_model` | 参数冻结与只读加载 |
| `simulate_ecm` | 统一零阶保持求解器 |

### 实际文件路径

| 内容 | 路径 |
| --- | --- |
| 容量 | `identification/capacity_estimator.py` |
| OCV | `identification/ocv_extractor.py`、`battery_models/ocv_model.py` |
| 脉冲/R0 | `identification/pulse_detector.py`、`resistance_estimator.py` |
| 静置拟合 | `identification/relaxation_fitter.py` |
| 动态辨识 | `identification/ecm_fitter.py` |
| 验证 | `validation/dynamic_validation.py` |
| SPICE/3S | `simulations/spice_battery_runner.py`、`battery_models/battery_pack.py` |

```powershell
cd "BatteryLab"
conda run -n kaifa_battery python -m scripts.capacity_analysis_demo
conda run -n kaifa_battery python -m scripts.ocv_extraction_demo
conda run -n kaifa_battery python -m scripts.pulse_identification_demo
conda run -n kaifa_battery python -m scripts.ecm_identification_demo
conda run -n kaifa_battery python -m scripts.dynamic_validation_demo
conda run -n kaifa_battery python -m scripts.temperature_analysis_demo
conda run -n kaifa_battery python -m scripts.identified_spice_demo
conda run -n kaifa_battery python -m scripts.battery_stage3_demo --profile standard
conda run -n kaifa_battery python -m pytest tests -v
conda run -n kaifa_battery python -m pip check
```

## 9. 结论

1. 用 CALCE 真实公开数据完成了“容量 → OCV → R0 → RC → 动态辨识 → 独立验证 → SPICE → 3S → BMS 参考”的完整链路；
2. 一阶 RC 是当前数据下最可信、可解释的模型；二阶 RC 的慢时间常数不可辨识；
3. RMSE/MAE 达标，但最大瞬时误差超标，整体验收保留 **FAIL**；
4. 温度特性与充电方向内阻压升保留 `NOT_VERIFIED`；
5. 所有“实测”均指 CALCE 公开数据，不是本人硬件实测；跨样品与单温度限制已写入全部文档。

## 10. 学习练习

1. 用 `validation_summary.csv` 复算三模型 FUDS 平均 RMSE；
2. 找出 375.84 mV 对应的时刻、SOC 与电流，解释为什么模型在此处失效；
3. 设计一个只增加一次真实实验就能显著降低最大误差的方案，并说明预算。

## 11. 面试题（示例）

1. 为什么额定容量不等于实际容量？
2. 为什么端电压不等于 OCV？
3. 如何从实验提取 OCV-SOC 曲线？
4. 什么是充放电迟滞？
5. 为什么内阻随 SOC 与温度变化？
6. 如何由脉冲实验估计 R0？
7. 如何通过指数恢复辨识 RC 时间常数？
8. 为什么最小二乘可用于电池模型辨识？
9. 为什么二阶 RC 不一定比一阶 RC 准确？
10. 为什么训练误差与独立验证误差必须区分？
