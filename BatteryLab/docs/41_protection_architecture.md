# 41 第五阶段保护架构与阈值设计依据

## 1. 本阶段目标

在第三阶段冻结电芯模型和第四阶段模拟采集链之上，补齐真实的 3S 电池保护与被动均衡：

- 背靠背 N 沟道 MOSFET 充放电开关（真实 ngspice）。
- 逐节过压/欠压、充放电过流、短路、过温/低温保护。
- 带迟滞与确认延时的比较器。
- 锁存型故障状态机、合法恢复、禁止自动重启。
- 充放电独立许可与 FET 控制接口。
- 被动均衡电流、功耗、温升与 3S 不一致性收敛。

这些电路是教学工程实现，**不是 BQ76922 或任何商业保护 IC 的内部电路**。

## 2. 拓扑

```text
3S 电芯 ── BATT_N ──[CHG-FET]── CS ──[DSG-FET]── PACK_N(=SPICE 地)
   │                                              │
   └────────────── PACK_P ────────────────────────┘
                     │
        ┌────────────┴────────────┐
     负载/充电器              均衡支路（每节 100 Ω + MOSFET）
```

低边共源背靠背结构：CHG 管体二极管只允许充电方向，DSG 管体二极管只允许放电方向。
只关断一只即可阻断对应方向；两只同时关断才能双向阻断。

## 3. 阈值来源（可追溯）

| 阈值 | 取值 | 依据 |
| --- | --- | --- |
| 单体过压触发 | 4.25 V | 等于第四阶段 AFE 采集上限；高于模型参考上限 4.20 V 50 mV |
| 单体过压释放 | 4.15 V | 100 mV 回差 |
| 单体欠压触发 | 2.80 V | 高于采集下限 2.5 V；低于模型参考下限 3.0 V |
| 单体欠压释放 | 3.00 V | 200 mV 回差 |
| 充电过流 | 1.50 A | 约 0.74C，覆盖第六阶段 1 A 恒流 |
| 放电过流 | 4.00 A | 约 2C，接近第三阶段实测最大 4.002 A |
| 短路 | 8.00 A | 两方向共用，5 ms 确认 |
| 过温 | 65 ℃ / 释放 55 ℃ | 高于 NTC 量程上限 60 ℃ 的工程余量 |
| 充电温度窗 | 0–45 ℃ | 锂离子常规充电窗口 |
| 放电温度窗 | −20–60 ℃ | NTC 只在 0–60 ℃ 验证，负温部分 `NOT_VERIFIED` |
| 均衡启动 | 4.10 V 且压差 ≥30 mV | 只在接近满电时耗散 |
| 均衡停止 | 压差 ≤10 mV | 回差避免反复开关 |

阈值在加载时做强制校验：越出采集范围、回差倒置、短路阈值低于放电过流、
允许自动重启等都会抛 `ProtectionConfigError`，不会静默修正。

## 4. 关键公式

```text
过压迟滞宽度      = V_trip − V_release
确认延时          t_d = N × dt
RC 模拟延时       t_d = −τ·ln[(V_f − V_th)/(V_f − V_0)]
均衡电流          I_bal = V_cell / (R_bal + R_ds_on)
均衡功耗          P = I_bal²·(R_bal + R_ds_on)
均衡温升          ΔT = P × R_th
开关导通电阻      R_sw = 2 × R_ds_on（两只串联）
反向漏电          I_leak ≈ I_S（体二极管饱和电流）
```

## 5. 变量与单位

| 变量 | 含义 | 单位 |
| --- | --- | --- |
| `V_trip/V_release` | 触发/释放阈值 | V |
| `τ` | RC 时间常数 | s |
| `I_bal` | 均衡支路电流 | A |
| `R_th` | 热阻 | ℃/W |
| `R_ds_on` | 单管导通电阻 | Ω |

## 6. 参数来源

- 电芯容量、R0、RC、OCV：第三阶段冻结参数（CALCE 公开数据辨识）。
- 单体采集范围与 NTC：第四阶段 `configs/afe_config.yaml`。
- MOSFET/比较器/均衡参数：`configs/protection_config.yaml`，教学假设。

## 7. 源码

- `protection/limits.py`：阈值加载与校验。
- `protection/comparator.py`：迟滞 + 确认延时 + 传输延时。
- `protection/state_machine.py`：锁存状态机。
- `protection/protection_controller.py`：逐节比较与许可输出。
- `protection/balancing.py`：均衡决策与 ECM 收敛。
- `circuits/protection_mosfet.py`、`gate_driver.py`、`protection_comparator.py`、`balancing_circuit.py`：真实 ngspice。

## 8. 运行命令

```powershell
conda run -n kaifa_battery python -m scripts.battery_stage5_demo
conda run -n kaifa_battery python -m pytest tests -q
```

## 9. 常见错误

1. 把教学 MOSFET 模型说成真实器件模型。
2. 把配置阈值当作实测阈值。
3. 认为只关一只管子就能双向阻断。
4. 用均衡电流乘以组电压计算整组损耗。
5. 恢复后自动重新充电（本阶段明确禁止）。

## 10. 练习与面试题

1. 为什么保护阈值必须落在采集有效域内？
2. 过压释放点为什么不能等于触发点？
3. 背靠背 MOSFET 两只管子分别阻断哪个方向？
4. 为什么恢复后必须重新使能？
5. 被动均衡为什么只能降低高电压单体？
