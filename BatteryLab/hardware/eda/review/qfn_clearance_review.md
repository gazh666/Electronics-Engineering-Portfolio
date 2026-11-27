# QFN 细间距 DRC 审核（Task 4）

## 1. 现象
V1（网格摆放）与 V2（功能布局）在默认 0.20 mm 全局间距下，U1（BQ76922，RSN WQFN-32，0.4 mm 间距）
均出现 4 项 `clearance` 错误，DRC 实测最小间距 **0.1828 mm**：

| 焊盘对 | 网络 |
|---|---|
| U1.1 / U1.32 | BAT_AFE / CP1_NODE |
| U1.8 / U1.9 | CELL_0_POS / CELL_0_NEG |
| U1.17 / U1.16 | I2C_SCL / ALERT |
| U1.24 / U1.25 | REGIN / GND |

## 2. 原因判定
1. 不是封装错误：0.4 mm 间距、0.20 mm 焊盘宽为 TI RSN 封装与 IPC-7351B 推荐值；
2. 不是焊盘尺寸错误：0.78 × 0.20 mm 与数据手册推荐一致；
3. 是**全局规则不适用于特定细间距封装**：0.20 mm 全局间距对 0.4 mm 间距 QFN 无工艺可行性；
4. 工艺能力：常规 PCB 厂 0.15 mm 间距、精细 0.10 mm，0.1828 mm 在常规能力内。

## 3. 处理
- 仅在 U1 内部焊盘之间设置**局部 0.15 mm** 规则（`BatteryLab_BMS_V2.kicad_dru`）；
- 全局 0.20 mm 规则保持不变，未关闭任何 DRC 规则，未缩小焊盘，未排除违规；
- 处理前后真实 DRC：4 errors → **0 errors**。

```
(rule "U1 QFN-32 0.4mm fine pitch"
    (condition "A.memberOfFootprint('U1') && B.memberOfFootprint('U1')")
    (constraint clearance (min 0.15mm)))
```

## 4. 结论
该 4 项错误属于原厂封装在常规工艺下的固有间距，已用**局部规则 + 数据手册依据**处理；
全局设计规则未被降低。若未来量产，需按实际板厂能力确认 0.15 mm 阻焊桥与蚀刻补偿。
