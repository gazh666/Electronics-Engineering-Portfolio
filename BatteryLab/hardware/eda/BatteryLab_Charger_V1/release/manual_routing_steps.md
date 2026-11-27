# BatteryLab_Charger_V1 人工布线操作步骤（PCB 未完成布线）

- 未连接网络：**17** 个；未连接连接点合计 **51**。
- 状态：**PARTIAL_COMPLETION**。GND 已在 F.Cu/B.Cu 铺铜，其余网络需人工布线。

## 布线前
1. 在 KiCad 10 打开 `BatteryLab_Charger_V1.kicad_pcb`。
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
| PHASE | 11 | C204.2 L1.1 Q3.1 Q3.2 Q3.3 Q4.5 Q4.6 Q4.7 Q4.8 Q4.9 TP6.1 U2.20 |
| ADAPTER_P | 8 | C207.1 Q3.5 Q3.6 Q3.7 Q3.8 Q3.9 RS3.2 TP5.1 U2.2 |
| SENSE_P | 5 | C205.1 C206.1 L1.2 RS2.1 TP7.1 U2.14 |
| VREF_3V3 | 5 | C202.1 R203.1 R205.1 R207.1 R209.1 U2.10 |
| SENSE_N | 3 | J6.1 R202.1 RS2.2 U2.13 |
| ACSET | 2 | R207.2 R208.1 U2.16 |
| BTST | 2 | C204.1 D1.2 U2.22 |
| ISET1 | 2 | R203.2 R204.1 U2.11 |
| ISET2 | 2 | R205.2 R206.1 U2.15 |
| REGN | 2 | C203.1 D1.1 U2.18 |
| TS_NTC | 2 | R209.2 R210.1 U2.6 |
| VFB | 2 | R201.1 R202.2 U2.12 |
| ADAPTER_N | 1 | J5.2 U2.1 |
| HIDRV_GATE | 1 | Q3.4 U2.21 |
| INPUT_RAW | 1 | J5.1 RS3.1 |
| LODRV_GATE | 1 | Q4.4 U2.19 |
| TTC | 1 | C201.1 U2.7 |

## 布线后
1. 重新执行 `kicad-cli pcb drc --format json --severity-all --schematic-parity`。
2. 目标：未连接=0、未解释 DRC 错误=0、一致性=0。
3. 通过后重新导出 Gerber/钻孔/STEP，并更新 release_manifest.json。
