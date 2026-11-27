# 42 背靠背 MOSFET 充放电开关

## 1. 拓扑

低边、共源、两只 N 沟道 MOSFET：

```text
BATT_N ──D  CHG  S──┬──S  DSG  D── PACK_N
                    │
                   CS（共源）
```

- CHG 管：drain=BATT_N，source=CS，bulk=CS。
- DSG 管：drain=PACK_N，source=CS，bulk=CS。
- 体二极管：CHG 从 CS 指向 BATT_N（允许充电）；DSG 从 CS 指向 PACK_N（允许放电）。

## 2. 原理

N 沟道 MOSFET 的体二极管阳极是 source/bulk、阴极是 drain。低边共源背靠背时：

- 关断 CHG：阻断 BATT_N→CS（充电方向）。
- 关断 DSG：阻断 PACK_N→CS（放电方向）。
- 两只都关断：两个方向都无低阻通路，只剩 nA 级漏电。

因此"充满关充电管"、"放空关放电管"可以独立实现，而不需要高压侧驱动。

## 3. 真实 ngspice 模型

```text
.model NMOS_PROTECTION NMOS (LEVEL=1 VTO=2.5 KP=20 LAMBDA=0.01
                             RD=0.008 RS=0.004 IS=1e-9 CGSO=1e-9 CGDO=1e-9)
```

- `LEVEL=1` 含真实体二极管与沟道导通电阻，不是理想开关。
- `IS=1e-9` 给出 nA 级反向漏电，用于验证双向阻断。
- 栅极由 10 V 相对共源节点的 VCVS 驱动，串 10 Ω 栅极电阻、100 kΩ 下拉。

SPICE 参考地设在 PACK_N，避免整组浮空；CS 通过 1 GΩ 只定义直流工作点。

## 4. 实测结果（Run `protection_20261126_143336_1fa8a9`）

| 工况 | 结果 |
| --- | --- |
| 两管导通、11.8 Ω 负载 | 放电 1.007 A，开关压降 37.584 mV |
| 单管导通电阻 | 18.666 mΩ（目标 20 mΩ，误差 −6.7%） |
| 两管导通、12.6 V 充电 | 充电正常，开关损耗可计算 |
| CHG 关断 + 充电 | 1.00 nA，充电被阻断 |
| DSG 关断 + 负载 | 13.2 nA，放电被阻断 |
| 双管关断 + 12.6 V | 漏电 1.00 nA（限值 1 µA） |
| 输入掉电 0 V、两管导通 | 15.809 A 回灌 |
| 输入掉电、DSG 关断 | 13.2 nA，回灌被阻断 |
| 瞬态同时关断 | 574.5 ns 切断，终值 5.98 µA |

## 5. 栅极驱动

- 等效栅电容 `Ceq = Qg/Vgs = 20 nC / 10 V = 2 nF`。
- 峰值电流 `Vgs/Rg = 1 A`，SPICE 实测 0.975 A（−2.5%，源边沿 1 ns 限制）。
- 10–90% 上升时间 `2.2·Rg·Ceq = 44 ns`，SPICE 实测 44.0 ns。
- 驱动功耗 `Qg·Vgs·fsw = 20 mW/管`，两只共 40 mW @100 kHz。

## 6. 变量

| 变量 | 含义 | 单位 |
| --- | --- | --- |
| `R_ds_on` | 单管导通电阻 | Ω |
| `R_sw` | 两只串联 | Ω |
| `Qg` | 栅极电荷 | C |
| `P_drive` | 驱动功耗 | W |

## 7. 命令与产物

```powershell
conda run -n kaifa_battery python -m scripts.protection_switch_demo
```

产物：`results/protection/run_<id>/switch_cases.csv`、`turn_off_waveform.csv`、
`gate_drive.json`、`protection_switch.cir`、`plots/`。

## 8. 局限

1. 教学 level-1 模型，不是真实器件晶体管级模型。
2. 未建模米勒平台、雪崩、SOA、结温。
3. 未验证真实 PCB 寄生电感与 EMI。

## 9. 常见错误

1. 只看一个方向的电流就宣称"双向阻断"。
2. 把 37.6 mV 当成单管压降（实际是两只串联）。
3. 忽略输入掉电时电池向输入电容回灌的路径。

## 10. 面试题

1. 为什么 BMS 常用低边共源背靠背？
2. 体二极管方向如何决定哪只管子阻断哪个方向？
3. 为什么栅极驱动要以共源节点为参考？
4. 输入掉电回灌如何被阻断？
5. 导通损耗如何随电流变化？
