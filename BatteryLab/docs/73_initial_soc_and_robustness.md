# 73 初始 SOC 偏差与鲁棒性矩阵

日期：2026-11-26
对应源码：`experiments/initial_soc_experiment.py`、`experiments/model_mismatch_experiment.py`、
`analysis/estimation_robustness.py`

## 1. 初始 SOC 实验设计

- 初始误差：−20 / −10 / 0 / +10 / +20 pp；
- 初始估计 SOC 必须位于 (0,1)，越界记 `NOT_EXECUTABLE`；
- 对照方法：ECM 观测器（有反馈）与安时积分（无反馈）；
- 收敛判据：|误差| ≤2 pp 连续 60 s，缺口 >2 s 重新计时。

us06_50 初始 SOC ≈ 0.5，±20 pp 全部可执行（0.30 / 0.70）。

## 2. 结果

| 初始误差 | 方法 | RMSE pp | 终值 pp | 收敛 | 耗时 s |
| --- | --- | --- | --- | --- | --- |
| −20 | ECM | 4.192 | 1.559 | CONVERGED | 1579.2 |
| −20 | 安时 | 17.132 | −0.019 | CONVERGED* | 6468.5 |
| −10 | ECM | 2.119 | 1.559 | CONVERGED | 808.7 |
| −10 | 安时 | 9.304 | −0.019 | CONVERGED* | 6468.5 |
| 0 | ECM | 1.729 | 1.559 | CONVERGED | 60.3 |
| 0 | 安时 | ~0 | ~0 | CONVERGED | 60.3 |
| +10 | ECM | 1.917 | 1.559 | CONVERGED | 254.9 |
| +10 | 安时 | 10.000 | 10.000 | NOT_CONVERGED | — |
| +20 | ECM | 2.888 | 1.559 | CONVERGED | 479.6 |
| +20 | 安时 | 20.000 | 20.000 | NOT_CONVERGED | — |

\* 安时积分的"收敛"是**下限限幅假象**：估计 SOC 先撞到 0 并停住，参考 SOC 也
接近 0，于是误差变小。它不是反馈修正。这一点必须在报告中写明。

## 3. 模型参数失配（us06_50，ECM 观测器）

| 场景 | 偏差 | RMSE pp |
| --- | --- | --- |
| 容量 | −20% | 5.860 |
| 容量 | −10% | 2.928 |
| 容量 | 0% | 0.000 |
| 容量 | +10% | 4.606 |
| R0 | −20% | 3.139 |
| R0 | 0% | 1.729 |
| R0 | +20% | 0.927 |
| RC（R1 与 τ1 同向） | −20% | 2.249 |
| RC | +20% | 1.322 |
| OCV 偏移 | −10 mV | 1.748 |
| OCV 偏移 | +10 mV | 3.748 |
| 初始极化 | ±10 mV | 1.732 / 1.726 |

解释：

- 容量偏差直接造成比例型 SOC 误差，是最敏感参数；
- 本数据集上增大 R0 反而降低误差，说明冻结 R0 相对该工况偏小；这是观察，
  不能据此回调；
- OCV 偏移 ±10 mV 使 RMSE 从 1.09 变到 3.75 pp，平台区可观测性差的直接证据；
- 初始极化 ±10 mV 影响很小，因为 τ1 ≈ 18 s，很快衰减。

## 4. S01–S24 预注册矩阵执行状态

| 编号 | 实验 | 状态 | 证据 |
| --- | --- | --- | --- |
| S01 | 正确初始 SOC | PASS | initial_soc_experiments.csv（0 pp） |
| S02 | 初始偏低 10 pp | PASS | 808.7 s 收敛 |
| S03 | 初始偏高 10 pp | PASS | 254.9 s 收敛 |
| S04 | 初始偏低 20 pp | PASS | 1579.2 s 收敛 |
| S05 | 初始偏高 20 pp | PASS | 479.6 s 收敛 |
| S06 | 电流固定失调 | PASS | sensor_error_results.csv |
| S07 | 电流增益偏差 | PASS | 同上 |
| S08 | 电流随机噪声 | PASS | 同上 |
| S09 | ADC 量化 | PASS | 同上（12 bit） |
| S10 | 电压采集失调 | PASS | model_mismatch ocv_offset |
| S11 | 容量偏差 | PASS | model_mismatch capacity |
| S12 | R0 偏差 | PASS | model_mismatch r0 |
| S13 | RC 参数偏差 | PASS | model_mismatch rc |
| S14 | OCV 低斜率区 | PASS | 129 个低斜率区间，38 样本 `LOW_OBSERVABILITY` |
| S15 | 静置校正条件不足 | PASS | 真实动态段校正 0 次，行为符合预期 |
| S16 | 数据缺失 | PASS | `test_data_gap_is_marked_and_not_integrated` |
| S17 | 温度失配 | NOT_VERIFIED | 无 0/45℃ 数据 |
| S18 | 动态充放电切换 | PASS | US06/BJDST 含充电回馈段，观测器稳定 |
| S19 | 3S 初始 SOC 不一致 | PASS | pack_soc_summary.csv |
| S20 | 3S 容量不一致 | PASS | 2.03/2.00/1.97 Ah |
| S21 | 均衡支路电流补偿 | PASS | 1.970 pp → 0.000 pp |
| S22 | CC-CV 充电 SOC | PASS | charging_summary.json，终止 SOC 85.85% |
| S23 | 保护中断 | NOT_VERIFIED | 本阶段未构造充电保护中断的 SOC 连续性实验 |
| S24 | 老化后容量更新 | NOT_VERIFIED | 无真实老化数据；合成更新数学通过 |

统计：PASS 20，NOT_VERIFIED 3（S17/S23/S24），FAIL 0。

S23 的诚实说明：第六阶段已验证过压锁存与超时保护动作，但第七阶段没有把
"保护中断期间 SOC 不积累、恢复后从实际状态继续"做成独立实验，因此不标记 PASS。

## 5. 常见错误

1. 把安时积分的触底"收敛"当成反馈有效。
2. 初始 SOC 越界时静默裁剪到 0/1。
3. 根据 R0 扫描结果回调 R0（用测试集调参）。
4. 把 S17/S23/S24 的缺失写成 PASS。

## 6. 运行命令

```bash
conda run -n kaifa_battery python -m scripts.battery_stage7_demo --profile standard
```

## 7. 练习与面试题

练习：

1. 把初始 SOC 误差设为 +30 pp，检查是否仍可执行、收敛时间如何变化。
2. 为 S23 设计一个"充电 3000 s → 保护中断 600 s → 恢复"的 ECM 实验，并说明
   SOC 在中断期间应如何变化。

面试题：

1. 为什么负初始偏差的收敛比正偏差慢？
2. 容量偏差为什么比 R0 偏差更直接地造成 SOC 误差？
3. 如何区分"算法收敛"与"状态触底"？
