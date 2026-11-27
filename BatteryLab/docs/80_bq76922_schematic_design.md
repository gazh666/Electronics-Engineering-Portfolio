# 80 BQ76922 原理图级设计：逐引脚、3S 通道与常见错误

日期：2026-11-26
依据：TI BQ76922 数据手册 **SLUSE86A**（2022-04 首发，2024-04 修订，76 页）。
状态：引脚级设计意图与网络分配，**没有 KiCad 原理图，没有 ERC**。

## 1. 器件与封装

| 项 | 内容 |
| --- | --- |
| 器件 | BQ76922，3S–5S 电池监测与保护 AFE |
| 封装 | RSN 32 脚 QFN，4×4 mm，带裸露热焊盘 |
| 引脚表 | SLUSE86A p.3–4 |
| 3S 配置 | SLUSE86A p.62 Table 8-3 |
| 布局要求 | SLUSE86A p.62 Layout Guidelines |
| 本设计映射 | `hardware/eda/requirements/bms_pin_mapping.csv`，33 行 |
| 完整性检查 | `pin_mapping_completeness.json`，missing=[] |

QFN 的热焊盘不是"可选焊盘"。它既是散热路径，也是地连接的一部分。本设计把 PAD
接到 GND，并要求焊接，不把 PAD 当成 NC。

## 2. 读引脚表的正确方法

引脚表最容易犯的错，是按"功能名字"猜连接。本设计坚持：每个引脚必须有唯一网络
或明确允许悬空；同名网络用 `SAME_NET_AS`；未用引脚按 Table 8-3 处理；来源页码写入 CSV。

## 3. 引脚总表（33 行）

| 脚 | 名称 | 类型 | 本设计网络 | 说明 |
| --- | --- | --- | --- | --- |
| 1 | BAT | I | BAT_AFE | 组端正极经串联二极管与 RC 后进入 |
| 2 | VC5 | IA | CELL_2_POS | 顶部电芯正端 |
| 3 | VC4A | IA | CELL_2_NEG | 顶部电芯负端，与 pin4 短接 |
| 4 | VC4B | IA | CELL_2_NEG | 与 U1.3 同网络 |
| 5 | VC3A | IA | CELL_1_POS | 未用通道，短接到 VC2 |
| 6 | VC3B | IA | CELL_1_POS | 与 pin7 同网络 |
| 7 | VC2 | IA | CELL_1_POS | 第 2 节电芯正端 |
| 8 | VC1 | IA | CELL_0_POS | 第 1 节电芯正端 |
| 9 | VC0 | IA | CELL_0_NEG | 第 1 节电芯负端，经 R/C 接 VSS |
| 10 | VSS | P | GND | 器件地与采样地单点连接 |
| 11 | SRP | IA | SENSE_P | 分流电阻靠电芯侧 |
| 12 | SRN | IA | SENSE_N | 分流电阻靠负载侧，Kelvin |
| 13 | TS1 | IO | NTC_INPUT | 外部 NTC，输入上限受 REG18+0.3 V 约束 |
| 14 | TS2 | IO | 悬空 | 保留 SHUTDOWN 时 TS2 必须悬空 |
| 15 | REG18 | O | REG18 | 内部 1.8 V LDO，2.2 µF 到 VSS |
| 16 | ALERT | IO | ALERT | 中断或 HDQ 复用，10 kΩ 上拉到 REG1 |
| 17 | SCL | IO | I2C_SCL | 400 kHz，上拉到 REG1 3.3 V |
| 18 | SDA | IO | I2C_SDA | 400 kHz，上拉到 REG1 3.3 V |
| 19 | CFETOFF | IO | CFETOFF_CTRL | 主机控制充电 FET 禁止 |
| 20 | DFETOFF | IO | DFETOFF_CTRL | 主机控制放电 FET 禁止 |
| 21 | RST_SHUT | I | GND | 不使用复位/关机时接 VSS |
| 22 | REG1 | O | REG1_3V3 | 配置 3.3 V，最大 45 mA，2.2 µF |
| 23 | REGIN | I | REGIN | REG1 LDO 输入，3.3 V 档要求 ≥4.1 V |
| 24 | BREG | O | REGIN | BREG 不用但 REGIN 使用时必须连 REGIN |
| 25 | FUSE | IO | GND | 不实现二次熔断器驱动时接 VSS |
| 26 | PDSG | O | 悬空 | 不使用预放电时保持悬空 |
| 27 | PCHG | O | 悬空 | 不使用预充电时保持悬空 |
| 28 | LD | IO | LD_SENSE | 使用 DSG 驱动时经串联电阻接 PACK+ |
| 29 | PACK | I | PACK_SENSE | 组端电压检测，1 MΩ + 0.1 µF |
| 30 | DSG | O | DSG_GATE | 高侧放电 NMOS 栅极驱动 |
| 31 | CHG | O | CHG_GATE | 高侧充电 NMOS 栅极驱动 |
| 32 | CP1 | IO | CP1_NODE | 电荷泵电容；不用时接 BAT |
| PAD | Thermal Pad | P | GND | 必须焊到板并接 GND |

## 4. 电源组：BAT、REGIN、REG18、REG1、BREG

| 引脚 | 设计连接 | 依据与约束 |
| --- | --- | --- |
| BAT (1) | 组端+ 经串联二极管与 RC | BAT 绝对最大 60 V；3S 的 12.75 V 有充足余量 |
| REG18 (15) | 2.2 µF 到 VSS | 内部 1.8 V LDO，仅内部使用，不对外供电 |
| REGIN (23) | 组端或 ≥4.1 V 输入 | 3.3 V 档要求 REGIN 不小于 4.1 V |
| REG1 (22) | 配置 3.3 V，2.2 µF | 最大 45 mA，设计预算约 5 mA（未实测） |
| BREG (24) | 连到 REGIN | BREG 不用但 REGIN 使用时必须连 REGIN |

REG18 是内部基准/LDO 节点，不是外部 1.8 V 电源；接运放或 LED 会引入额外负载
与噪声，本设计只放去耦电容。REG1 可作 I2C 上拉电源，但必须满足 45 mA 总限额，
且上拉电源与 AFE 同域；NTC 偏置必须用 REG18，见第 7 节。

## 5. 采样组：3S 的真实 VC 映射

BQ76922 的 VC 引脚不是"VC0、VC1、VC2 顺序接三节"。Table 8-3 明确要求
**cell 1、2、5 必须接真实电芯**：

| 电芯 | 正端 | 负端 | 说明 |
| --- | --- | --- | --- |
| CELL1 | VC1 (pin8) | VC0 (pin9) | 最底部电芯 |
| CELL2 | VC2 (pin7) | VC1 (pin8) | 中间电芯，与 CELL1 共享 VC1 |
| CELL3 | VC5 (pin2) | VC4A/VC4B (pin3/4) | 顶部电芯，VC4A/B 在 PCB 短接 |
| 未用 | — | VC3A/VC3B (pin5/6) | 短接到相邻 VC，本设计短到 VC2 |

节点命名用 `CELL_0_POS`、`CELL_0_NEG`、`CELL_1_POS`、`CELL_2_POS`，不把 N0–N3
直接映射成 VC0–VC3；顶部电芯必须走 VC5–VC4A。未用通道：VC3A/VC3B 短到 VC2，
VC4A/VC4B 在 PCB 短接，VC0 经 R/C 接 VSS。每个 VC 输入串 47 Ω、差分并 0.22 µF，
落在 p.7 推荐的 20–100 Ω / 0.1–0.22–1 µF 内。一阶计算 τ=20.68 µs、
fc=7696.08 Hz、100 kHz 衰减 −22.30 dB、1% 建立 95.2 µs，均为解析值。

## 6. 电流采样：SRP/SRN 与 Kelvin

| 项 | 设计 | 依据 |
| --- | --- | --- |
| 分流电阻 | WSL2010R0100FEA，10 mΩ | `shunt_comparison.csv` |
| 压降 @2.5 A | 25 mV | I×R |
| 库仑计输入范围 | ±200 mV | SLUSE86A p.11 |
| 满量程电流 | 20 A | 200 mV / 10 mΩ |
| 电流分辨率 | 0.757 mA | 7.568 µV / 10 mΩ |
| 串联电阻 | SRP/SRN 各 100 Ω | BOM R113/R114 |
| 差分电容 | 0.1 µF | 既有架构文档 |

SRP/SRN 不用时应接 VSS；本设计使用它们，因此不走"不用"分支。Kelvin 连接要求
从分流电阻焊盘内侧单独引出，采样线不承载负载电流，且与功率路径分开。

p.62 还要求分流电阻温度系数 TC ≤ 50 ppm/°C。本设计选用的 WSL2010 为
±75 ppm/°C，属于已知偏离，不能写成"满足手册建议"。

## 7. 温度通道：TS1、TS2 与 NTC 上拉约束

| 引脚 | 设计 | 约束 |
| --- | --- | --- |
| TS1 (13) | 10 kΩ NTC 分压 | 输入上限为 VREG18+0.3 V |
| TS2 (14) | 悬空 | 保留 SHUTDOWN 唤醒能力时必须悬空 |

关键约束：TS1 的输入电压不能超过 VREG18+0.3 V。因此 NTC 上拉**必须接 REG18**，
不能接 REG1 3.3 V。把 NTC 上拉到 3.3 V 会超过 TS1 的绝对最大输入，属于原理图级
错误，ERC 不一定能发现，但会在上电后损坏或误读。

BOM 中 R112 标注"10 kΩ，NTC 上拉到 REG18"，与这条约束一致。NTC 具体型号
（B 值、精度、封装）仍为 TBD，`component_database.csv` 中 NTC-001 尚未取得手册。

## 8. 通信：ALERT、SCL、SDA

SCL/SDA 为 400 kHz，各用 2.2 kΩ 上拉到 REG1 3.3 V；ALERT 用 10 kΩ 上拉。
上拉电源必须与 AFE 同域，否则关机时可能通过上拉电阻反灌。总线电容、上升时间、
地址冲突均未实测，属于 `NOT_VERIFIED`。

## 9. 驱动：CHG、DSG、PACK、LD、CFETOFF、DFETOFF、CP1

| 引脚 | 设计 | 说明 |
| --- | --- | --- |
| CHG (31) | 高侧充电 NMOS 栅极 | 与 DSG 组成背靠背高侧开关 |
| DSG (30) | 高侧放电 NMOS 栅极 | 驱动参考点为高侧源极 |
| PACK (29) | 组端电压检测 | 1 MΩ + 0.1 µF |
| LD (28) | 负载检测 | 使用 DSG 驱动时经串联电阻接 PACK+ |
| CFETOFF (19) | 主机控制充电 FET 禁止 | 上电默认电平需确认 |
| DFETOFF (20) | 主机控制放电 FET 禁止 | 上电默认电平需确认 |
| CP1 (32) | 电荷泵电容 | 不使用 CP1 时接 BAT |

第五阶段教学拓扑是低边共源背靠背，本阶段 BQ76922 是高侧驱动；两者不能混用
栅极参考与体二极管方向。CFETOFF/DFETOFF 的上电默认电平尚未完整核实，
`bms_pin_mapping.csv` 注明"需确认"，不能假设默认为低。

## 10. 其他引脚：RST_SHUT、FUSE、PDSG、PCHG、PAD

| 引脚 | 处理 | 原因 |
| --- | --- | --- |
| RST_SHUT (21) | 接 VSS | 不使用复位/关机功能 |
| FUSE (25) | 接 VSS | 不实现二次熔断器驱动 |
| PDSG (26) | 悬空 | 不使用预放电 |
| PCHG (27) | 悬空 | 不使用预充电 |
| PAD | 接 GND 并焊接 | 散热与地连接 |

"不用"不等于"随便"。RST_SHUT 与 FUSE 接 VSS 是数据手册允许的终止方式；
PDSG/PCHG 保持悬空；PAD 必须焊接。把这几个引脚全部接地，可能改变启动或
熔断器逻辑。

## 11. Table 8-3 与 p.62 布局要求

| 要求 | 内容 | 本设计落实 |
| --- | --- | --- |
| 3S 通道 | cell 1/2/5 接真实电芯 | VC1/VC0、VC2/VC1、VC5/VC4A |
| 未用 VC | 短接相邻 VC 或互连电阻 | VC3A/VC3B 短到 VC2 |
| 分流电阻 TC | ≤ 50 ppm/°C | 选 75 ppm/°C，已知偏离 |
| Kelvin | 从焊盘内侧独立走线 | 写入 `critical_net_rules.csv` |
| 采样地 | 与功率地单点连接 | 写入 GND 规则 |
| 滤波 | 靠近 AFE 引脚 | 布局约束，未布线 |

p.62 是"布局指南"，不是"布局已完成"。没有 PCB 文件，就无法证明这些要求被满足。
`layout_review.csv` 中 Kelvin、去耦位置、回流路径全部是 `BLOCKED` 或
`MANUAL_REVIEW`。

## 12. 常见错误

1. 把 N0–N3 顺序映射成 VC0–VC3，忽略顶部电芯必须走 VC5–VC4A。
2. 把 VC3A/VC3B 悬空或直接接地，而不是短接到相邻 VC。
3. VC4A 与 VC4B 分别接不同网络，未在 PCB 短接。
4. 把第五阶段的 100 Ω 外部均衡支路直接接到任意 VC 引脚。
5. 把 REG18 当外部 1.8 V 电源给 NTC 或运放供电。
6. 把 TS1 上拉到 REG1 3.3 V，超过 VREG18+0.3 V 的输入上限。
7. BREG 悬空但 REGIN 仍在用，违反"BREG 必须连 REGIN"的要求。
8. CP1 不用时悬空，而不是接 BAT。
9. SRP/SRN 不用时悬空，而不是接 VSS。
10. 保留 SHUTDOWN 唤醒却把 TS2 接固定电平。
11. 把 PAD 当 NC，不焊接、不接地。
12. 把高侧 CHG/DSG 当低边共源电路接栅极。

## 13 ERC 与 DRC 状态

本机没有 KiCad：没有 `.kicad_sch`/网表/ERC，也没有 `.kicad_pcb`/DRC。
上表 33 行只是文档级映射，不是电气连通性证明。`validation_summary.json` 中
8 项原理图/PCB 产物全部为 BLOCKED；"逐脚已检查"只能限定在文档对照这一层。

## 14 自测题

1. 为什么 3S 的顶部电芯必须接 VC5–VC4A，而不是 VC3–VC2？
   答案要点：SLUSE86A Table 8-3 规定 cell 1/2/5 接真实电芯；顶部电芯对应
   VC5 与 VC4A/VC4B，未用的 VC3A/VC3B 短接到相邻 VC。
2. TS1 的 NTC 上拉为什么不能接 3.3 V？
   答案要点：TS1 输入上限为 VREG18+0.3 V，约 2.1 V；3.3 V 上拉超过绝对最大输入。
3. REG18 为什么不能对外供电？
   答案要点：它是内部 1.8 V LDO 节点，数据手册只要求去耦，不承诺外部负载能力。
4. CP1 不使用时应该怎么处理？
   答案要点：接 BAT，不悬空。
5. 为什么高侧 CHG/DSG 不能照搬第五阶段低边共源接法？
   答案要点：栅极参考点与体二极管方向不同；高侧驱动以高侧源极为参考，
   低边共源以共源节点为参考，混用会导致驱动不足或误导通。

## 15 延伸阅读

- TI BQ76922 数据手册 SLUSE86A：<https://www.ti.com/lit/ds/symlink/bq76922.pdf>
- TI BQ76922 产品页：<https://www.ti.com/product/BQ76922>
- TI 电池管理应用笔记入口：<https://www.ti.com/power-management/battery-management/overview>
