# 26 电源工程性能指标体系

本文说明第五阶段统一的工程指标定义、计算口径与真实仿真结果。所有数值来自
`results/performance/run_20261125_143528_3011f8e8/performance_metrics.json`
（Model E，Vin=12 V，目标 5 V，D=0.4167，fsw=100 kHz，L=47 µH，C=100 µF，
ESR=30 mΩ，Rload=2.5 Ω，5 ms 瞬态）。该文件由
`analysis/performance_analyzer.py` 中的 `PerformanceAnalyzer.analyze` 生成，
数据结构定义在 `analysis/performance_models.py`。

## 1. 标称值与实际值必须分开

| 概念 | 来源 | 本项目取值 | 数据来源标记 |
| --- | --- | --- | --- |
| 标称/目标输出电压 | `configs/nonideal_buck_config.yaml` | 5.000000 V | `project_assumption` |
| 实际平均输出电压 | 真实 SPICE 稳态窗口时间加权 | 4.668158 V | `spice_derived` |
| 输出误差 | 实际平均 − 目标 | −0.331842 V | `spice_derived` |
| 输出误差百分比 | 误差 / 目标 | −6.6368 % | `spice_derived` |

5 V 是本项目设定的设计参考，不是强制 PASS 条件。`configs/performance_limits.yaml`
中的 `baseline_open_loop` 显式把 `output_voltage_target` 设为 `enabled: false`，
因此开环基线不会因为输出电压偏离 5 V 而 FAIL；这与“不得把 5 V 当强制目标”的
阶段约束一致。

输出精度按“相对目标电压的偏差”定义：

$$
\text{accuracy}=\left(1-\frac{|V_{out}-V_{target}|}{V_{target}}\right)\times100\%
=1-6.6368\%=93.3632\%
$$

注意这只是开环工况下相对配置目标的数值，不代表闭环稳压精度，也不能与
datasheet 的“输出电压精度 ±1 %”直接比较。

## 2. 平均值的统一定义

对稳态窗口 $[t_0,t_1]$ 上的波形 $x(t)$：

$$
\bar{x}=\frac{1}{t_1-t_0}\int_{t_0}^{t_1}x(t)\,dt
$$

实现位置：`analysis/time_domain.py` 的 `time_weighted_mean`，底层用梯形积分。
本项目不用 `mean(V)*mean(I)` 计算功率，因为开关波形电压与电流相位不同，
直接相乘会系统性高估或低估。

## 3. 功率与效率

端口平均功率：

$$
P=\frac{1}{t_1-t_0}\int_{t_0}^{t_1}v(t)i(t)\,dt
$$

实现位置：`analysis/power_metrics.py` 的 `compute_power_accounting`
（第四阶段已有，本阶段直接复用）。

| 指标 | 实际值 | 口径 |
| --- | ---: | --- |
| 输入功率 $P_{in}$ | 9.379313 W | V(vin)·I_in 的积分均值 |
| 驱动功率 $P_{drv}$ | 0.010580 W | (V(drv)−V(sw))·I_drv |
| 输出功率 $P_{out}$ | 8.716695 W | V(out)·I_load |
| 功率级效率 | 92.9353 % | $P_{out}/P_{in}$ |
| 系统效率 | 92.8306 % | $P_{out}/(P_{in}+P_{drv})$ |
| 总损耗 | 0.673201 W | 各器件损耗之和 |
| 功率残差 | −2.3949 µW | $P_{in}+P_{drv}-P_{out}-P_{loss}$ |
| 残差比 | −2.55×10⁻⁷ | 残差 / (输入+驱动) |

残差比只有 2.55×10⁻⁷，说明统一窗口下的功率边界闭合；残差单独报告，
从不摊派给某个器件。`configs/performance_limits.yaml` 的
`power_residual_ratio` 上限为 0.05，实测远低于限值。

## 4. 器件应力

| 指标 | 实际值 | 说明 |
| --- | ---: | --- |
| 电感电流峰值 | 2.187097 A | 窗口原始样本最大值 |
| 电感电流谷值 | 1.547831 A | 窗口原始样本最小值 |
| 电感电流 RMS | 1.876377 A | 时间加权 $\sqrt{\langle i_L^2\rangle}$ |
| 电容电流 RMS | 0.182518 A | 用于 ESR 发热评估 |
| 输入电流峰值 | 2.185397 A | 高侧开关导通段电流 |
| 输入电流 RMS | 1.217129 A | 输入电容选型依据 |

这些值来自真实节点/支路电流，不是理论公式回填。MOSFET 的 VDS 电压等级、二极管
反向电压等器件应力在第四阶段 `analysis/` 的损耗与应力模块中已有定义，本阶段
不重复定义，只在报告里读取同一套窗口数据。

## 5. 指标命名与状态

`analysis/performance_models.py` 统一定义：

- `MetricStatus`：`AVAILABLE`、`NOT_APPLICABLE`、`INVALID_DATA`、`NOT_SETTLED`、`NOT_RESOLVED`
- `DataSource`：`spice_derived`、`spice_simulation`、`analytical_theory`、`project_assumption`
- `PerformanceMetric`：名称、数值、单位、状态、来源、计算方法、说明
- `PerformanceResult`：稳态窗口、八类指标组（voltage、current、ripple、power、
  efficiency、switching、spectrum、quality）、判定、质量、频谱、谐波、原始帧

每个指标都带 `method` 字段，例如输出电压纹波写
`max-min of raw samples in window`，这样报告读者能追溯口径。

## 6. 设计目标与实测结果的边界

- 设计目标写在配置里，标记为 `project_assumption`。
- 实测值由真实 SPICE 波形积分得到，标记为 `spice_derived`。
- 理论值（如纹波解析式）标记为 `analytical_theory`，不参与 PASS/FAIL。
- 报告与 CSV 不允许把三类数据混写在同一列。

## 7. 面试题

1. 为什么平均功率要用 $\int vi\,dt$，而不能用 $\bar V\cdot\bar I$？
   开关波形中电压与电流存在相位差和非线性重叠，均值相乘会丢失相关性。
2. 功率级效率和系统效率的区别是什么？
   前者只算主功率路径，后者把栅极驱动功率也计入输入。
3. 功率残差非零说明模型错了吗？
   不一定。它可能来自数值积分误差、未建模寄生或器件模型电荷，应作为数据质量
   指标单独报告，而不是强行归零。
4. 为什么输出电压误差要同时给绝对值和百分比？
   绝对值反映控制/损耗造成的伏级偏差，百分比便于和不同电压等级比较。
5. 开环 Buck 的输出电压为什么低于 $D V_{in}$？
   因为 MOSFET 导通电阻、二极管正向压降、电感 DCR 和死区等非理想因素。
6. 如果目标 5 V 没达到，应该改限值让它 PASS 吗？
   不应该。应保留真实 FAIL 或记录为设计偏差，修改限值属于篡改结论。
