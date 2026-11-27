# 证据索引（每个数字都能落到文件）

## BatteryLab

| 指标 | 数值 | 文件 |
|---|---|---|
| 全量测试 | 594 passed | `BatteryLab/portfolio/BatteryLab_最终EDA硬件设计验收报告.md`、`BatteryLab/portfolio/*_v3.md` |
| 历史测试 | 550 passed（单独存档） | `BatteryLab/portfolio/BatteryLab_工程指标真实性核查报告_v3.md` |
| BMS PCB 规模 | 4 层 100.1×72.1 mm、34 footprint、304 段、46 过孔 | `BatteryLab/hardware/eda/BatteryLab_BMS_V2/release/routing_metrics.json` |
| 充电器 PCB 规模 | 4 层 100.1×72.1 mm、33 footprint、316 段、50 过孔 | `BatteryLab/hardware/eda/BatteryLab_Charger_V2/release/routing_metrics.json` |
| BMS ERC | 0 错误 / 59 告警 | `.../BatteryLab_BMS_V2/release/erc.json` |
| BMS DRC | 0 错误 / 0 未连接 / 4 一致性（安装孔） | `.../BatteryLab_BMS_V2/release/drc.json` |
| 充电器 ERC / DRC | 0/50 告警；0 错误 / 0 未连接 / 4 一致性 | `.../BatteryLab_Charger_V2/release/erc.json`、`drc.json` |
| 引脚审计 | BMS 33（30 匹配 + 3 允许悬空）、充电器 25 全匹配 | `.../release/pin_mapping_audit.csv` |
| ERC 告警逐条分类 | 109 条（59+50） | `BatteryLab/hardware/eda/review/schematic_warning_review.csv` |
| QFN 间距处理 | 4 errors → 0，局部 0.15 mm | `BatteryLab/hardware/eda/review/qfn_clearance_review.md` |
| 叠层 / 网络类 / 线宽 | IPC-2221 计算表 | `hardware/eda/review/pcb_stackup.yaml`、`net_classes.csv`、`trace_width_calculation.csv` |
| 布线后验收 | 完整报告 | `BatteryLab/portfolio/BatteryLab_PCB最终布线验收报告.md` |
| 版图前后对照 | V1→V2 | `BatteryLab/portfolio/BatteryLab_PCB工程设计前后对照.md` |
| 最终数据核查 | 11 项一致性核查 | `docs/FINAL_DATA_AUDIT.md` |
| CC-CV 指标口径 | CV 稳态误差 13.50 mV / CC→CV 过冲 2.07 mV | `docs/FINAL_DATA_AUDIT.md` §10、`BatteryLab/docs/56_spice_charging_simulation.md` |
| 面积缩小核算 | 12444 → 7217.21 mm²（−42.0%） | `docs/FINAL_DATA_AUDIT.md` §11 |
| 已知工程局限 | 109 ERC 告警、SW 节点 108.5 mm、平面连续性等 | `known_limitations.md` |

## TestLab

| 指标 | 数值 | 文件 |
|---|---|---|
| 测试 | 557 passed | `TestLab/README.md`、`TestLab/docs/29_test_quality_report.md` |
| 覆盖率 | 84% | `TestLab/docs/29_test_quality_report.md` |
| 发布验收 | 7/7 核心检查 | `TestLab/docs/`（发布验收报告） |

## PowerLab

| 指标 | 说明 | 文件 |
|---|---|---|
| 仿真后端 | ngspice-34 共享库 | `PowerLab/docs/01_environment_setup.md` |
| 阶段范围 | 基础 11 项 + Buck 开环瞬态 | `PowerLab/README.md` |

## 关于“VERIFIED”的含义
`VERIFIED` 只表示“证据存在且可复现”，**不代表工程指标达标**；
两者在 `BatteryLab/portfolio/BatteryLab_真实量化工程成果总表_v3.md` 中分列统计。

## 关于原始运行输出
`results/`（SPICE 波形、日志、run 目录）体积大且含本机路径，**不随仓库分发**；
如需原始数据，请按 `docs/REPRODUCIBILITY.md` 在本地重新运行生成。
