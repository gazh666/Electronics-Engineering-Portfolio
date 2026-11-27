# 100 电池老化、容量衰减与单体不一致性

> 结论分级：VERIFIED / LIMITED / SYNTHETIC / NOT_VERIFIED。
> 本文件只陈述可追溯的既有结果，不声称本项目降低了真实电池老化速度。

## 1. 真实健康状态证据（公开数据）

| 项目 | 值 | 条件 | 证据级别 | 来源 |
|---|---|---|---|---|
| 直流内阻 DCIR | 0.07327 Ω | SP2，25 °C，充电脉冲 4.48 A，1.0 s | VERIFIED | `results/battery_health/run_battery_health_20261126_161844_389769/resistance_summary.json` |
| 参考容量 | 2.028083 Ah | SP2 单循环满放 | LIMITED（单循环） | `results/stage7/run_stage7_20261126_162211_3590e5/capacity_soh_summary.csv` |
| 容量 SOH | 100.0 % | 同上，循环 1 | LIMITED | 同上 |

说明：单循环满放只能验证容量计算链路，不能外推循环寿命。

## 2. 合成长序列（禁止当作实测老化）

| 项目 | 值 | 证据级别 | 说明 |
|---|---|---|---|
| 内阻增长终值 | +39.6 % | SYNTHETIC | `synthetic_resistance_growth.csv`，100 点线性序列 |
| 容量衰减终值 | 99.7 % SOH（-0.3 %） | SYNTHETIC | `SYNTHETIC_SP2_LIKE`，第 2–3 循环 |

`resistance_summary.json` 自身已标记 `real_growth_status = NOT_VERIFIED`，本文件沿用该状态。

## 3. 3S 单体不一致性

| 场景 | 单体最大 SOC 误差 | 组内 SOC 极差 | 证据级别 |
|---|---|---|---|
| 忽略均衡电流补偿 | 1.97 pp | 11.50 pp | LIMITED |
| 计入均衡电流补偿 | 0.00 pp | 9.53 pp | LIMITED |

来源：`results/stage7/run_stage7_20261126_162211_3590e5/pack_soc_summary.csv`。

- 上述三节电芯的初始 SOC 差异由模型构造，不是实测组内差异；
- 均衡补偿把单体最大 SOC 误差从 1.97 pp 降到 0 pp，但组内极差仍有 9.53 pp，说明补偿只修正观测，不消除真实不一致。

## 4. 结论边界

1. 真实老化实验未开展，循环寿命与内阻增长均为 NOT_VERIFIED。
2. 容量衰减、内阻增长属于电池健康状态研究结果，不是本项目对真实电池的改善。
3. 合成序列与公开实测数据在文件与字段上严格分离。
4. 低 SOC 区间（< 5 %）误差显著增大，见 `docs/104_stage9_validation.md` 的模型有效域说明与 `results/hardening/ecm/run_*/low_soc_error_by_band.csv`。
