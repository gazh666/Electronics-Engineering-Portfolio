# BatteryLab 第二阶段工程证据

- 生成日期：2026-11-26
- 综合验收运行：`stage2_20261126_123052_b15f65`
- 总体验收：**PASS**（9 项检查全部通过）
- 参数来源：`configs/ecm_parameters.yaml`、`configs/ocv_reference.yaml`，均为 `educational_assumption`

## 1. 工程指标与证据

| 工程指标 | 实际结果 | 单位 | 实际工况 | 数据来源 | Run ID | 原始证据 | 验证状态 | 局限 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R0 反算 | 0.030000 | Ω | 2A 接入阶跃，ΔI=2A | SPICE_DERIVED | `ecm_20261126_122858_dadfee` | `results/ecm/run_ecm_20261126_122858_dadfee/pulse_response_metrics.json` | PASS | 模型参数非实测辨识 |
| 瞬时压降 | 60.000 | mV | 0→2A 阶跃 | SPICE_DERIVED | `ecm_20261126_122858_dadfee` | 同上 | PASS | 采样 0.1 s |
| 一阶脉冲结束电压 | 3.702001 | V | 2A 60s，69.9s 采样 | custom_ecm_simulation | `ecm_20261126_122846_d4bb75` | `results/ecm/run_ecm_20261126_122846_d4bb75/waveform.csv` | PASS（解析误差 4.44e-16 V） | 固定 OCV 3.8 V |
| 二阶脉冲结束电压 | 3.683056 | V | 2A 60s，69.9s 采样 | custom_ecm_simulation | `ecm_20261126_122851_934617` | `results/ecm/run_ecm_20261126_122851_934617/waveform.csv` | PASS（解析误差 4.44e-16 V） | 固定 OCV 3.8 V |
| 60 s 解析参考（一阶/二阶） | 3.701991 / 3.683027 | V | 2A 60s | ANALYTICAL_THEORY | 同上 | `docs/11`、`docs/12` | PASS | 解析值 |
| 一阶恢复时间（±1mV） | 72.8 | s | 释放后 120 s 观察窗 | SPICE_DERIVED | `ecm_20261126_122846_d4bb75` | `summary.json` | PASS | 判据含容差与保持时间 |
| 二阶恢复 | NOT_RECOVERED | – | 释放后 120 s 观察窗 | SPICE_DERIVED | `ecm_20261126_122851_934617` | `summary.json` | NOT_RECOVERED（如实记录） | τ2=60 s，120 s 不足 |
| 60 s 脉冲 SOC | 0.583333333333 | – | 2A 60s，Q=2Ah | custom_ecm_simulation | `ecm_20261126_122857_cdbae7` | `waveform.csv` | PASS（误差 3.33e-13） | 效率取 1.0 |
| 脉冲能量平衡相对残差（一阶/二阶） | 8.0e-6 / 1.25e-5 | – | 10–70 s | custom_ecm_simulation | 上述两次运行 | `energy_balance.json` | PASS（≤1e-3） | 梯形积分 |
| 3S 开路组电压 | 11.400000 | V | 一致电芯，OCV 3.8 V | custom_ecm_simulation | `battery_pack_20261126_122903_614806` | `pack_waveform.csv` | PASS | 恒温、无均衡 |
| 3S 2A 接入组电压 | 11.220000 | V | 0→2A | custom_ecm_simulation | 同上 | 同上 | PASS | R0,pack=0.09 Ω |
| 3S 60 s 末组电压 | 11.049169 | V | 69.9 s 采样 | custom_ecm_simulation | 同上 | 同上 | PASS | 固定 OCV |
| 3S 电压求和误差 | 0.0 | V | 全时段 | custom_ecm_simulation | 同上 | `consistency_metrics.json` | PASS（≤1e-6 V） | 同一电流 |
| 3S 一致电芯最大压差 | 0.0 | V | 全时段 | custom_ecm_simulation | 同上 | 同上 | PASS | 完全一致参数 |
| SOC 不一致最大压差 | 0.407143 | V | 2A 至首个单体 3.0 V | custom_ecm_simulation | `battery_pack_20261126_122913_c85554` | `cell_waveforms.csv` | 已记录 | 教学 OCV |
| 容量不一致最大压差 | 0.197000 | V | 2A，容量 2.0/1.9/1.8 Ah | custom_ecm_simulation | `battery_pack_20261126_122913_52a33b` | 同上 | 已记录 | 无老化模型 |
| 内阻不一致最大压差 | 0.060000 | V | 2A，R0 30/40/60 mΩ | custom_ecm_simulation | `battery_pack_20261126_122914_0e93b0` | 同上 | 已记录 | 忽略温度 |
| 综合不一致最大压差 | 0.468857 | V | SOC+容量+内阻 | custom_ecm_simulation | `battery_pack_20261126_122915_5df86a` | 同上 | 已记录 | 教学参数 |
| 首个越限电芯 | cell3 | – | 四种不一致实验 | custom_ecm_simulation | 同上 | `event_log.csv` | 已记录 | 非 BMS 保护动作 |
| 恒阻 5.7 Ω 初始电流 | 1.968912 | A | 3S，1800 s | custom_ecm_simulation | `battery_pack_20261126_122903_614806` | `power_delivery_constant_resistance.csv` | 已记录 | 理想负载 |
| 恒阻末端电流 | 1.933842 | A | 1800 s | custom_ecm_simulation | 同上 | 同上 | 已记录 | 未含变换器 |
| 恒功率 11.111 W 初始电流 | 0.982276 | A | 3S，1800 s | custom_ecm_simulation | 同上 | `power_delivery_constant_power.csv` | 已记录 | 90% 效率为假设 |
| 恒功率平均功率 | 11.111112 | W | 1800 s | custom_ecm_simulation | 同上 | 同上 | 已记录 | 理想恒功率 |
| 步长细化电压差（恒阻） | 1.02e-6 | V | 0.1 s 对 0.05 s | custom_ecm_simulation | 同上 | `power_delivery_summary.json` | PASS | 局部截断误差 |
| 步长细化电压差（恒功率） | 2.73e-7 | V | 0.1 s 对 0.05 s | custom_ecm_simulation | 同上 | 同上 | PASS | 同上 |
| Python/ngspice 最大误差（单体二阶） | 1.23e-6 | V | 0–190 s，排除阶跃 0.15 s | SPICE_SIMULATION | `spice_ecm_20261126_122919_ee3a13` | `waveform.csv`、`circuit.cir` | PASS（≤1e-3 V） | 线性 R/C |
| Python/ngspice 最大误差（3S） | 3.64e-6 | V | 同上 | SPICE_SIMULATION | `spice_ecm_20261126_122919_ba990a` | `pack_waveform.csv`、`circuit.cir` | PASS（≤1e-3 V） | 线性 R/C |
| PyBaMM 与自研 ECM 最大差 | 1.14e-5 | V | 2A 60s 脉冲 | BEHAVIORAL_MODEL | `stage2_20261126_123044_d2d0af` | `pybamm_comparison.csv` | PASS | 官方库，非自主求解器 |
| CALCE 重放 Rint RMSE | 0.299492 | V | DST 60–1559 s，151 点 | 公开实验数据 | `stage2_20261126_123044_d2d0af` | `calce_replay_comparison.csv` | UNCALIBRATED_BASELINE | 未辨识参数与 SOC |
| CALCE 重放二阶 RC RMSE | 0.333280 | V | 同上 | 公开实验数据 | 同上 | 同上 | UNCALIBRATED_BASELINE | 同上 |
| pytest 回归 | 118 passed | 项 | 全量测试 | SOFTWARE_TEST | – | `results/stage2/acceptance_commands.log` | PASS | 软件测试不等同电源性能 |
| pip check | No broken requirements | – | kaifa_battery | SOFTWARE_TEST | – | 同上 | PASS | 依赖自洽 |

## 2. 验收结论

| 检查项 | 结果 | 阈值 | 结论 |
| --- | --- | --- | --- |
| RC 解析误差 | 4.44e-16 V | ≤1e-6 V | PASS |
| Rint 解析误差 | 0.0 V | ≤1e-6 V | PASS |
| SOC 误差 | 3.33e-13 | ≤1e-8 | PASS |
| 3S 电压求和误差 | 0.0 V | ≤1e-6 V | PASS |
| 一致电芯压差 | 0.0 V | ≤1e-9 V | PASS |
| Python 与 ngspice | 3.64e-6 V | ≤1e-3 V | PASS |
| PyBaMM 交叉验证 | 1.14e-5 V | ≤2e-3 V | PASS |
| 脉冲能量平衡 | 1.25e-5 | ≤1e-3 | PASS |
| 6 工况 × 3 模型能量平衡 | 全部 PASS_RELATIVE | 全部通过 | PASS |

## 3. 明确未完成事项

- 真实电芯参数辨识（R0、R1/C1、R2/C2、OCV-SOC）未执行，属于第三阶段。
- EKF/UKF、SOC 估计、SOH 估计未执行。
- BMS 保护与均衡仅记录模型边界，未实现保护电路。
- 无真实硬件测量，禁止将本文件数值描述为硬件实测。
- 参数为教学假设，禁止描述为商业电芯参数。

## 4. 主要运行目录

- 三模型脉冲对照：`results/ecm/run_ecm_20261126_122858_dadfee/`
- 3S 基准与恒阻/恒功率：`results/battery_pack/run_battery_pack_20261126_122903_614806/`
- 不一致性汇总：`results/battery_pack/run_battery_pack_20261126_122915_bee8ed/`
- 真实 ngspice：`results/spice_ecm/run_spice_ecm_20261126_122919_f8aaf5/`
- 动态/外部对照：`results/stage2/run_stage2_20261126_123044_d2d0af/`
- 综合验收：`results/stage2/run_stage2_20261126_123052_b15f65/`
- 命令日志：`results/stage2/acceptance_commands.log`
