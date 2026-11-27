# BatteryLab 最终 EDA 硬件设计验收报告（v3）

- 生成日期：2026-11-27
- 工程状态：**ENGINEERING RESEARCH DRAFT — NOT HARDWARE VALIDATED — NOT FOR PRODUCTION**
- 结论：**PARTIAL_COMPLETION**（原理图完成并通过引脚审计；PCB 完成放置/网表/板框/4 层与制造文件导出，但**实际布线未完成**）

> 本报告所有 ERC / DRC / 制造文件均由本机真实 KiCad 10.0.8 生成，未使用任何镜像源、未伪造任何输出。
> 禁止将本设计用于真实锂电池接线、制板、焊接或投产。

---

## 1. KiCad 环境（真实安装）

| 项目 | 实际值 |
|---|---|
| 安装方式 | `winget install --id KiCad.KiCad --exact`（官方包，来源 GitHub） |
| 版本 | **10.0.8** |
| 安装路径 | `C:\\Users\\<user>\AppData\Local\Programs\KiCad\10.0` |
| CLI | `...\10.0\bin\kicad-cli.exe` |
| 符号库 | 223 个 `.kicad_sym` |
| 封装库 | 155 个 `.pretty` |
| 3D 模型 | 已安装 |
| 绑定 Python | `...\10.0\bin\python.exe`（可 `import pcbnew`，用于程序化生成 PCB） |

证据：`results/eda/kicad_env_20261127/version.txt` 与各 `help_*.txt`。

**能力边界说明**：`kicad-cli` 只负责检查与导出（ERC/DRC/网表/Gerber/钻孔/STEP/SVG/PDF），不具备原理图绘制或自动布线能力；本工程的原理图与 PCB 由脚本按真实器件符号/封装生成，属"可编辑工程"，布线仍需人工完成。

---

## 2. 真实可编辑工程文件

```text
hardware/eda/
├── BatteryLab_BMS_V1/
│   ├── BatteryLab_BMS_V1.kicad_pro
│   ├── BatteryLab_BMS_V1.kicad_sch
│   ├── BatteryLab_BMS_V1.kicad_pcb
│   ├── sym-lib-table / fp-lib-table
│   └── release/            (netlist.xml, schematic.pdf, bom.csv, erc.json, drc.json,
│                            pcb_top.svg, pcb_bottom.svg, gerbers/, drill/, positions.csv,
│                            board.step, layout_review.csv, release_manifest.json)
├── BatteryLab_Charger_V1/  (同上结构)
└── libraries/BatteryLab.kicad_sym   (自定义 U1/U2/MOSFET 符号)
```

- 主控符号：`BatteryLab:BQ76922`（RSN 32 脚 + PAD）、`BatteryLab:BQ24610`（RGE 24 脚 + PAD），按官方引脚表逐脚命名。
- MOSFET：`BatteryLab:NMOS_SON5x6`（1–9 脚，映射 SON 5×6）。
- 标准器件符号取自官方库（`Device:R/C/L`、`Connector_Generic`、`Connector:TestPoint`）。
- 封装（**真实 KiCad 库**）：`Package_DFN_QFN:Texas_RSN_WQFN-32-1EP_4x4mm_P0.4mm_EP2.8x2.8mm`、`Package_DFN_QFN:Texas_RGE0024H_VQFN-24-1EP_4x4mm_P0.5mm_EP2.7x2.7mm`、`Package_SON:Texas_S-PVSON-N8`、`Inductor_SMD:L_Bourns_SRN6045TA`、`Resistor_SMD`、`Capacitor_SMD`、`Connector_PinHeader_2.54mm`、`TestPoint`。

---

## 3. 原理图完成度

### 3.1 BMS（BatteryLab_BMS_V1）
覆盖 12 个功能块：3S 采集接口、BQ76922、采集 RC 滤波（47Ω/0.22µF）、供电去耦（REG18/REG1 2.2µF）、双向电流检测（10mΩ + 100Ω 滤波）、背靠背高侧保护 MOSFET、栅极驱动、内部均衡（不设外部均衡支路）、NTC 检测、I²C 主机接口、电池/负载连接器、4 个测试点。

### 3.2 充电器（BatteryLab_Charger_V1）
覆盖：输入接口、输入检流（10mΩ）、BQ24610、同步 Buck 功率级（600kHz，22µH，2×4.7µF）、高低侧 MOSFET、充电电流采样、VFB 分压（2.1V→12.15V）、NTC/充电使能、REGN 自举与肖特基、去耦与测试点。

### 3.3 真实引脚映射审计（`scripts/audit_schematic.py`）

| 工程 | 组件 | 网络 | 通过 | 人工确认 | 失败 |
|---|---|---|---|---|---|
| BMS | 30 | 34 | 27 | 6 | **0** |
| 充电器 | 29 | 25 | 25 | 0 | **0** |

BMS 的 6 项人工确认 = 3 项数据手册允许悬空（TS2/PDSG/PCHG，已放 `no_connect`）+ 3 项同名网（VC4B/VC3B/BREG，`SAME_NET_AS`）。**关键芯片引脚无一项失败。**

---

## 4. 真实 ERC（`kicad-cli sch erc --severity-all`）

| 工程 | 错误 | 告警 | 告警构成 |
|---|---|---|---|
| BMS | **0** | 59 | 离线网格 51、单引脚标签 5、自定义库提示 3 |
| 充电器 | **0** | 50 | 离线网格 40、单引脚标签 7、自定义库提示 3 |

- **ERC 错误为 0**。
- `endpoint_off_grid`：坐标未落在 KiCad 连接网格的 0.01mm 量化差，属装饰性告警。
- `isolated_pin_label`：ALERT / CFETOFF / DFETOFF / CP1 等仅连接到主机/测试点的单引脚网络，属设计意图。
- `lib_symbol_issues`：无 GUI 环境下 `BatteryLab` 自定义库解析提示；符号已内嵌于 `.kicad_sch`（`lib_symbols`），文件可独立打开编辑。

---

## 5. 真实 PCB 与 DRC（`kicad-cli pcb drc --schematic-parity`）

| 指标 | BMS | 充电器 |
|---|---|---|
| 层数 | **4**（F.Cu / In1.Cu / In2.Cu / B.Cu） | 4 |
| 板框尺寸 | **102 × 122 mm** | 102 × 122 mm |
| 放置器件 | **30 / 30** | 29 / 29 |
| 网络 | 34 | 25 |
| 原理图- PCB 一致性 | **0 项** | **0 项** |
| DRC 错误 | **4**（间距，QFN 细间距） | **0** |
| DRC 告警 | 1（`lib_footprint_mismatch`，热焊盘改名） | 1 |
| **未连接项** | **65** | **51** |

### 5.1 关键说明（不掩饰问题）
1. **PCB 未完成实际布线**：`kicad-cli` 无自动布线能力；本工程完成"放置 + 网表 + 板框 + 4 层 + GND 铜皮填充（F.Cu/B.Cu）+ 封装/焊盘"的真实可编辑板，但非 GND 走线未绘制，故仍存在 65/51 个未连接项 → 状态 **PARTIAL**（GND 已通过铺铜连通，较未铺铜时 71/67 下降）。
2. **4 个间距错误（BMS）**：全部为 U1（QFN-32，0.4mm 间距）自身相邻焊盘，实际间隙 0.1828mm < 默认 0.2mm 规则。正确处理是为该细间距器件定义 0.15mm 间距规则；本报告**未通过放宽/关闭规则来制造"零错误"**，如实保留。
3. **板框大于 70×50 目标**：为容纳全部器件并保持 20mm 放置栅格，板框自动扩展为 102×122mm；布线压缩后可回归 70×50 量级，属待优化项。
4. **MOSFET 引脚映射假设**：SON 5×6 采用 1–3=S、4=G、5–8=D、9(EP)=D 的常见定义，**须按 TI 数据手册 SLPS488B/SLPS526/SLPS630 顶视图复核后方可制板**。

---

## 6. 制造文件（研究版本，禁止投产）

每个工程 `release/` 均含 40 个文件（`release_manifest.json` 记录 sha256）：

- `netlist.xml`、`schematic.pdf`、`bom.csv`
- `erc.json`、`drc.json`
- `pcb_top.svg`、`pcb_bottom.svg`
- `gerbers/`（F.Cu、In1.Cu、In2.Cu、B.Cu、阻焊、丝印、Edge.Cuts、job 文件等）
- `drill/*.drl`（Excellon）
- `positions.csv`（贴片坐标，mm，双面）
- `board.step`（3D）
- `layout_review.csv`（逐器件放置与关键性评审）
- `unconnected_nets.csv`（未完成网络清单，依据真实 DRC）
- `manual_routing_steps.md`（人工布线操作步骤）
- `release_manifest.json`

> 所有 Gerber / 钻孔 / STEP **均标注为工程研究版本、未经硬件验证**；因 PCB 未布线，**不得用于制板**。

---

## 7. 与教学模型的边界（必须区分）

- 本文件中的 BQ76922 / BQ24610 为**真实芯片方案**，引脚与封装逐项核对官方数据手册。
- 此前自主分立 AFE 教学模型（含 3.837mV / 6.666mA 误差预算、第六阶段非同步 Buck 参数）**不是**本板卡的实测精度或外围参数，二者严格分离。
- 历史 BOM 检查通过 ≠ 封装焊盘、实际连线、硬件安全已验证。

---

## 8. 仍存在的人工工作（未完成网络清单来源）

- 打开 `BatteryLab_BMS_V1.kicad_pcb` 与 `BatteryLab_Charger_V1.kicad_pcb`，依据 `drc.json` 的 `unconnected_items` 完成布线（优先 BAT_POS / PACK_POS / PACK_NEG 2.0mm 功率路径、SENSE_P/SENSE_N Kelvin、PHASE 回路、栅极驱动回路）。
- 为 U1 定义 QFN 细间距（0.15mm）间距规则并复核 4 个间距项。
- 复核 MOSFET SON 5×6 引脚映射与全部封装焊盘（对照官方 Datasheet 顶视图）。
- 布线后重新运行 `kicad-cli pcb drc --schematic-parity` 并重新导出 Gerber/STEP。

---

## 9. 验收结论

| 维度 | 状态 |
|---|---|
| KiCad 环境 | **PASS**（10.0.8 真实安装） |
| 原理图数量 | **PASS**（2 套，可编辑） |
| 关键引脚/封装核查 | **PASS**（U1/U2 引脚 0 失败；封装为真实库） |
| ERC | **PASS**（0 错误） |
| 原理图-PCB 一致性 | **PASS**（0 项） |
| PCB 布线 | **FAIL / PARTIAL**（未布线，71/67 未连接） |
| DRC 间距 | **FAIL（4 项，BMS）**（QFN 细间距规则未设） |
| 制造文件 | **研究版本**（已导出，禁止投产） |
| 硬件验证 | **NOT VERIFIED**（未打样） |

**最终：PARTIAL_COMPLETION。** EDA 硬件设计已从"BLOCKED_NO_KICAD"推进到"真实可编辑工程 + 真实 ERC/DRC + 真实制造文件"，但布线未完成，须人工收尾后方可用于评审。
