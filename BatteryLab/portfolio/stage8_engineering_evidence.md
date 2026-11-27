# BatteryLab 第八阶段 · 硬件工程证据表

日期：2026-11-26
定位：**Engineering Prototype Design — Not Hardware Validated**
判定：**10 PASS / 1 FAIL / 9 BLOCKED**，0 项伪造，硬件未验证

本文件用于简历与面试，所有数字均可在仓库内追溯。任何"已完成"表述都不包含
原理图、PCB、ERC、DRC、制板或实测。

## 1. 一句话

在无 KiCad 的实验环境中，完成 3S 电池管理系统与 1 A 同步 Buck 充电器的
**官方数据手册级器件选型、逐引脚设计、可复算设计计算、BOM、FMEA 与自动化审计工具链**，
并如实保留 9 项 KiCad 相关 BLOCKED。

## 2. 量化成果

| 维度 | 数量 | 证据 |
| --- | --- | --- |
| 官方数据手册核查 | 8 份 | `references/datasheets/` |
| 主控 PDF 全文解析 | 2 份（BQ76922 76 页、BQ24610 32 页） | `bq76922_datasheet.pdf`、`bq24610_datasheet.pdf` |
| 硬件工程设计 | 2 个（BMS、充电器） | `hardware/eda/requirements/` |
| 引脚级映射 | 32+1 与 24+1，100% 覆盖 | `bms_pin_mapping.csv`、`charger_pin_mapping.csv` |
| 关键网络规则 | 18 类 | `critical_net_rules.csv` |
| 接口定义 | 5 个连接器 + 4 个测试点 | `interface_definition.csv` |
| 器件数据库记录 | 17 条 | `component_database.csv` |
| 器件对比 | MOSFET 4 款、分流 4 种、电感 4 款、电容 5 类 | `hardware/component_selection/` |
| 降额检查 | 13 项 | `component_derating.csv` |
| 工程 BOM | 51 行（BMS 26、充电板 25） | `results/eda/run_bom_20261126_165157/bom.csv` |
| BOM 校验 | 0 问题；10 个关键器件全核查 | `bom_validation.json` |
| FMEA | 14 项失效模式 | `design_fmea.csv` |
| 验证计划 | 15 项，全部 NOT_EXECUTED | `hardware_validation_plan.md` |
| EDA/计算模块 | 13 个 | `eda_tools/` |
| 脚本 | 8 个，全部真实运行 | `scripts/` |
| 测试 | 新增 68 个；全量 480 passed | `tests/` |
| 计算工程图 | 12 张，标注 CALCULATED | `results/eda/run_figures_20261126_170245_33438b/` |
| 学习文档 | 14 篇（77–90） | `docs/` |
| 哈希清单 | 12 个文件 | `release_manifest.json` |

## 3. 关键技术结论（可复算）

1. **分流电阻**：10 mΩ / 0.5 W，2.5 A 功耗 62.5 mW；满量程 ±20 A，分辨率 0.757 mA；
   TC 75 ppm/°C，**超过 BQ76922 建议的 50 ppm/°C**，列为已知偏离。
2. **保护 MOSFET**：2×CSD18540Q5B（60 V、2.2 mΩ max），路径 4.4 mΩ，
   2.5 A 损耗 27.5 mW，单管一阶结温 25.69 ℃。
3. **单体采样**：47 Ω + 0.22 µF，截止 7696 Hz，100 kHz 衰减 −22.3 dB。
4. **充电电压**：2.1 V 基准、475 kΩ/100 kΩ → 12.075 V，单体 4.025 V，
   最坏区间 11.916–12.236 V。
5. **充电电流**：1.0061 A；预充/终止 0.1012 A；输入限流 1.500 A；定时 5.227 h。
6. **功率级**：22 µH/600 kHz，纹波 29.9%，峰值 1.150 A，DCR 损耗 0.142 W。
7. **LC 谐振**：标称 9.4 µF → 11.07 kHz，**低于 12–17 kHz 目标，判 FAIL**；
   有效电容需实测。
8. **均衡功耗**：47 Ω 最坏 200.6 mW，**超过 0.25 W 的 80%**，必须用 1206 以上。
9. **充电 FET**：30 V 器件在 32 V ACOV 下余量不足，标 MANUAL_REVIEW。

## 4. 能力映射

| 能力 | 证据 |
| --- | --- |
| 读官方数据手册并落到引脚 | BQ76922 p.3-4/p.62、BQ24610 p.4/p.17/p.29-31 逐条引用 |
| 器件选型与降额 | 4 款 MOSFET FOM 对比、4 种分流权衡、13 项降额 |
| 电路计算 | 分压、误差预算、RC、Buck、LC、热、铜箔 |
| 自动化审计 | 网表解析、引脚审计、BOM 校验、ERC/DRC 解析器、发布哈希 |
| 工程诚实性 | 9 项 BLOCKED、1 项 FAIL、3 项真实设计缺陷，全部公开 |
| 可测试性 | 68 个新测试，含反例（未知结构、重复网络、超时、缺失报告） |

## 5. 简历可直接使用的三条

1. 基于 TI BQ76922 / BQ24610 官方数据手册，完成 3S BMS 与 1 A 同步 Buck 充电器的
   引脚级设计与 51 行工程 BOM，关键器件 100% 数据手册核查，0 虚构。
2. 编写 13 个 EDA/计算模块与 8 个脚本，实现网表解析、引脚映射审计、BOM 校验、
   ERC/DRC 报告解析与 SHA-256 发布清单，新增 68 个测试（全量 480 passed）。
3. 通过解析计算识别 3 项真实设计风险（分流 TC 75 ppm 超 50 ppm 建议、均衡电阻
   200.6 mW 超 1206 的 80%、30 V FET 对 32 V ACOV 余量不足），并保留 9 项
   KiCad BLOCKED 与 1 项 LC 谐振 FAIL，未用替代图片伪造完成。

## 6. 边界声明

- 没有 KiCad 原理图、PCB、ERC、DRC、Gerber、STEP；
- 没有制板、焊接、上电、实测；
- 无源件与连接器仍为 TBD，未虚构商业型号；
- 温度特性、有效电容、开关损耗、VFB 偏置电流均为 NOT_VERIFIED；
- 本阶段不修改 TestLab / PowerLab，不采购器件。
