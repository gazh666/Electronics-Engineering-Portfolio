# 最终工程数据核查报告 (FINAL_DATA_AUDIT)

- 核查日期：2026-11-27
- 核查对象：BatteryLab 两块四层 PCB（BMS V2 / Charger V2）、原理图、软件回归测试
- 核查方式：直接读取仓库内的 KiCad 检查输出、指标 JSON 与 pytest 日志，不手工改写数值
- 结论：以下数值与仓库内原始证据一致；如与历史汇报冲突，以本报告与原始证据文件为准

## 1. 证据来源（source of truth）

| 数据 | 证据文件 |
|---|---|
| BMS 布线指标 | `BatteryLab/hardware/eda/BatteryLab_BMS_V2/release/routing_metrics.json` |
| 充电器布线指标 | `BatteryLab/hardware/eda/BatteryLab_Charger_V2/release/routing_metrics.json` |
| DRC | 各 `release/drc.json` |
| ERC | 各 `release/erc.json` |
| 未连接网络 | 各 `release/unconnected_nets.csv` |
| 引脚审计 | 各 `release/pin_mapping_audit.csv` |
| 前/后工程对照 | `BatteryLab/portfolio/BatteryLab_PCB工程设计前后对照.md` |
| 回归测试 | `BatteryLab/portfolio/BatteryLab_工程指标真实性核查报告_v3.md`（记录 594 passed 及原始日志路径） |
| 原始运行输出 | 本地 `BatteryLab/results/`（体积大、含本机路径，**不随仓库分发**，可按复现步骤重新生成） |

## 2. PCB 基本参数

| 项目 | BMS V2 | Charger V2 |
|---|---|---|
| 铜层数 | **4 层**（F.Cu / In1.Cu / In2.Cu / B.Cu） | **4 层**（同左） |
| 实际板框尺寸 | **100.1 × 72.1 mm** | **100.1 × 72.1 mm** |
| 器件数 | 34（含 4 个安装孔） | 33（含 4 个安装孔） |
| 走线段数 | **304** | **316** |
| 过孔数 | **46** | **50** |
| 走线总长 | 1236.118 mm | 1207.119 mm |

- 板框尺寸取自 `GetBoardEdgesBoundingBox`，不是设计目标值；两块板完全一致。
- 层分布：BMS 段数 F 233 / In1 48 / In2 23；充电器 F 241 / In1 35 / In2 37 / B 3。

## 3. 布线与未连接

| 项目 | BMS V2 | Charger V2 |
|---|---|---|
| 未连接网络数 | **0** | **0** |
| `unconnected_items` | **0** | **0** |

两块板均已完成全部网络布线，`unconnected_nets.csv` 为空。

## 4. DRC

| 项目 | BMS V2 | Charger V2 |
|---|---|---|
| DRC 错误 | **0** | **0** |
| DRC 警告 | **1**（`lib_footprint_mismatch`） | **1**（`lib_footprint_mismatch`） |

两块板各保留 1 项 `lib_footprint_mismatch` 警告（封装库版本差异提示），不影响连通性与间距。

## 5. ERC

| 项目 | BMS V2 | Charger V2 |
|---|---|---|
| ERC 错误 | **0** | **0** |
| ERC 警告 | **59** | **50** |

BMS 59 = `endpoint_off_grid` 51 + `isolated_pin_label` 5 + `lib_symbol_issues` 3。
充电器 50 = `endpoint_off_grid` 40 + `isolated_pin_label` 7 + `lib_symbol_issues` 3。

> ERC 警告已在 `BatteryLab/hardware/eda/review/schematic_warning_review.csv` 中逐条分类。
> **分类不等于问题全部消除**；详见 `docs/known_limitations.md`。

## 6. 原理图—PCB 一致性

| 项目 | BMS V2 | Charger V2 |
|---|---|---|
| `schematic_parity` 差异 | **4** | **4** |
| 差异来源 | H1–H4 安装孔（仅 PCB 存在，无电气连接） | H1–H4 安装孔（同左） |

4 项差异全部来自 4 个仅 PCB 侧存在的安装孔，属预期差异，已记录。

## 7. 引脚映射与数据手册依据

| 项目 | 器件 | 审计项数 | 匹配 | 允许悬空 | 不一致 |
|---|---|---|---|---|---|
| BMS | BQ76922 / CSD18540Q5B | 33 | 30 | 3 | **0** |
| Charger | BQ24610 / CSD17578Q5A / CSD17581Q5A | 25 | 25 | 0 | **0** |

- 引脚定义依据 TI BQ76922、BQ24610 数据手册与 TI CSD 系列 MOSFET 数据手册；
  引脚审计表见各 `release/pin_mapping_audit.csv` 与 `review/qfn_footprint_audit.csv`。
- 3 项允许悬空为数据手册标注的 NC/不连接引脚，不是遗漏。

## 8. 原理图拓扑修复记录（真实存在）

`BatteryLab/scripts/build_eda_schematic.py` 中保留两处真实修复（对应此前发现的拓扑错误）：

1. 采样/主回路：`J1.4 → BAT_POS`、`R105.1 → BAT_POS`（原错接在电流检测回路）。
2. 接地：`J1.1 → GND`、`R101.1 → GND`（原悬空/错接）。

修复后重跑 ERC/网表，上述错误消失；历史错误网表未被覆盖删除，可追溯。

## 9. 自动化回归测试

- 最终全量 pytest：**594 passed**（记录见 `BatteryLab/portfolio/BatteryLab_工程指标真实性核查报告_v3.md`，
  原始日志 `results/eda/pytest_v3_20261127.log` 为本地运行产物，不随仓库分发）。
- 历史基线 550 passed 单独存档，未与本次合并统计。

## 10. CC-CV 指标口径更正（重点）

历史汇报中存在指标混用，现按原始波形与运行配置更正：

| 指标 | 正确数值 | 含义 |
|---|---|---|
| 恒压（CV）稳态误差 | **13.50 mV** | 进入恒压后稳态电压与目标之差 |
| CC→CV 切换过冲 | **2.07 mV** | 恒流切换到恒压瞬间的电压过冲 |
| 恒流（CC）稳态误差 | 1.09 mA | 恒流阶段电流误差 |
| 功率级效率 | 98.01 % | 充电功率级仿真效率 |

- **2.07 mV 是 CC→CV 切换过冲，不是恒压稳态误差。**
- 已更正文件：
  - `BatteryLab/docs/stage10/00_learning_manual.md`
  - `BatteryLab/docs/103_system_design_review.md`
  - `BatteryLab/scripts/battery_stage10_demo.py`
  - `BatteryLab/portfolio/BatteryLab_研发岗简历项目最终版_v4.md`
- 原始波形证据：本地 `BatteryLab/results/stage6/run_stage6_*/summary.json`（C03 工况过冲 2.07 mV；
  C02 工况 CV 误差 −13.5 mV）；汇总见 `BatteryLab/portfolio/BatteryLab_CC_CV控制优化前后对照.md` 与
  `BatteryLab/docs/56_spice_charging_simulation.md`。

## 11. PCB 面积缩小核算

- V1 板框：102 × 122 mm = **12444 mm²**（`BatteryLab_BMS_V1.kicad_pcb` Edge.Cuts 实测 0–102 / 0–122）。
- V2 板框：100.1 × 72.1 mm = **7217.21 mm²**（`routing_metrics.json` 实测）。
- 面积缩小：1 − 7217.21 / 12444 = **42.0%**（由实际尺寸计算，非估计）。

## 12. 结论

- 上述 11 项核查全部通过，数值与仓库原始证据一致。
- 仍存在未验证项：热、EMI、信号完整性、参考平面连续性、开关节点寄生、实际制板/焊接/上电。
- 本作品集为个人工程研究原型，**不是 Production Ready，也不是 Hardware Validated**。
