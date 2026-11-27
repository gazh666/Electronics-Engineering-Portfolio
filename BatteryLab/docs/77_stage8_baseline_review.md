# 77 第八阶段基线复核：真实器件、EDA 与证据边界

日期：2026-11-26
环境：Conda `kaifa_battery` / Python 3.11.18 / PySpice 1.5 / ngspice 34
阶段定位：真实半导体选型 + KiCad 原理图/PCB + 自动化硬件工程验证
结论先行：本阶段只完成**可复算的工程设计**，没有完成任何 KiCad 产物，也没有任何硬件实测。

## 1. 为什么先做基线复核

第七阶段结束时，仓库里已经有一套能跑通的电池模型、SOC 观测器和保护/充电仿真。
第八阶段第一次引入"真实器件型号"，风险不在代码，而在三件事：

1. 把数据手册的**最大值/典型值/测试条件**当成同一件事；
2. 把解析计算出来的功耗、温升当成实测；
3. 把"写了引脚映射"当成"画完了原理图"。

因此本阶段的第一份文档不是设计说明，而是证据边界说明。后续 78–84 号文档的
每个数字都必须能追溯到数据手册页码、计算结果文件或明确的 `NOT_VERIFIED`。

## 2. 前七阶段的可复现基线

| 项目 | 结果 | 证据 |
| --- | --- | --- |
| Python 解释器 | 3.11.18（conda `kaifa_battery`） | `conda run -n kaifa_battery python -V` |
| 依赖一致性 | `pip check` 干净 | `results/eda/run_stage8_20261126_165159_f06bd0/pip_check.json` |
| 第八阶段开始前测试 | `pytest tests -q` = 412 passed（62.78 s） | 本阶段基线记录（与 76 号 64.78 s 为不同次运行） |
| 第七阶段验收 | 22 项预登记 PASS，0 FAIL，6 项 NOT_VERIFIED | `docs/76_stage7_validation.md` |
| 冻结电池模型 | 一阶 RC，容量 2.0280827046460144 Ah | `data/identified/.../identified_parameters.yaml` |
| 真实数据 | CALCE 25℃ 动态工况，无老化/多温度数据 | `configs/dataset_split.yaml` |
| 版本控制 | BatteryLab 不是 git 仓库 | 无 commit 可引用 |
| KiCad | 未安装，`kicad-cli` 不在 PATH | `kicad_version.txt` = `KICAD_NOT_FOUND` |

这张表的作用是：第八阶段的所有"设计计算"都建立在一个**测试通过、依赖干净**的
软件基线上；但它不提供任何硬件精度背书。

## 3. 已有硬件资产盘点

第八阶段新增的不是一堆散落的 CSV，而是四类可核查资产：

| 目录 | 内容 | 本阶段用途 |
| --- | --- | --- |
| `hardware/eda/requirements/` | `bms_design.yaml`、`charger_design.yaml`、BMS 33 行引脚映射、充电器 25 行引脚映射、关键网络规则、接口定义、均衡评审 | 把"设计意图"固化成可审计输入 |
| `hardware/component_selection/` | 器件数据库、MOSFET/分流/电容/电感对比、降额表、封装核对表 | 把"选型"固化成可复算表格 |
| `hardware/design_review/` | 原理图评审、布局评审、FMEA、硬件验证计划 | 记录 PASS/BLOCKED/MANUAL_REVIEW |
| `eda_tools/` 与 `scripts/hardware_design_calculation.py` | 分流、RC、反馈、电感、铜箔、热一阶计算 | 生成 `design_calculations.json` |

其中 `bms_pin_mapping.csv` 为 33 行（32 引脚 + 热焊盘 PAD），`verified` 全为 `true`；
`charger_pin_mapping.csv` 为 25 行（24 引脚 + PAD）。完整性检查结果见
`pin_mapping_completeness.json`：BMS `missing_pin_numbers=[]`，充电器同样为空。

引脚映射"完整"只表示**每个引脚都有归属网络**，不表示网络在原理图中已经连通，
更不表示 PCB 已经布线。这是本阶段最容易被误读的一条。

## 4. 本阶段定位：工程设计 vs 硬件验证

| 维度 | 本阶段做了什么 | 本阶段没做什么 |
| --- | --- | --- |
| 器件选型 | 依据官方数据手册比较 MOSFET、分流电阻、电感 | 没有采购、没有来料检验 |
| 电路设计 | 引脚级网络分配、RC 参数、反馈分压、均衡路径 | 没有 KiCad 原理图文件 |
| 计算 | 解析功耗、一阶 RC、一阶热、反馈误差 | 没有热仿真、没有 Monte Carlo |
| 规则 | 关键网络宽度/间距/层偏好、Kelvin 约束 | 没有 DRC，没有实际布线 |
| 验证 | Python 自动检查 20 项 | 没有 ERC/DRC/Gerber/上电测试 |
| 结论 | `engineering_design_only` | 不是 `hardware_validated` |

`release_manifest.json` 明确写着：

```text
release_type = ENGINEERING_DESIGN_ONLY
hardware_validated = false
production_released = false
```

这不是保守措辞，而是事实状态。

## 5. 证据链与 Run ID

| 证据 | 路径 | 说明 |
| --- | --- | --- |
| 标准运行 | `results/eda/run_stage8_20261126_165159_f06bd0` | 20 项检查、BOM、引脚完整性、发布清单 |
| 设计计算 | 同上 `design_calculations.json` | 分流、RC、反馈、电感、均衡、热一阶 |
| 早期计算运行 | `results/eda/run_calc_20261126_164748_4dd611` | 同一计算脚本的独立 Run ID |
| BOM | 同上 `bom.csv`、`bom_validation.json` | BMS 26 行、充电器 25 行，issue_count=0 |
| 环境取证 | 同上 `metadata.json`、`kicad_version.txt` | `kicad_cli=null`，`KICAD_NOT_FOUND` |
| 发布清单 | 同上 `release_manifest.json` | 12 个文件逐一 SHA-256 |

`design_calculations.json` 顶部自带免责声明
`Engineering Prototype Design — Not Hardware Validated`，并且
`calculation_only=true`。任何引用该文件的图表或结论，都必须保留这两个字段的语义。

## 6. 阶段验收：10 PASS / 9 BLOCKED / 1 FAIL

| 状态 | 数量 | 含义 |
| --- | --- | --- |
| PASS | 10 | 环境、引脚完整性、设计计算、BOM、均衡功率检查等 |
| BLOCKED | 9 | 1 项 KiCad 环境 + 8 项 KiCad 产物 |
| FAIL | 1 | LC 谐振 11.07 kHz，低于 12–17 kHz 目标 |

8 项产物级 BLOCKED 来自 `blocked_items.json`：

| 产物 | 状态 |
| --- | --- |
| `BatteryLab_BMS_V1.kicad_sch` | `BLOCKED_NO_KICAD_GUI` |
| `BatteryLab_BMS_V1.kicad_pcb` | `BLOCKED_NO_KICAD_GUI` |
| `erc_raw.json` | `NOT_PRODUCED` |
| `drc_raw.json` | `NOT_PRODUCED` |
| `schematic.pdf` | `NOT_PRODUCED` |
| `gerbers/` | `NOT_PRODUCED` |
| `drill/` | `NOT_PRODUCED` |
| `board.step` | `NOT_PRODUCED` |

第 9 项 BLOCKED 是 `kicad_available` 检查本身。也就是说，BLOCKED 不是"通过"，
而是"缺少本机 KiCad GUI 或管理员权限，无法继续"。

唯一的 FAIL 是 LC 谐振频率：标称 9.4 µF 与 22 µH 得到 11.07 kHz，低于 12–17 kHz。
该项属于充电板功率级，详细分析由 84 号文档负责；本阶段**没有通过修改限值来消除 FAIL**。
另外需要说明：MLCC 在直流偏压下有效电容下降，实际谐振频率可能高于标称计算值，
但这属于 `NOT_VERIFIED`，不能拿来把 FAIL 改写成 PASS。

## 7. 本阶段的关键工程结论

1. BMS 保护路径选 2×CSD18540Q5B（60 V），组端 12.75 V 对应 21.25% 降额；
   2.5 A 时每只导通损耗 13.75 mW，合计 27.5 mW。
2. 分流电阻选 WSL2010R0100FEA（10 mΩ、0.5 W、±1%、75 ppm/°C），
   2.5 A 时压降 25 mV、功耗 62.5 mW、满量程 20 A、电流分辨率 0.757 mA。
3. 10 mΩ 的 TC 为 75 ppm/°C，超过 BQ76922 p.62 建议的 50 ppm/°C，
   这是**已知偏离**，必须靠软件温度补偿并在验收中保留。
4. 10 A 短路时 10 mΩ 直流功耗 1 W，超过 0.5 W 额定，只能依赖毫秒级保护切断；
   脉冲耐量未从数据手册提取，标 `NOT_VERIFIED`。
5. 47 Ω 单体滤波电阻同时位于均衡路径内，最坏外部功耗 200.6 mW，
   0603 常见 0.1 W 不够，必须 1206 0.25 W 或更大，且余量偏小。
6. 四款 TI NexFET 数据手册均未给出 SOA 曲线，不能用"有 SOA"来论证短路安全。

## 8. NOT_VERIFIED 清单

| 项 | 缺什么 |
| --- | --- |
| KiCad 原理图/PCB/ERC/DRC/Gerber/STEP | 本机无 KiCad，未安装、未提权 |
| 所有实物测试 | 未采购、未制板、未上电、未测温 |
| 实际板级热阻 | 只有数据手册 RθJA 条件值，无本板铜箔/气流实测 |
| 分流电阻脉冲耐量 | 未提取 WSL 脉冲曲线，短路只按直流额定判断 |
| MOSFET SOA | 四款数据手册均未提供 SOA 曲线 |
| 充电高边 30 V 器件在 32 V ACOV/PH 瞬态下的余量 | 需人工复核，`MANUAL_REVIEW` |
| NTC 具体型号与 B 值 | `component_database.csv` 中 NTC-001 仍为 TBD |
| MLCC 直流偏压后的有效电容 | 未取得 DC Bias 曲线 |
| BQ76922 保护阈值是否写入 OTP/寄存器 | 沿用第五阶段教学值，未芯片实测 |

## 9. 为什么不能宣称"完成硬件"

- 没有 `.kicad_sch`，所以没有网表，没有 ERC，没有"连接关系已检查"这一说；
- 没有 `.kicad_pcb`，所以没有 DRC，没有阻抗/回流/热铜皮验证；
- 没有 Gerber/钻孔/贴片坐标，所以没有可制造文件；
- 没有实物，所以没有精度、温升、EMI、保护动作时间；
- 引脚映射完整只证明"文档覆盖 32 个引脚"，不证明"电气正确"；
- 设计计算只证明"公式与输入一致"，不证明"器件在真实板上按公式工作"。

因此本阶段的正确表述是：**完成了真实器件的工程设计、可复算计算与验证计划，
硬件实现被 KiCad 环境阻塞**。

## 10 自测题

1. 为什么 `bms_pin_mapping.csv` 的 33 行全部 `verified=true`，仍然不能声称原理图完成？
   答案要点：verified 表示引脚表与官方引脚表逐条核对，属于文档级证据；原理图需要
   KiCad 文件、网表与 ERC，本机没有这些产物。
2. 10 PASS / 9 BLOCKED / 1 FAIL 中，BLOCKED 为什么不能计入通过率？
   答案要点：BLOCKED 表示缺少 GUI 或权限，检查未执行；把它算作通过会掩盖未完成工作。
3. 为什么不能通过降低 LC 谐振目标来消除 FAIL？
   答案要点：限值是预登记工程约束，修改限值属于伪造结果；应分析电感/电容选型或
   有效电容，保留 FAIL 并给出整改方案。
4. 分流电阻 2.5 A 时只有 62.5 mW，为什么还要讨论短路？
   答案要点：10 A 短路时直流功耗 1 W，超过 0.5 W 额定；额定功率是直流/指定条件，
   短路耐受取决于脉冲能量与保护速度，不能外推。
5. `calculation_only=true` 与 `hardware_validated=false` 分别约束了什么？
   答案要点：前者表示所有数值来自解析计算，后者表示没有实物验证；两者都不允许
   把结果描述为实测。

## 11 延伸阅读

- TI BQ76922 数据手册 SLUSE86A：<https://www.ti.com/lit/ds/symlink/bq76922.pdf>
- TI BQ24610 数据手册 SLUS892D：<https://www.ti.com/lit/ds/symlink/bq24610.pdf>
- Vishay Dale WSL 数据手册 Document 30100：<https://www.vishay.com/docs/30100/wsl.pdf>
- Bourns SRN6045 数据手册：<https://www.bourns.com/docs/Product-Datasheets/SRN6045.pdf>
- KiCad 官方下载页：<https://www.kicad.org/download/windows/>
