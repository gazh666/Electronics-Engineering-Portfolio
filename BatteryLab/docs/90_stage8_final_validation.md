# 90 第八阶段最终验收

日期：2026-11-26
定位：**Engineering Prototype Design — Not Hardware Validated**
最终判定：**10 项 PASS，1 项 FAIL，9 项 BLOCKED；0 项伪造；硬件未验证**

标准运行：`results/eda/run_stage8_20261126_165159_f06bd0`
计算运行：`results/eda/run_calc_20261126_164748_4dd611`
BOM 运行：`results/eda/run_bom_20261126_165157`
工程图运行：`results/eda/run_figures_20261126_170245_33438b`
全量测试：**480 passed in 71.26 s**；`pip check`：No broken requirements found

---

## 1. 一句话结论

第八阶段完成了**可核查的器件选型、引脚级原理图设计、真实设计计算、BOM、评审、
FMEA、验证计划与自动化审计工具**；由于本机没有 KiCad，**原理图、PCB、ERC、DRC、
Gerber、STEP 全部为 BLOCKED**，没有任何替代图片或伪造报告被当作完成证据。

---

## 2. 环境与基线

| 项 | 实测值 | 说明 |
| --- | --- | --- |
| Conda 环境 | `kaifa_battery` | Python 3.11.18 |
| PySpice / ngspice | 1.5 / 34 | 第六、七阶段已用 |
| 本阶段前全量测试 | 412 passed（62.78 s） | 前七阶段基线 |
| 本阶段后全量测试 | **480 passed（71.26 s）** | 新增 68 个测试 |
| `pip check` | 干净 | 无破损依赖 |
| KiCad | **未安装** | `kicad-cli` 不在 PATH，`C:\Program Files\KiCad` 不存在 |
| winget 可见包 | `KiCad.KiCad 10.0.8` | 仅记录，未安装、未提权 |
| 版本控制 | BatteryLab 非 git 仓库 | 无法提供 commit |

---

## 3. 交付物清单

### 3.1 需求与设计输入

| 文件 | 内容 | 状态 |
| --- | --- | --- |
| `hardware/eda/requirements/bms_design.yaml` | 3S BMS 设计目标、AFE 选型、保护窗口 | 完成 |
| `hardware/eda/requirements/charger_design.yaml` | 18 V→12.15 V/1 A 充电目标 | 完成 |
| `hardware/eda/requirements/bms_pin_mapping.csv` | 32 引脚 + PAD，33 行，逐行页码 | 完成 |
| `hardware/eda/requirements/charger_pin_mapping.csv` | 24 引脚 + PAD，25 行 | 完成 |
| `hardware/eda/requirements/critical_net_rules.csv` | 18 类关键网络规则 | 完成 |
| `hardware/eda/requirements/interface_definition.csv` | J1–J5、TP1–TP4 接口 | 完成 |
| `hardware/eda/requirements/balancing_design_review.csv` | 内部/外部均衡方案评审 | 完成 |

### 3.2 器件选型

| 文件 | 内容 | 状态 |
| --- | --- | --- |
| `component_database.csv` | 17 条器件记录，标注核查状态 | 完成 |
| `mosfet_comparison.csv` | 4 款 TI NexFET 对比 | 完成 |
| `shunt_comparison.csv` | 1/2/5/10 mΩ 四种分流对比 | 完成 |
| `capacitor_comparison.csv` | 5 类电容候选 | 完成（DC Bias 缺，NOT_VERIFIED） |
| `inductor_comparison.csv` | 4 款电感（含 1 款未核实） | 完成 |
| `component_derating.csv` | 13 项降额检查 | 完成 |
| `footprint_verification.csv` | 8 个封装核查 | BLOCKED（无 KiCad） |

### 3.3 工具与脚本

| 类别 | 文件 | 状态 |
| --- | --- | --- |
| 设计计算 | `eda_tools/design_calculations.py` | 完成 |
| 热计算 | `eda_tools/thermal_calculations.py` | 完成 |
| 反馈设计 | `eda_tools/feedback_design.py` | 完成 |
| 电感设计 | `eda_tools/inductor_design.py` | 完成 |
| 铜箔计算 | `eda_tools/copper_calculations.py` | 完成 |
| KiCad 调用 | `eda_tools/kicad_runner.py` | 完成（未找到 CLI 时如实报告） |
| 网表解析 | `eda_tools/netlist_parser.py` | 完成 |
| 引脚审计 | `eda_tools/pin_mapping_audit.py` | 完成 |
| BOM 审计 | `eda_tools/bom_validator.py` | 完成 |
| 板级指标 | `eda_tools/board_metrics.py` | 完成（pcbnew 延迟导入） |
| 报告解析 | `eda_tools/report_parser.py` | 完成 |
| 发布清单 | `eda_tools/release_manifest.py` | 完成 |
| 布局应用 | `eda_tools/board_placement.py` | 完成（pcbnew 延迟导入） |

脚本：`scripts/verify_kicad.py`、`hardware_design_calculation.py`、`audit_schematic.py`、
`audit_pcb.py`、`export_eda_artifacts.py`、`generate_hardware_bom.py`、
`battery_stage8_demo.py`、`hardware_engineering_figures.py` 共 8 个，全部真实运行。

### 3.4 文档

`docs/77`–`docs/90` 共 14 篇；`portfolio/stage8_engineering_evidence.md` 1 篇；
`hardware/design_review/` 下 3 个 CSV + 1 个验证计划。

---

## 4. 真实计算汇总（解析计算，不是实测）

| 项 | 数值 | 依据 |
| --- | --- | --- |
| 分流电阻 | 10 mΩ，WSL2010R0100FEA | Vishay WSL Doc 30100 |
| 2.5 A 时分流功耗 | 62.5 mW（额定的 12.5%） | P=I²R |
| 分流满量程 / 分辨率 | ±20 A / 0.757 mA | BQ76922 ±200 mV，1 LSB=7.568 µV |
| 分流温度系数 | 75 ppm/°C | **超过 BQ76922 建议的 50 ppm/°C** |
| BMS 保护 FET | 2×CSD18540Q5B（60 V，2.2 mΩ max） | SLPS488B |
| 2.5 A 路径损耗 | 27.5 mW（每只 13.75 mW） | I²R |
| 单管一阶结温 | 25.69 ℃（Δ≈0.69 ℃） | RθJA 50 ℃/W（数据手册条件） |
| 单体输入滤波 | 47 Ω + 0.22 µF | SLUSE86A p.7 |
| 滤波截止频率 | 7696.08 Hz | 一阶 RC |
| 100 kHz 衰减 | −22.30 dB | 一阶 RC |
| 充电电压设定 | 12.075 V（R2=475 kΩ, R1=100 kΩ） | VFB=2.1 V |
| 单体对应电压 | 4.025 V | 12.075/3 |
| 电压容差最坏区间 | 11.916–12.236 V | 基准 ±0.5%、电阻 ±0.5% |
| 充电电流设定 | 1.0061 A（ISET1=0.20122 V） | V_ISET1/(20×R_SR) |
| 预充/终止电流 | 0.1012 A（ISET2=0.10123 V） | V_ISET2/(100×R_SR) |
| 输入限流 | 1.500 A（ACSET=0.300 V） | V_ACSET/(20×R_AC) |
| 安全定时 | 5.227 h（56 nF） | K_TTC=5.6 min/nF |
| 电感 | 22 µH，SRN6045-220M | Bourns SRN6045 |
| 纹波 | 0.299 A（29.9%），峰值 1.150 A | Buck 公式 |
| 电感 DCR 损耗 | 0.142 W | I²R |
| LC 谐振（标称 9.4 µF） | **11.07 kHz** | 1/(2π√LC) |
| 充电 FET 导通损耗 | 5.76 mW（高边 4.66 + 低边 1.11） | 仅导通 |
| 均衡电流 | 65.32 / 54.00 / 43.55 mA（Rint 15/28/46 Ω） | 内部均衡 |
| 外部 47 Ω 功耗 | **200.6 / 137.1 / 89.1 mW** | 最坏超过 0.25 W 的 80% |
| 芯片内部均衡功耗 | 64.0 / 81.6 / 87.2 mW | RθJA 33.2 ℃/W |
| 铜箔示例 | 20 mm×2 mm×35 µm @2.5 A → 4.926 mΩ / 30.79 mW | 理想均匀铜箔 |

---

## 5. 验收项逐条判定

| # | 验收项 | 判定 | 证据 |
| --- | --- | --- | --- |
| 1 | Python 环境记录 | PASS | `metadata.json` |
| 2 | 依赖完整性 | PASS | `pip_check.json` |
| 3 | KiCad 可用 | BLOCKED | `kicad_version.txt` = KICAD_NOT_FOUND |
| 4 | BQ76922 引脚映射完整（32+PAD） | PASS | `pin_mapping_completeness.json` |
| 5 | BQ24610 引脚映射完整（24+PAD） | PASS | 同上 |
| 6 | 设计计算完成 | PASS | `design_calculations.json` |
| 7 | 充电电压低于单体过压阈值 | PASS | 4.025 V < 4.25 V |
| 8 | 分流功耗在额定内（2.5 A） | PASS | 62.5 mW / 500 mW |
| 9 | 均衡电阻功耗不超 1206 额定 | PASS | 200.6 mW / 250 mW（余量仅 19.8%） |
| 10 | LC 谐振在 12–17 kHz | **FAIL** | 标称 11.07 kHz |
| 11 | BOM 审计无问题 | PASS | `bom_validation.json`，issues=0 |
| 12 | BMS 原理图 | BLOCKED | `blocked_items.json` |
| 13 | BMS PCB | BLOCKED | 同上 |
| 14 | ERC 报告 | BLOCKED | 未产出 |
| 15 | DRC 报告 | BLOCKED | 未产出 |
| 16 | 原理图 PDF | BLOCKED | 未产出 |
| 17 | Gerber | BLOCKED | 未产出 |
| 18 | 钻孔文件 | BLOCKED | 未产出 |
| 19 | STEP | BLOCKED | 未产出 |
| 20 | 发布清单 | PASS | 12 个文件已哈希 |

**为什么第 10 项是 FAIL 而不是 PASS**：按标称 9.4 µF 计算，LC 谐振 11.07 kHz
低于 BQ24610 内部补偿要求的 12–17 kHz。考虑 MLCC 直流偏压后有效电容下降，
谐振会上移进入目标带，但没有 DC Bias 曲线与实测，不能把"可能合格"写成 PASS。
因此保留 FAIL，并在第 7 节列为待实测项。

---

## 6. 三个真实工程发现

### 6.1 分流电阻温度系数偏离官方布局建议

BQ76922 数据手册 p.62 要求分流电阻 TC ≤ 50 ppm/°C。可获得的 Vishay WSL
（±1%、2010/2512）在 10 mΩ 档为 ±75 ppm/°C，1–2 mΩ 档更高达 ±275 ppm/°C。
本设计选择 10 mΩ 作为分辨率与功耗的折中，**TC 偏离必须记录**，并在软件中做
温度补偿；若要严格满足，需要改用更低 TCR 的四端或合金分流电阻，并重新核查
数据手册。

### 6.2 滤波电阻同时是均衡电阻，功耗被低估

BQ76922 采用内部均衡时，均衡电流经过 VC 引脚与外部 47 Ω 滤波电阻。4.05 V、
内部电阻最小 15 Ω 时，电流 65.32 mA，外部电阻功耗 **200.6 mW**，已超过 0603
常见 0.1 W，达到 1206 0.25 W 的 80%。这不是"理论担忧"，而是设计取值直接
推出的结论。缓解：使用 1206/2512 电阻、增大阻值降低电流、限制同时均衡节数，
并在实测中用热像仪确认温升。

### 6.3 30 V MOSFET 在 32 V 输入过压保护下的边界

BQ24610 对 20 V 输入推荐 30 V 及以上 MOSFET，但本设计 ACOV 为 32 V。
30 V 器件在输入瞬态下余量不足，属于 MANUAL_REVIEW，需要输入钳位、TVS
或改用 40/60 V 器件后重新评估 FOM 与驱动损耗。

---

## 7. 未完成项与用户需要执行的操作

本机没有 KiCad，以下步骤必须由用户在有 KiCad 的环境中完成：

1. 安装 KiCad（官方安装包或 `winget install --id KiCad.KiCad`），勾选符号库、
   封装库与 3D 模型库。
2. 验证 CLI：
   `"C:\Program Files\KiCad\<版本>\bin\kicad-cli.exe" version`
3. 运行环境探测：
   `conda run -n kaifa_battery python -m scripts.verify_kicad --cli "<上面的路径>"`
4. 在 KiCad 中新建 `BatteryLab_BMS_V1` 与 `BatteryLab_Charger_V1` 工程，按
   `hardware/eda/requirements/bms_pin_mapping.csv` 与 `charger_pin_mapping.csv`
   绘制原理图，放置符号与封装，保存为 `.kicad_sch` / `.kicad_pcb`。
5. 运行 ERC：
   `kicad-cli sch erc --format json --output results/eda/.../erc_raw.json <工程>`
6. 布局布线后运行 DRC：
   `kicad-cli pcb drc --format json --severity-all --exit-code-violations --output ... <工程>`
7. 导出：`kicad-cli pcb export gerbers/drill/pos/step`、
   `kicad-cli sch export pdf`。
8. 重新运行 `python -m scripts.audit_schematic`、`audit_pcb`、
   `export_eda_artifacts`，把 BLOCKED 变成真实审计结果。

**不要**为了"看起来完成"而手工编写 `.kicad_pcb` 文本或伪造 DRC JSON。

---

## 8. 明确不可宣称的内容

1. 不得宣称已完成 KiCad 原理图或 PCB。
2. 不得宣称 ERC/DRC 通过。
3. 不得宣称已制板、已焊接、已上电、已实测。
4. 不得把 12.6 V 当作允许的充电条件。
5. 不得把教学保护阈值当作 BQ76922 寄存器或 OTP 已配置。
6. 不得把解析计算当作硬件精度、温升或量产一致性结论。
7. 不得宣称 WSL 分流满足 50 ppm/°C 建议。
8. 不得把"标称 LC 11.07 kHz"写成"满足 12–17 kHz"。

---

## 9. 测试与依赖

| 项 | 结果 |
| --- | --- |
| 新增测试文件 | 6 个 |
| 新增测试用例 | 68 个（全部通过） |
| 全量测试 | **480 passed（71.26 s）** |
| `pip check` | No broken requirements found |
| 无 KiCad 环境下的导入 | 通过（pcbnew 延迟导入） |

---

## 10. 工程图

`results/eda/run_figures_20261126_170245_33438b/` 共 12 张，全部由解析计算生成，
每张标注 `CALCULATED — NOT MEASURED`，并在 `figures_manifest.json` 中声明
`not_eda_exports=true`、`not_measured=true`：

01 分流功耗与分辨率、02 RDS(on) 温漂、03 BMS 路径损耗、04 均衡功耗、
05 均衡电流、06 充电电压容差、07 充电电流设定、08 电感纹波、09 LC 谐振、
10 铜箔、11 充电器导通损耗、12 分流 TC 与限值。

---

## 11. 复现命令

```bash
conda run -n kaifa_battery python -m scripts.verify_kicad
conda run -n kaifa_battery python -m scripts.hardware_design_calculation
conda run -n kaifa_battery python -m scripts.generate_hardware_bom
conda run -n kaifa_battery python -m scripts.audit_schematic
conda run -n kaifa_battery python -m scripts.audit_pcb
conda run -n kaifa_battery python -m scripts.export_eda_artifacts
conda run -n kaifa_battery python -m scripts.hardware_engineering_figures
conda run -n kaifa_battery python -m scripts.battery_stage8_demo --profile standard
conda run -n kaifa_battery python -m pytest tests -q
conda run -n kaifa_battery python -m pip check
```

---

## 12. 与第九阶段的接口

- 引脚映射、BOM、设计计算 JSON、评审 CSV、FMEA、验证计划可直接被第九阶段复用；
- 所有 BLOCKED 与 NOT_EXECUTED 状态必须保留，不得在第九阶段改写成通过；
- 取得真实 KiCad 结果或实测数据后，应生成新的 Run ID，并同时保留本文件作为
  设计阶段基线；
- 本阶段不修改 TestLab、PowerLab，也不采购器件、不制板、不上电。
