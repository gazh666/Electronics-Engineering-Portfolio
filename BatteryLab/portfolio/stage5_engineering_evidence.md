# BatteryLab 第五阶段工程证据（3S 保护与被动均衡）

> 所有数值来自 `results/` 下已保存的真实运行记录。
> “SPICE”一律指本机 ngspice 34 真实求解；“ECM”指冻结电池模型数值积分；
> “状态机”指离散事件仿真。三者严格区分，不互相冒充。

## 1. 本阶段做了什么

在第三阶段冻结电芯模型与第四阶段模拟采集链之上，补齐真实保护与均衡：

```text
3S 电芯模型 + 第四阶段采集
  ├─ 背靠背 N 沟道 MOSFET（低边共源，含体二极管）
  ├─ 栅极驱动（Qg / Rg / 驱动功耗）
  ├─ 逐节过压 / 欠压（迟滞 + 确认延时）
  ├─ 充电过流 / 放电过流 / 短路（三级）
  ├─ 过温 / 充电高温 / 充电低温
  ├─ 锁存状态机 + 独立充放电许可 + 合法恢复
  └─ 被动均衡（100 Ω + MOSFET）与 3S 不一致性收敛
```

## 2. 量化证据（8 列，严格区分数据类型）

| 指标 | 实际数值 | 单位 | 工况 | 数据来源 | Run ID | 原始证据 | 验证状态 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 A 放电开关压降 | 37.584 | mV | 双管导通，11.8 Ω | spice_simulation | `protection_20261126_143914_82fa77` | `switch_cases.json` | IDENTIFIED |
| 开关总导通电阻 | 37.332 | mΩ | 同上 | spice_simulation | 同上 | 同上 | IDENTIFIED |
| 单管导通电阻 | 18.666 | mΩ | 目标 20 mΩ | spice_simulation | 同上 | 同上 | IDENTIFIED |
| 充电管关断后充电电流 | 1.00 | nA | 12.6 V 充电 | spice_simulation | 同上 | `CASE_C` | IDENTIFIED |
| 放电管关断后放电电流 | 13.2 | nA | 11.8 Ω 负载 | spice_simulation | 同上 | `CASE_D` | IDENTIFIED |
| 双管关断反向漏电 | 1.00 | nA | 12.6 V 反向 | spice_simulation | 同上 | `CASE_E` | IDENTIFIED |
| 输入掉电回灌电流（双管导通） | 15.809 | A | 充电器 0 V | spice_simulation | 同上 | `CASE_F` | IDENTIFIED |
| 输入掉电回灌（放电管关断） | 13.2 | nA | 充电器 0 V | spice_simulation | 同上 | `CASE_G` | IDENTIFIED |
| 瞬态切断时间 | 574.5 | ns | 同时关断 | spice_simulation | 同上 | `turn_off_waveform.csv` | IDENTIFIED |
| 切断后残余电流 | 5.98 | µA | 2 µs 结束 | spice_simulation | 同上 | 同上 | IDENTIFIED |
| 栅极峰值电流 | 0.975 | A | 解析 1.000 A | spice_simulation | 同上 | `gate_drive.json` | IDENTIFIED |
| 栅极 10–90% 上升时间 | 44.0 | ns | Rg 10 Ω，Ceq 2 nF | spice_simulation | 同上 | 同上 | IDENTIFIED |
| 驱动功耗 | 40 | mW | 两管 @100 kHz | analytical_theory | 同上 | 同上 | IDENTIFIED |
| 过压跳闸电压 | 4.250046 | V | 配置 4.250 V | spice_simulation | `protection_20261126_143915_9a84ab` | `comparator_sweep.csv` | IDENTIFIED |
| 过压释放电压 | 4.149736 | V | 配置 4.150 V | spice_simulation | 同上 | 同上 | IDENTIFIED |
| 迟滞宽度 | 0.100310 | V | 配置 0.100 V | spice_simulation | 同上 | 同上 | IDENTIFIED |
| RC 确认延时 | 60.865 | ms | 解析 60.820 ms | spice_simulation | 同上 | `comparator_step.csv` | IDENTIFIED |
| 带迟滞抖动次数 | 1 | 次 | 2 mV RMS 噪声 3 s | behavioral_comparator_model | 同上 | `comparator_behavior.json` | IDENTIFIED |
| 无迟滞抖动次数 | 1461 | 次 | 同噪声 | behavioral_comparator_model | 同上 | 同上 | IDENTIFIED |
| 过压锁存延时 | 0.154 | s | 4.30 V | discrete_state_machine | `protection_20261126_143915_7354a8` | `protection_timeline.csv` | IDENTIFIED |
| 欠压锁存延时 | 0.154 | s | 2.70 V | discrete_state_machine | 同上 | 同上 | IDENTIFIED |
| 充电过流锁存延时 | 0.502 | s | −2.0 A | discrete_state_machine | 同上 | 同上 | IDENTIFIED |
| 放电过流锁存延时 | 0.202 | s | +5.0 A | discrete_state_machine | 同上 | 同上 | IDENTIFIED |
| 短路锁存延时 | 0.006 | s | 9.0 A | discrete_state_machine | 同上 | 同上 | IDENTIFIED |
| 过温锁存延时 | 2.005 | s | 70 ℃ | discrete_state_machine | 同上 | 同上 | IDENTIFIED |
| 自动重启次数 | 0 | 次 | 恢复后未使能 | discrete_state_machine | 同上 | `state_machine_events.csv` | IDENTIFIED |
| 均衡支路电流 | 41.783 | mA | 4.18 V，100 Ω | spice_simulation | `protection_20261126_143916_7ed424` | `balancing_spice_channels.csv` | IDENTIFIED |
| 均衡电阻功耗 | 174.58 | mW | 同上 | spice_simulation | 同上 | 同上 | IDENTIFIED |
| 均衡电阻温升 | 34.92 | ℃ | Rth 200 ℃/W | analytical_thermal_estimate | 同上 | 同上 | ESTIMATED |
| 3S 压差收敛 | 130.00 → 10.47 | mV | 12 h 静置 | ecm_simulation | 同上 | `balancing_long_run.csv` | IDENTIFIED |
| 压差收敛比例 | 91.95 | % | 同上 | ecm_simulation | 同上 | 同上 | IDENTIFIED |
| 均衡停止时间 | 28560 | s | 理想 28608 s | ecm_simulation | 同上 | 同上 | IDENTIFIED |
| 均衡耗时相对误差 | 0.17 | % | 同上 | ecm_simulation | 同上 | 同上 | IDENTIFIED |
| 累计耗散能量 | 1.339 | Wh | 12 h | ecm_simulation | 同上 | 同上 | IDENTIFIED |
| 综合检查 | 41 PASS / 0 FAIL | — | 全部模块 | mixed | `stage5_validation_20261126_143914_3f8da9` | `validation_checks.csv` | IDENTIFIED |
| 真实 SPICE 求解次数 | 12 | 次 | 预算 40 | spice_simulation | 同上 | `summary.json` | IDENTIFIED |
| Pytest | 316 passed | — | 原 257 + 新增 59 | test_suite | — | `pytest` 输出 | IDENTIFIED |

## 3. 可写进简历的诚实表述

- 设计并验证 3S 低边共源背靠背 MOSFET 充放电保护开关，真实 ngspice 测得单管
  18.7 mΩ、双向阻断残余 ≤13.2 nA、输入掉电回灌 15.8 A 可被放电管阻断。
- 实现逐节过压/欠压、充电/放电过流、短路、过温/低温保护，比较器跳闸误差 46 µV、
  迟滞误差 0.31 mV、确认延时误差 0.074%。
- 实现锁存型故障状态机，支持独立充放电许可、5 s 全清窗口、显式恢复与重新使能，
  自动重启 0 次；41 项综合检查全部通过。
- 实现被动均衡电路与 12 h 不一致性实验：压差 130 mV → 10.47 mV（91.95%），
  均衡电流 41.8 mA，电阻功耗 174.6 mW，时间与理想值偏差 0.17%。

## 4. 不可声称的内容

1. 不是真实 BQ76922 或商业保护 IC 的内部模型。
2. MOSFET 是 level-1 教学模型，不是真实器件晶体管级模型。
3. 均衡温升是一阶热阻估算，不是热仿真或实测。
4. 没有做过真实电池过充、过流、短路实验。
5. 没有 PCB、EMI、批次分布与长期漂移数据。
