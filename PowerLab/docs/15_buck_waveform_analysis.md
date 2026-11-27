# 15 Buck 波形分析：启动、稳态与纹波

本文基于真实 ngspice 波形解释分析流程与实测结果。默认工况为
Vin=12 V、D=5/12、fsw=100 kHz、L=47 µH、C=100 µF、R=2.5 Ω、仿真 5 ms。

## 1. 启动过程

开环 Buck 没有软启动，电容从 0 V 开始充电，电感电流先出现较大冲击。

| 指标 | 实测值 |
| --- | --- |
| 输出峰值电压 | 7.8463 V |
| 相对稳态参考值的超调 | 3.0649 V（64.1%） |
| 电感峰值电流 | 7.7124 A |
| 相对额定 2 A 的倍数 | 3.86× |
| 输出电压稳定时间 | 1.4136 ms |
| 电感周期平均电流稳定时间 | 1.715 ms |

稳定判据：输出电压进入参考值 ±max(10 mV, 2%) 并保持至少 0.5 ms；电感电流先按完整
PWM 周期求时间加权平均，再要求 5% 相对 + 0.02 A 绝对误差带。逐点判断电感电流会
被开关纹波本身触发，因此不能直接用瞬时值。

图：[startup_output_voltage.png](file:///PowerLab/results/buck/run_20261125_114918_5421128c/plots/startup_output_voltage.png)、
[startup_inductor_current.png](file:///PowerLab/results/buck/run_20261125_114918_5421128c/plots/startup_inductor_current.png)。

## 2. 稳态窗口识别

实现位置：[steady_state.py](file:///PowerLab/analysis/steady_state.py)
`identify_steady_state()`。

流程：

1. 用真实 gate 阈值交点切分完整开关周期；
2. 要求至少 20 个完整周期；
3. 取最后 20 个周期，前后各 10 个周期比较；
4. 平均电压、平均电感电流变化 ≤ 0.1%（含 1 mV / 1 mA 绝对容差）；
5. 周期纹波变化 ≤ 5%（含 0.5 mV 绝对容差）。

默认工况判定为 `STEADY_STATE`：

| 项目 | 实测 |
| --- | --- |
| 稳态窗口 | 4.79001 ms – 4.99001 ms |
| 完整周期 | 20 |
| 电压均值变化比 | 1.68e-5 |
| 电流均值变化比 | 6.16e-5 |
| 纹波变化比 | 5.44e-4 |

窗口内的波形另存为 `steady_state_waveform.csv`。不在窗口内强行计算纹波，避免把
启动上升沿误当成开关纹波。

## 3. PWM 波形

分析位置：[buck_waveforms.py](file:///PowerLab/analysis/buck_waveforms.py)
`analyze_pwm_waveform()`。

- 阈值：`(0 + 5)/2 = 2.5 V`；
- 用相邻采样点线性插值求上升/下降交点；
- 只统计「上升沿 → 下降沿 → 下一个上升沿」的完整周期；
- 首尾不完整脉冲自动丢弃。

实测：频率 99999.99999999999 Hz，占空比 0.41666666666667407，完整周期 499 个。
与配置值一致到浮点舍入量级。

## 4. 开关节点电压

`switch_node_v = V(sw)`。开关导通时接近 12 V（减去开关与采样源压降），关断时被
二极管钳位在约 0 V 附近。实测最大值 > 11 V、最小值 < 1 V，说明开关与续流路径
均真实工作。图：[switching_waveforms.png](file:///PowerLab/results/buck/run_20261125_115042_d4dd77aa/plots/switching_waveforms.png)。

## 5. 电感电流与输出纹波

稳态窗口实测：

| 指标 | 理论（理想 CCM） | SPICE | 相对差异 |
| --- | --- | --- | --- |
| 输出平均电压 | 5.000 V | 4.7813 V | -4.37% |
| 平均电感电流 | 2.000 A | 1.9126 A | -4.37% |
| 电感峰值电流 | 2.3103 A | 2.2327 A | -3.36% |
| 电感谷值电流 | 1.6897 A | 1.5925 A | -5.75% |
| 电感纹波 | 0.6206 A | 0.6402 A | +3.17% |
| 输出纹波 | 7.757 mV | 8.139 mV | +4.92% |

差异来自：

- 开关 `RON=1 mΩ` 与二极管正向压降使实际占空比-电压关系低于 `D·Vin`；
- 二极管理想因子/串联电阻使续流段并非理想 0 V；
- 纹波公式忽略 ESR/ESL 与开关瞬间细节；
- ngspice 非均匀采样与数值容差。

这些差异均在 `configs/buck_validation.yaml` 的限值内（电压 10%、电感纹波 15%、
输出纹波 25%），不构成验证失败。

## 6. 非均匀时间采样

ngspice 的自适应步长使时间轴非均匀。默认 5 ms 运行的步长统计：

| 指标 | 数值 |
| --- | --- |
| 采样点 | 118512 |
| 最小步长 | 2.27e-10 s |
| 最大步长 | 5.0e-8 s |
| 平均步长 | 4.22e-8 s |
| 中位步长 | 5.0e-8 s |
| 最大步长约束 | 50 ns，已遵守 |

因此所有平均值使用梯形积分 `∫x dt / ∫t`，而不是简单算术平均；切窗时在边界
线性插值补点，保证积分区间与所选周期严格一致。

## 7. 波形数据质量

`SimulationResult.metadata["quality"]` 检查：

- 时间轴严格递增；
- 所有数值有限（无 NaN/Infinity）；
- 各列长度与时间轴一致。

验证报告中的 `waveform_data_quality` 项直接引用该结果，失败时不会标记 PASS。

## 8. 理论与 SPICE 的边界

- 理论值单独写入 `theoretical_results.json`，`data_source = analytical_theory`；
- 波形与指标写入 `spice_results.json`，`data_source = spice_simulation`；
- 对照写入 `comparison.json`，`data_source = comparison`。

三者不混用，也不把理论公式结果冒充仿真结果。
