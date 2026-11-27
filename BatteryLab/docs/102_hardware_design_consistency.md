# 102 硬件设计一致性与器件应用研究

> 结论：EDA 交付 **BLOCKED**，硬件未验证。本文件只记录可核查的选型研究与设计计算，不把 ERC/DRC 等同于硬件验证。

## 1. EDA 交付状态

来源：`results/eda/run_stage8_20261126_165159_f06bd0/validation_summary.json`、`results/hardening/eda/run_20261126_184337_03a70e/eda_status.json`

| 检查项 | 状态 | 详情 |
|---|---|---|
| Python 环境 | PASS | 3.11.18 |
| pip check | PASS | 无损坏依赖 |
| KiCad 可用 | BLOCKED | kicad-cli 未找到 |
| BMS 引脚映射 | PASS | 33 行，缺失 0 |
| 充电器引脚映射 | PASS | 25 行，缺失 0 |
| 设计计算 | PASS | 解析计算完成 |
| 充电电压低于单体过压 | PASS | 4.0250 V/cell < 4.25 V |
| 分流电阻功率 | PASS | 62.5 mW / 500 mW |
| 均衡电阻功率 | PASS | 200.6 mW / 250 mW（1206） |
| LC 谐振目标 | **FAIL** | 11.07 kHz，目标 12–17 kHz |
| BOM 验证 | PASS | 问题 0，关键已核实 10 |
| BMS 原理图 / PCB | BLOCKED | 未生成 |
| ERC / DRC | BLOCKED | 未产生 |
| Gerber / 钻孔 / STEP | BLOCKED | 未产生 |

计数：PASS 10 / BLOCKED 9 / FAIL 1。BLOCKED 不等于通过。

## 2. 商业器件应用研究状态

来源：`hardware/component_selection/component_database.csv`

| 器件 | 类别 | Datasheet 状态 | 项目应用研究状态 |
|---|---|---|---|
| BQ76922 | 3S–5S 电池监测与保护 AFE | VERIFIED_DATASHEET（SLUSE86A） | 引脚映射 33 行完整；仅选型与原理图设计研究，未生成原理图/PCB |
| BQ24610 | 1–6 节同步 Buck 充电控制器 | VERIFIED_DATASHEET（SLUS892D） | 引脚映射 25 行完整；仅原理图设计研究，未生成原理图 |
| CSD18532Q5B / CSD18540Q5B / CSD17578Q5A / CSD17581Q5A | N 沟道功率 MOSFET | VERIFIED_DATASHEET | 4 个候选对比，用于保护/同步整流选型研究 |
| WSL2512/WSL2010 系列 | 1/2/5/10 mΩ 分流电阻 | VERIFIED_DATASHEET | 4 个阻值对比，用于电流检测选型研究 |
| INA240A2 | 双向电流检测放大器 | datasheet 规格研究 | 行为级模型与误差预算使用其手册参数 |
| SRN6045-150M / 220M | 功率电感 | VERIFIED_DATASHEET | 2 个候选；IHLP2525 未取得手册，NOT_VERIFIED |
| 10 kΩ B3950 NTC | 温度传感器 | 未取得手册 | NOT_VERIFIED |

不得把 BQ76922 / BQ24610 数据手册典型精度当作本项目分立 AFE 的实测精度；两者是不同实现。

## 3. 降额与理论功耗

| 项目 | 计算值 | 限值/额定 | 判定 |
|---|---|---|---|
| 单体充电电压 | 4.0250 V | 4.25 V 过压阈值 | PASS |
| 分流电阻功耗 @2.5 A | 62.5 mW | 500 mW | PASS |
| 均衡电阻功耗 | 200.6 mW | 250 mW | PASS |
| LC 谐振频率 | 11.07 kHz | 12–17 kHz | FAIL（保留） |

## 4. 与本次仿真结果的关系

- 保护级真实 MOSFET 仿真的通路电阻 30.67 mΩ（2×Rds(on)+封装），与 `configs/protection_config.yaml` 的 0.040 Ω 目标量级一致；
- 第 101 节系统仿真把该保护级串入电池正极，效率 94.2–95.2 % 含该通路损耗；
- 上述均为软件模型，不是 PCB 实测。

## 5. 未完成项

1. KiCad 原理图（BMS、充电器）未绘制；
2. PCB 未布局布线，层数/尺寸/器件数量无法报告；
3. ERC/DRC 未运行，未连接网络数量无法报告；
4. Gerber、钻孔、STEP 未生成；
5. 无打样、无贴片、无实物上电。
