# 103 工程图与结果呈现

## 1. 原则

1. 所有图由**本阶段真实运行结果**绘制，不手绘近似；
2. 每张图标注 `SIMULATED / CALCULATED — NOT MEASURED`；
3. 概念图单独标记 `CONCEPTUAL`，不与数据图混用；
4. 缺数据时记录 `SKIPPED`，不生成占位图；
5. 图清单写入 `figures_manifest.json`，包含 `not_measured: true`。

实现：`scripts/system_engineering_figures.py`，数据来源按最新运行目录自动发现。
实际运行：`results/stage9/figures/figures_20261126_174007_f7dbf7`，共 14 张
（13 张数据图 + 1 张概念图），清单见同目录 `figures_manifest.json`。

## 2. 图目录

| 编号 | 文件 | 数据来源 | 性质 |
| --- | --- | --- | --- |
| 01 | `01_system_architecture.png` | 无（结构说明） | CONCEPTUAL |
| 02 | `02_power_map_vout.png` | `results/converter_power_map/*/converter_power_map_*.csv` | 真实 SPICE |
| 03 | `03_power_map_efficiency.png` | 同上 | 真实 SPICE |
| 04 | `04_integrated_voltages.png` | `results/system_spice/*/waveform.csv` | 同网表 SPICE |
| 05 | `05_integrated_currents.png` | 同上 | 同网表 SPICE |
| 06 | `06_load_step_vout.png` | `results/system_average/*/average_result.json` | 平均模型 |
| 07 | `07_bidirectional_coupling.png` | 同上 | 平均模型 |
| 08 | `08_protection_spice.png` | `results/system_protection/*/waveform.csv` | 同网表 SPICE |
| 09 | `09_fault_injection.png` | `results/system_protection/*/fault_injection.json` | 真实控制器 |
| 10 | `10_discharge_runtime.png` | `results/system_lifetime/discharge_*` | ECM + 映射 |
| 11 | `11_min_cell_voltage.png` | 同上 | ECM + 映射 |
| 12 | `12_aging_runtime.png` | `results/system_lifetime/aging_*` | 参数敏感性 |
| 13 | `13_energy_breakdown.png` | `results/system_energy/*` | 同网表 SPICE |
| 14 | `14_baseline_candidate.png` | PowerLab `stage6_optimization/sweep.json` | 历史真实 Run |

## 3. 读图注意

- 图 04 中输出曲线乘 2 以便与 10 V 级电压同轴显示，已在绘图代码中体现；
- 图 08 展示的是"保护开关关断后的电气后果"，不是 BMS 检测时间；
- 图 10/11/12 的时间分辨率是 5 s 步长，不能读出微秒级细节；
- 图 14 的候选参数必须重新做闭环验证后才能声称可用。
