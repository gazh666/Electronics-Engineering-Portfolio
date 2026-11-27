# Electronics Engineering Portfolio

**Power Electronics | Battery Management | Semiconductor Applications | PCB Design | Engineering Validation**

三个独立、可复现的电子工程项目：电池管理（BatteryLab）、电源电路仿真（PowerLab）、
自动化测试与工程验证（TestLab）。全部基于真实运行的 SPICE 求解、自动化测试与 KiCad EDA 检查，
不使用伪造数据、不把仿真写成实测、不隐藏失败结论。

> 本仓库为**个人工程研究原型**，未进行制板、焊接、上电或真实仪器/电池实验。
> 明确不含 **Production Ready / Hardware Validated** 表述。工程局限见
> [known_limitations.md](known_limitations.md)。

## 三个项目

- **BatteryLab — 电池管理系统**
  模拟前端采集、AFE 误差预算、MOSFET 保护、被动均衡、CC-CV 充电、SOC 估计，
  以及两套**真实可编辑的 KiCad 原理图 + 两块四层 PCB**。

- **PowerLab — 电源电路仿真**
  Buck 拓扑、功率器件非理想建模、效率与损耗分析、Pareto 多目标优化、PI 控制、软启动。

- **TestLab — 自动化测试与验证**
  SCPI 虚拟仪器、自动化测试、参数扫描、故障注入、工程验证与可靠性统计。

## BatteryLab 最终量化成果

每项均标注结果性质：`仿真` / `解析计算` / `公开数据分析` / `EDA 设计` / `软件测试`。

| 成果 | 数值 | 性质 | 证据 |
|---|---|---|---|
| 最坏情况电压采样误差预算 | 30.887 → 3.837 mV | 仿真 | `portfolio/BatteryLab_resume_metrics_v3.csv` |
| 最坏情况电流采样误差预算 | 37.736 → 6.666 mA | 仿真 | 同上 |
| 被动均衡单体压差 | 130 → 10.47 mV | 仿真 | 同上（B01） |
| 独立 MOSFET 保护 故障→电流抑制 | 0.871 µs | 仿真（SPICE 原始波形） | `BatteryLab/portfolio/BatteryLab_MOSFET保护真实性复验.md` |
| 联合系统保护 故障→电流抑制 | 119.8 µs（**RISK**） | 仿真 | `BatteryLab/portfolio/BatteryLab_研发岗成果证据卡_v3.md` |
| CC-CV 功率级效率 | 98.01 % | 仿真 | `BatteryLab/portfolio/BatteryLab_CC_CV控制优化前后对照.md` |
| CC 稳态误差 / CV 稳态误差 / CC→CV 过冲 | 1.09 mA / 13.50 mV / 2.07 mV | 仿真 | `BatteryLab/portfolio/BatteryLab_CC_CV控制优化前后对照.md` |
| SOC 估计 RMSE | 1.8247 个百分点 | 公开数据分析（CALCE 重放） | `BatteryLab/portfolio/BatteryLab_研发岗成果证据卡.md`（E01） |
| 可编辑原理图 | 2 套（BMS / 充电器） | EDA 设计 | `hardware/eda/*V2/` |
| 四层 PCB | 2 块，100.1 × 72.1 mm | EDA 设计 | `hardware/eda/*V2/release/routing_metrics.json` |
| 走线 / 过孔总数 | 620 段 / 96 个 | EDA 设计 | 两块板合计（304+316 / 46+50） |
| PCB 未连接项 | 65 / 51 → 0 / 0 | EDA 检查 | `release/unconnected_nets.csv` |
| DRC 错误 | 4 / 0 → 0 / 0 | EDA 检查 | `release/drc.json` |
| PCB 面积缩小 | 约 42 %（102×122 → 100.1×72.1 mm） | 解析计算 | [FINAL_DATA_AUDIT.md](docs/FINAL_DATA_AUDIT.md) |
| 软件回归测试 | 594 passed | 软件测试 | `BatteryLab/portfolio/BatteryLab_工程指标真实性核查报告_v3.md` |

> 以上均为仿真、解析计算、公开数据分析、EDA 设计或软件测试结果，
> **不是实际商业 BMS 板卡的硬件测量值**。

## PCB 真实预览（KiCad 导出 SVG）

以下为 `kicad-cli` 从实际 `.kicad_pcb` 导出的顶层/底层 SVG，不是渲染图或效果图。

**BMS V2（4 层，100.1 × 72.1 mm，304 段 / 46 过孔，0 未连接）**

![BMS PCB 顶层](BatteryLab/hardware/eda/BatteryLab_BMS_V2/release/pcb_top.svg)
![BMS PCB 底层](BatteryLab/hardware/eda/BatteryLab_BMS_V2/release/pcb_bottom.svg)

**Charger V2（4 层，100.1 × 72.1 mm，316 段 / 50 过孔，0 未连接）**

![Charger PCB 顶层](BatteryLab/hardware/eda/BatteryLab_Charger_V2/release/pcb_top.svg)
![Charger PCB 底层](BatteryLab/hardware/eda/BatteryLab_Charger_V2/release/pcb_bottom.svg)

**3D / STEP 查看说明**：本仓库**不提供伪造的 3D 渲染图**。如需 3D 视图，请下载
[BMS STEP](BatteryLab/hardware/eda/BatteryLab_BMS_V2/release/board.step) 或
[Charger STEP](BatteryLab/hardware/eda/BatteryLab_Charger_V2/release/board.step)，
用 KiCad PCB Editor、FreeCAD 或任意 STEP 查看器打开。

## 工程证据索引

- 完整证据索引：[docs/EVIDENCE_INDEX.md](docs/EVIDENCE_INDEX.md)
- 最终数据核查：[docs/FINAL_DATA_AUDIT.md](docs/FINAL_DATA_AUDIT.md)
- 前后工程对照：[BatteryLab/portfolio/BatteryLab_PCB工程设计前后对照.md](BatteryLab/portfolio/BatteryLab_PCB工程设计前后对照.md)
- ERC 告警分类：[BatteryLab/hardware/eda/review/schematic_warning_review.csv](BatteryLab/hardware/eda/review/schematic_warning_review.csv)
- 布线规划与叠层：[BatteryLab/hardware/eda/review/routing_plan.md](BatteryLab/hardware/eda/review/routing_plan.md)
- 性能优化前后对照：[BatteryLab/portfolio/BatteryLab_工程性能优化前后对照_v2.md](BatteryLab/portfolio/BatteryLab_工程性能优化前后对照_v2.md)
- 原理图 PDF：[BMS](BatteryLab/hardware/eda/BatteryLab_BMS_V2/release/schematic.pdf) /
  [Charger](BatteryLab/hardware/eda/BatteryLab_Charger_V2/release/schematic.pdf)

> 说明：原始运行输出（`results/`、pytest 日志）体积较大且含本机路径，**不随仓库分发**；
> 仓库内证据为汇总 CSV、验证文档与 EDA 发布文件，原始输出可按复现步骤在本地重新生成。

## 项目索引

| 项目 | 方向 | 关键技术 | 可复现证据 |
|---|---|---|---|
| [TestLab](TestLab/README.md) | 自动化测试 / 虚拟仪器 | PyVISA-sim、SCPI、行为模型 DUT、故障注入、可靠性、报告 | 557 passed、覆盖率 84%、发布验收 7/7 |
| [PowerLab](PowerLab/README.md) | 电源电路仿真 | PySpice 1.5 + ngspice 34、Buck 开环瞬态、CCM/DCM、理论对照 | ngspice 真实求解、11 项基础分析回归 |
| [BatteryLab](BatteryLab/README.md) | 电池采样 / 保护 / 充电 / EDA | 电池模型、AFE 误差预算、保护 SPICE、充电闭环、KiCad 4 层 PCB | 594 passed、ERC/DRC 0 错误、0 未连接 |

## 目录说明

```
Electronics-Engineering-Portfolio/
├── TestLab/                      # PyVISA-sim 自动化测试平台
├── PowerLab/                     # PySpice + ngspice 电源仿真
├── BatteryLab/                   # 电池软件链 + KiCad 硬件设计
│   ├── hardware/eda/
│   │   ├── BatteryLab_BMS_V1/    # 未布线工程草案（保留）
│   │   ├── BatteryLab_BMS_V2/    # 完成布线的工程研究版本
│   │   ├── BatteryLab_Charger_V1/
│   │   ├── BatteryLab_Charger_V2/
│   │   ├── requirements/         # 引脚映射、网络规则、接口定义
│   │   └── review/               # ERC 告警分类、QFN 审核、叠层、线宽计算
│   └── portfolio/                # 验收报告、前后对照、简历 v3/v4
├── docs/                         # 证据索引、复现步骤、许可与上传清单
└── known_limitations.md          # 已知工程局限（必读）
```

## 重要声明

1. **数据性质**：全部为 `spice_simulation` / `pyvisa-sim SCPI` / `behavioral_model` / EDA 检查结果，
   不是实验室实测。
2. **失败与风险照实保留**：保护联合工况 119.8 µs（RISK）、环路带宽分离 1.86×（FAIL）、
   负载阶跃超 300 mV 限值（FAIL/过载研究）、低 SOC 误差未达标（LIMITED）。
3. **EDA 边界**：PCB 已完成布线、DRC 0 错误 0 未连接，但热、EMI、阻抗、平面完整性、
   开关节点寄生参数均未验证，不得作为投产或实际电池接线依据。详见 [known_limitations.md](known_limitations.md)。
4. **许可证**：本人原创及 AI 辅助开发的代码采用 MIT；第三方代码、数据、SPICE 模型、封装及工具
   保留各自原始许可证，详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
5. **AI 辅助**：代码整理与文档撰写使用了 AI 辅助；所有数值由仓库内脚本在本机计算，并保留原始输出。
6. **隐私**：仓库不包含密钥、令牌、账号、邮箱或个人绝对路径（上传前已做敏感信息扫描）。

## 复现

```powershell
# TestLab
conda create -n kaifa python=3.11 pip -y
conda run -n kaifa python -m pip install -r TestLab/requirements.txt -r TestLab/requirements-dev.txt
conda run -n kaifa python -m pytest TestLab/tests -q

# PowerLab（需要 ngspice DLL）
conda create -n kaifa_power python=3.11 pip -y
conda run -n kaifa_power python -m pip install -r PowerLab/requirements.txt
conda run -n kaifa_power pyspice-post-installation --install-ngspice-dll
conda run -n kaifa_power python -m pytest PowerLab/tests -q

# BatteryLab
conda create -n kaifa_battery python=3.11 pip -y
conda run -n kaifa_battery python -m pip install -r BatteryLab/requirements.txt
conda run -n kaifa_battery python -m pytest BatteryLab/tests -q
```

KiCad 部分需要 KiCad 10 与 `kicad-cli`，见 [BatteryLab/hardware/eda/review/tool_verification.md](BatteryLab/hardware/eda/review/tool_verification.md)。
完整复现步骤见 [docs/REPRODUCIBILITY.md](docs/REPRODUCIBILITY.md)。
