# 104 第九阶段与本次补强验收

## 1. 验收范围

- 第九阶段：三项目联合仿真、能量守恒、TestLab 接口、系统寿命外推；
- 本次补强：AFE 预算、保护真实性、软启动/PI/抗饱和、低 SOC 分区、系统 LC 候选、有效域、EDA 状态。

## 2. 验收矩阵

| 编号 | 验收项 | 实际结果 | 判定 |
|---|---|---|---|
| V-01 | TestLab 接口 | 4/4 PASS | PASS |
| V-02 | 系统输出电压 | 4.996827 V（4.9–5.1） | PASS |
| V-03 | 系统输出纹波 | 28.978 mVpp（≤50） | PASS |
| V-04 | 电感峰值电流 | 2.2995 A（≤3.5） | PASS |
| V-05 | Buck 输入电压 | 10.5929 V（8.5–13） | PASS |
| V-06 | 能量守恒残差 | 0.002828 %（≤1 %） | PASS |
| V-07 | 变换器效率 | 93.6828 % | PASS |
| V-08 | 保护电流抑制 | 0.871 µs（独立），119.8 µs（联合） | PASS |
| V-09 | 保护 2.5 ns 伪迹 | 已识别并拒绝 | PASS（真实性问题关闭） |
| V-10 | AFE 基线最坏预算 | 30.887 mV / 37.736 mA | FAIL（未达 10 mV/20 mA） |
| V-11 | AFE 优化候选 | 3.837 mV / 6.666 mA | PASS |
| V-12 | AFE 校准后统计 | 0.8730 mV / 0.8396 mA | PASS |
| V-13 | 软启动峰值电流 | 1.0897 → 1.0562 A（5 ms） | PASS |
| V-14 | 抗饱和 CV 过冲 | 3.257 → 2.068 mV | PASS |
| V-15 | PI 带宽分离 ≥5× | 最大 1.86×，0/25 通过 | FAIL（保留） |
| V-16 | 低 SOC 分区误差 | bjdst_80 0–5 % RMSE 157.7 mV | FAIL（保留） |
| V-17 | 系统优化 LC | 纹波 21.0 mV、效率 95.206 % | PASS |
| V-18 | LC 谐振 12–17 kHz | 11.07 kHz | FAIL（保留） |
| V-19 | KiCad / 原理图 / PCB | 未生成 | BLOCKED |
| V-20 | ERC / DRC / Gerber | 未产生 | BLOCKED |
| V-21 | 硬件实测 | 未打样、未上电 | NOT_VERIFIED |
| V-22 | 真实老化循环 | 未开展 | NOT_VERIFIED |

## 3. 状态计数

- 本次硬性检查：PASS 14 / FAIL 4 / BLOCKED 2 / NOT_VERIFIED 2（上表 22 项）。
- 第八阶段 EDA 内部计数：PASS 10 / BLOCKED 9 / FAIL 1。
- 阶段 9 全部用例：历史审计记录 17/24 完成 SPICE 收敛；本次未重跑，未重算。

## 4. 事实边界

1. 所有电气指标来自 SPICE 或公开数据重放，不是硬件实测。
2. AFE 基线 30.887 mV 未达目标，属于真实 FAIL；优化候选只在器件等级参数上有依据，未打样验证。
3. PI 带宽分离与 LC 谐振两项 FAIL 保留，未通过修改限值隐藏。
4. EDA BLOCKED 需要本机 KiCad 与用户确认，不属于通过。
5. 合成寿命数据与公开实测数据严格分开，未把合成老化写成实测。

## 5. 证据索引

| 领域 | 运行目录（取该领域最新 `run_<时间戳>_<随机>`） |
|---|---|
| 基线快照 | `results/hardening/baseline/run_*/` |
| AFE | `results/hardening/afe/run_*/` |
| 保护 | `results/hardening/protection/run_*/` |
| 充电 | `results/hardening/charging/run_*/` |
| ECM | `results/hardening/ecm/run_*/` |
| 系统 | `results/hardening/system/run_*/` |
| 有效域 | `results/hardening/domain/run_*/` |
| EDA | `results/hardening/eda/run_*/` |

最终验收退出码与耗时见 `results/stage10/final_acceptance_*/acceptance.md`。
