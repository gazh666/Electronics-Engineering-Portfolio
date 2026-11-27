# BatteryLab_BMS_V1 人工布线操作步骤（PCB 未完成布线）

- 未连接网络：**26** 个；未连接连接点合计 **65**。
- 状态：**PARTIAL_COMPLETION**。GND 已在 F.Cu/B.Cu 铺铜，其余网络需人工布线。

## 布线前
1. 在 KiCad 10 打开 `BatteryLab_BMS_V1.kicad_pcb`。
2. 确认四层叠层：F.Cu / In1.Cu / In2.Cu / B.Cu。
3. 按 `hardware/eda/requirements/critical_net_rules.csv` 建立网络类与线宽（功率 2.0mm、Kelvin 0.25mm、栅极 0.4mm）。
4. 为 U1/U2 的 QFN 焊盘建立 0.15mm 细间距规则（解决 4 个默认 0.2mm 间距项）。

## 布线重点
- 功率路径（BAT_POS / PACK_POS / PACK_NEG、PHASE）优先、短、宽，4 层并联铜皮。
- SENSE_P / SENSE_N 从分流电阻焊盘内侧 Kelvin 引出，等长并行、远离功率回路。
- 栅极驱动回路面积最小化，靠近 DSG/CHG/HIDRV/LODRV 引脚。
- 采集 RC（47Ω/0.22µF）靠近 U1 引脚；去耦电容贴近电源脚。
- 其余 GND 通过 F.Cu/B.Cu 铺铜与缝合过孔连回 In1.Cu 地平面。

## 未完成网络清单（依据真实 DRC）

| 网络 | 未连接连接点 | 该网焊盘 |
|---|---|---|
| MID_NODE | 7 | Q1.1 Q1.2 Q1.3 Q2.5 Q2.6 Q2.7 Q2.8 Q2.9 |
| CELL_1_POS | 6 | C102.2 R103.2 R106.1 R106.2 U1.5 U1.6 U1.7 |
| BAT_POS | 5 | Q1.5 Q1.6 Q1.7 Q1.8 Q1.9 R108.1 |
| REG1_3V3 | 5 | C105.1 J3.2 R109.1 R110.1 TP3.1 U1.22 |
| GND | 4 | C104.2 C105.2 J3.1 J4.2 R107.2 R113.1 RS1.1 U1.10 U1.21 U1.25 U1.PAD |
| CELL_0_NEG | 3 | C101.1 R101.2 R107.1 U1.9 |
| CELL_0_POS | 3 | C101.2 C102.1 R102.2 U1.8 |
| CELL_2_NEG | 3 | C103.1 R104.2 U1.3 U1.4 |
| PACK_POS | 3 | J2.1 Q2.1 Q2.2 Q2.3 |
| C1P | 2 | J1.3 R103.1 R104.1 |
| CELL_2_POS | 2 | C103.2 R105.2 U1.2 |
| I2C_SCL | 2 | J3.3 R109.2 U1.17 |
| I2C_SDA | 2 | J3.4 R110.2 U1.18 |
| NTC_INPUT | 2 | J4.1 R112.2 U1.13 |
| PACK_NEG | 2 | J2.2 R114.1 RS1.2 |
| REG18 | 2 | C104.1 R112.1 U1.15 |
| SENSE_N | 2 | R114.2 TP2.1 U1.12 |
| SENSE_P | 2 | R113.2 TP1.1 U1.11 |
| BAT_AFE | 1 | R108.2 U1.1 |
| C0N | 1 | J1.1 R101.1 |
| C0P | 1 | J1.2 R102.1 |
| C2P | 1 | J1.4 R105.1 |
| CHG_GATE | 1 | Q2.4 U1.31 |
| CP1_NODE | 1 | TP4.1 U1.32 |
| DSG_GATE | 1 | Q1.4 U1.30 |
| REGIN | 1 | U1.23 U1.24 |

## 布线后
1. 重新执行 `kicad-cli pcb drc --format json --severity-all --schematic-parity`。
2. 目标：未连接=0、未解释 DRC 错误=0、一致性=0。
3. 通过后重新导出 Gerber/钻孔/STEP，并更新 release_manifest.json。
