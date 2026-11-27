# 第七阶段工程证据表（SOC / SOH）

日期：2026-11-26
环境：Conda `kaifa_battery` / Python 3.11.18 / PySpice 1.5 / ngspice 34
标准运行：`results/stage7/run_stage7_20261126_162211_3590e5`

类型标签：

- `public_data`：公开实验数据；
- `derived_reference`：由真实电流推导的参考量；
- `synthetic_truth`：合成真值；
- `spice`：电路仿真；
- `behavioral`：行为级数学仿真；
- `hardware`：硬件实测（本阶段无）。

## 1. 核心指标

| 指标 | 数值 | 单位 | 工况 | 数据/来源 | Run ID | 证据文件 | 验证状态 | 类型 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SOC RMSE（ECM） | 1.729 | pp | us06_50, 25℃ | CALCE SP2 | `stage7_20261126_162211_3590e5` | `soc_method_comparison.csv` | PASS | public_data |
| SOC 最大误差（ECM） | 3.051 | pp | us06_50 | CALCE SP2 | 同上 | 同上 | PASS | public_data |
| SOC RMSE（ECM） | 2.003 | pp | bjdst_80 | CALCE SP2 | 同上 | 同上 | PASS | public_data |
| 覆盖率（4 工况） | 1.000 | 1 | us06/bjdst | CALCE SP2 | 同上 | 同上 | PASS | public_data |
| 端电压查表 RMSE | 12.778 | pp | us06_50 | CALCE SP2 | 同上 | 同上 | BASELINE_LIMITATION | public_data |
| 静置校正次数 | 0 | 次 | dst_50/us06_50 | CALCE SP2 | `soc_estimation_20261126_161725_90c158` | `correction_metrics.json` | PASS（条件不满足） | public_data |
| 合成夹具最终误差 | −0.019 | pp | 放电600s+静置1800s | 冻结 ECM | 同上 | `correction_events.csv` | PASS | synthetic_truth |
| 初始 −20 pp 收敛耗时 | 1579.2 | s | us06_50 | 冻结 ECM | `stage7_20261126_162211_3590e5` | `initial_soc_experiments.csv` | PASS | behavioral |
| 初始 +20 pp 收敛耗时 | 479.6 | s | us06_50 | 冻结 ECM | 同上 | 同上 | PASS | behavioral |
| 恒流 SOC 积分误差 | 5.55e-17 | 1 | 1 A × 3600 s | 数学 | 同上 | `validation_summary.json` | PASS | synthetic_truth |
| 容量积分误差 | 0 | Ah | 1 A × 3600 s | 数学 | 同上 | 同上 | PASS | synthetic_truth |

## 2. 传感器与 SPICE

| 指标 | 数值 | 单位 | 工况 | 数据/来源 | Run ID | 证据文件 | 验证状态 | 类型 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 失调 −20 mA 的 MAE | 0.923 | pp | us06_50 | 公开数据 + 人工扰动 | `soc_estimation_20261126_162035_01b72b` | `sensor_error_results.csv` | PASS | public_data + synthetic_sensor |
| 失调 +20 mA 的 MAE | 0.888 | pp | us06_50 | 同上 | 同上 | 同上 | PASS | public_data + synthetic_sensor |
| 增益 ±1% 的 MAE | 0.252 / 0.255 | pp | us06_50 | 同上 | 同上 | 同上 | PASS | public_data + synthetic_sensor |
| 噪声 10 mA 的 MAE | 0.0086 | pp | us06_50 | 同上 | 同上 | 同上 | PASS | public_data + synthetic_sensor |
| ADC 12 bit 的 MAE | 0.127 | pp | us06_50 | 同上 | 同上 | 同上 | PASS | public_data + synthetic_sensor |
| 零点校准（10 mA） | 0.453 → 0.019 | pp | us06_50 | 同上 | 同上 | `calibration_comparison.json` | PASS | behavioral |
| SPICE 求解次数 | 2 | 次 | 19.063 s 片段 | ngspice | `stage7_20261126_162211_3590e5` | `validation_summary.json` | PASS | spice |
| SPICE 区间电荷误差 | −0.00149 | % | us06_50 | ngspice | 同上 | 同上 | PASS | spice |
| SPICE 电流 RMSE | 0.470 | mA | us06_50 | ngspice | 同上 | 同上 | PASS | spice |

## 3. SOH 与电池组

| 指标 | 数值 | 单位 | 工况 | 数据/来源 | Run ID | 证据文件 | 验证状态 | 类型 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 真实积分容量 | 2.0280827046460144 | Ah | SP2 初始容量 | CALCE SP2 | `battery_health_20261126_161753_3e607b` | `capacity_soh_summary.json` | PASS | public_data |
| 与记录容量相对差 | 0.000984 | % | SP2 | CALCE SP2 | 同上 | 同上 | PASS | public_data |
| 合成 100 循环最终 SOH | 90.1 | % | 0.002 Ah/cycle | 合成 | 同上 | `cycle_capacity.csv` | PASS（数学） | synthetic_truth |
| 容量更新 | 2.000 → 1.996 | Ah | 会话边界 | 合成 | 同上 | `data_quality.json` | PASS（数学） | synthetic_truth |
| 真实表观 DCIR | 0.073274 | Ω | SOC 0.391, 25℃, 4.483 A | CALCE SP2 | `battery_health_20261126_161844_389769` | `resistance_health.csv` | PASS（单点） | public_data |
| 真实内阻增长率 | — | % | 无老化循环 | — | 同上 | `resistance_summary.json` | NOT_VERIFIED | hardware |
| 3S 忽略均衡误差 | 1.970 | pp | 40 mA, 1 h | 合成 3S | `stage7_20261126_161834_c31cbc` | `pack_soc_experiment.json` | PASS | synthetic_truth |
| 3S 计入均衡误差 | 0.000 | pp | 同上 | 合成 3S | 同上 | 同上 | PASS（实现一致性） | synthetic_truth |
| 3S 均衡估计 +20% 误差 | 0.394 | pp | 同上 | 合成 3S | 同上 | 同上 | PASS | synthetic_truth |

## 4. 充电

| 指标 | 数值 | 单位 | 工况 | 数据/来源 | Run ID | 证据文件 | 验证状态 | 类型 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 充电终止 SOC | 85.85 | % | CC-CV 12.15 V | 冻结 ECM | `soc_estimation_20261126_161855_6257d1` | `charging_summary.json` | PASS | behavioral |
| 充电时长 | 4634.5 | s | 同上 | 冻结 ECM | 同上 | 同上 | PASS | behavioral |
| 电流 +10 mA 的 RMSE | 0.366 | pp | 同上 | 冻结 ECM + 扰动 | 同上 | 同上 | PASS | behavioral |
| 初始 +10 pp 的 RMSE | 10.000 | pp | 同上 | 冻结 ECM | 同上 | 同上 | PASS（无反馈时保持） | behavioral |
| 是否强制 SOC=100% | 否 | — | 同上 | — | 同上 | 同上 | PASS | behavioral |

## 5. 明确不宣称的内容

1. 不宣称 SOC 绝对精度达到量产 BMS 规格；参考 SOC 是实验数据推导量。
2. 不宣称本观测器是 EKF 或与 BQ34Z100-R2 内部算法等价。
3. 不宣称 25℃ 结果覆盖 0/45℃。
4. 不宣称真实老化 SOH 或内阻增长。
5. 不宣称 19 s SPICE 回放等于数小时开关级联合仿真。
6. 不宣称合成 3S/充电实验是实测硬件结果。

## 6. 复现

见 `docs/76_stage7_validation.md` 第 12 节。
