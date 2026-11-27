# 68 安时积分、静置检测与 OCV 校正

日期：2026-11-26
对应源码：`estimation/coulomb_counter.py:37`、`estimation/rest_detector.py:37`、
`estimation/soc_correction.py:34`、`estimation/soc_correction.py:65`

## 1. 安时积分

```text
SOC_{k+1} = SOC_k - I_eff · Δt / (3600 · Q)
```

实现要点：

- 零阶保持：区间 `[t_k, t_k+1)` 用 `I_k`；
- 放电 `I ≥ 0` 除以放电效率，充电 `I < 0` 乘充电效率；
- 0–1 限幅是**估计器状态限幅**，每次都把原始未限幅 `raw_soc` 写入 `bound_events`；
- 不跨缺口积分。

## 2. 静置检测

静置的物理意义是"端电压 ≈ OCV"，需要同时满足：

| 条件 | 默认值 |
| --- | --- |
| `|I|` | ≤ 20 mA |
| 均衡支路电流 | ≤ 5 mA |
| 电压窗口斜率 | ≤ 2e-5 V/s（30 s 窗口） |
| 持续静置 | ≥ 300 s |
| 采样间隔 | ≤ 2 s |
| 保护 | 无异常 |
| 温度 | -20~60℃（提供时） |

300 s 的依据：冻结模型 `tau1 = 18.02 s`，5τ ≈ 90 s 已衰减 99.3%。对更大
时间常数的电芯必须重新评估，不能把 300 s 当普适常数。

## 3. 调度式校正

```text
SOC_corrected = SOC_predicted + α · (SOC_ocv - SOC_predicted)
α = 0.2
|ΔSOC| ≤ 0.02
每 60 s 最多一次
```

为什么必须按时间调度：如果每个样本都乘 α，等效时间常数会随采样率变化。
1 kHz 采样时收敛比 10 Hz 快 100 倍，这不是物理性质。

## 4. 真实动态工况的诚实结论

运行 `results/soc_estimation/run_soc_estimation_20261126_161725_90c158`：

| 数据集 | 校正次数 | 满足静置的样本 | 最后原因 |
| --- | --- | --- | --- |
| dst_50 | 0 | 0 | `VOLTAGE_NOT_STABLE` / `CURRENT_TOO_HIGH` |
| us06_50 | 0 | 0 | `CURRENT_TOO_HIGH` |

DST/US06 连续动态段没有 ≥300 s 且电压稳定的静置，因此静置校正**没有机会生效**。
这不是实现失败，而是算法适用条件不满足；报告必须如实写出。

## 5. 合成静置夹具（验证机制确实工作）

用冻结 ECM 生成"1 A 放电 600 s + 静置 1800 s"，初始估计 SOC 故意比真值低
5 pp（0.50 vs 0.55）：

| 指标 | 数值 |
| --- | --- |
| 校正次数 | 25 |
| 最终误差 | **-0.019 pp** |
| 数据来源 | `synthetic_truth` |

图：`07_rest_detection_state.png`、`08_ocv_correction_events.png`、
`08b_correction_count.png`。

## 6. 限幅掩盖误差的陷阱

us06_50 的参考 SOC 在末端接近 0，纯安时积分会先撞到 0 下限：

- 传感器失调 0 mA 时也有 **136 次**限幅；
- 正失调越大，限幅越早，末端误差被"压"成 −0.019 pp；
- 因此必须同时报告 MAE、RMSE 与限幅次数，不能只看 final error。

## 7. 设计取舍

| 取舍 | 选择 | 理由 |
| --- | --- | --- |
| 校正权重 | 固定 0.2 | 可解释、可复现；不根据测试集调 |
| 单次上限 | 0.02 | 防止一个噪声 OCV 拉飞 |
| 校正频率 | 60 s | 与采样率解耦 |
| 无静置时 | 不校正 | 宁可不修，也不用带载电压 |
| 校正后 SOC | 写回 counter | 后续积分从修正值继续 |

## 8. 常见错误

1. 每个样本都乘 0.2，误以为更快收敛。
2. 用带载端电压做校正。
3. 校正后不写回，下一次又从未校正值开始。
4. 不记录限幅，导致"末端误差很小"的假象。

## 9. 运行命令

```bash
conda run -n kaifa_battery python -m scripts.soc_correction_demo
conda run -n kaifa_battery python -m pytest tests/test_rest_detector.py tests/test_soc_correction.py -q
```

## 10. 练习与面试题

练习：

1. 把静置阈值从 300 s 改为 60 s，观察真实动态段是否开始误校正。
2. 把 `slope_window_s` 改为 5 s，观察噪声下静置判定是否抖动。

面试题：

1. 为什么固定 α 的逐样本融合会随采样率改变等效时间常数？
2. 静置检测为什么必须用电压斜率，而不能只看电流为 0？
3. 限幅记录如何帮助你识别"看似收敛、实为触底"的假象？
