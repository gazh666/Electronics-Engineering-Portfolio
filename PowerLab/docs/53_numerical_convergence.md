# 53 时间步长、离散化与数值收敛

> 本文件说明开关级 SPICE 的时间离散、步长控制与收敛判定，并引用
> `results/stage8/experiments/timestep_convergence.json` 的真实细化实验。
> 核心结论：**最细步长只是当前可用的数值参考，不是绝对真值；数值稳定也不等于物理准确。**

## 1. 目的与范围

目的：回答三个问题——仿真结果对最大时间步长是否敏感、能否给出数值收敛阶、
如何在不虚构“真值”的前提下记录收敛状态。

范围：VAL001 工况、变体 E、稳态 5 ms；计划步长 200 / 100 / 50 / 25 / 12.5 ns。
不在范围：求解器容差（见 `docs/54`）、物理模型误差（见 `docs/51`）。

## 2. 离散化与步长

SPICE 瞬态分析把微分方程转成一系列非线性代数方程，用伴随模型（companion model）
在离散时间点上求解。步长 `h` 同时受三件事约束：

1. 输出采样间隔（`step_time_s`）：本阶段统一取 50 ns；
2. 最大允许步长（`max_step_time_s`，对应 ngspice 的 `TMAX`）：收敛实验把它从 200 ns 缩到 12.5 ns；
3. 局部截断误差（LTE）控制：ngspice 在每个时间点估计 LTE，超限就自动减小内部步长。

实验代码把 `step_time_s` 与 `max_step_time_s` 设为同一个值
（`experiments/timestep_convergence.py:53-65`），因此表格中的“最大步长”就是实际的时间网格上限。
开关周期为 10 µs（100 kHz），12.5 ns 对应每周期 800 点。

离散化误差量级可用一阶估计：

```text
e_local ≈ C · h^(p+1) · y^(p+1)   （p 为积分方法阶数）
全局误差 ≈ O(h^p)
```

因此步长减半时误差应约降为 1/2^p；这也是下面用相邻两点差值判断收敛的依据。

## 3. 收敛判据

`validation/convergence_analysis.py:85-154` 的 `check_metric_convergence` 使用：

```text
change  = |m(h_coarse) − m(h_fine)|
allowed = max(absolute_tolerance, relative_tolerance · |m(h_fine)|)
stable  = change <= allowed
```

- 只有从最细步长向粗步长连续稳定的对数 ≥ `required_pairs`（本阶段为 2）才算
  `NUMERICALLY_STABLE`；否则 `NOT_CONVERGED`（`:139-144`）。
- 少于 2 个成功点 → `INSUFFICIENT_REFINEMENT`；指标缺失或非有限 → `INVALID_DATA`；
  重复步长直接抛 `ValueError`（`:77-82`）。
- 指标级容差来自 `configs/numerical_validation.yaml:14-35`，例如 Vout 绝对 1 mV、
  纹波绝对 0.5 mV 或相对 2%、电感纹波相对 1%、总损耗绝对 0.01 W 或相对 2%。

## 4. 细化实验设计

5 个计划步长，实际 4 个成功、1 个失败：

| 最大步长 | 状态 | Vout (V) | Vpp (V) | ΔIL (A) | IL 峰值 (A) | 效率 (%) | 总损耗 (W) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 200 ns | COMPLETED | 5.011164 | 0.020044 | 0.650168 | 2.330146 | 93.3487 | 0.713969 |
| 100 ns | COMPLETED | 5.011042 | 0.019881 | 0.650030 | 2.329606 | 93.3762 | 0.714188 |
| 50 ns | COMPLETED | 5.010399 | 0.019397 | 0.649728 | 2.329342 | 93.3315 | 0.717464 |
| 25 ns | **ERROR** | — | — | — | — | — | — |
| 12.5 ns | COMPLETED | 5.010775 | 0.019482 | 0.650079 | 2.329540 | 93.3456 | 0.716171 |

25 ns 失败被原样写入 JSON（`status: ERROR`），没有插值补点、没有改参数重跑掩盖。

7 个指标的收敛状态：全部 `NUMERICALLY_STABLE`，`stable_pairs = 3`（4 个成功点形成 3 对，
全部通过），`required_pairs = 2`；总体 `overall_status = NUMERICALLY_STABLE`
（`timestep_convergence.json` 的 `analysis`）。

## 5. 收敛阶与外推

`estimate_convergence_order`（`convergence_analysis.py:157-192`）用三点 Richardson：

```text
r   = h2/h1
p   = ln[(m3 − m2)/(m2 − m1)] / ln(r)   ，要求 (m3−m2)/(m2−m1) > 0
```

实测（步长比 r = 2.0）：

| 指标 | 收敛阶 | 状态 |
| --- | --- | --- |
| Vout 均值 | −2.390 | RESOLVED |
| 输出纹波 Vpp | −1.564 | RESOLVED |
| 电感纹波 ΔIL | −1.133 | RESOLVED |
| 电感峰值 | +1.032 | RESOLVED |
| 总损耗 | −3.898 | RESOLVED |
| 系统效率 | — | `NOT_RESOLVED`（非单调/振荡） |
| 功率残差比 | — | `NOT_RESOLVED`（非单调/振荡） |

收敛阶的绝对值反映三点拟合出的误差幂次，符号取决于指标随步长变化的方向；它不是物理规律，
也不能单独用来判断“哪个结果更准”。效率的四个点 93.3487 → 93.3762 → 93.3315 → 93.3456
并非单调，功率残差比也在 +1.70e-4 → −1.41e-4 → +9.08e-6 → −1.57e-5 之间变号，
因此代码诚实地返回 `NOT_RESOLVED`，没有强行给出一个阶数。

外推值（`richardson_extrapolate`，`:195-219`）为 Vout 5.0111933 V、总损耗 0.7139527 W。
需要注意实现取的是**最粗的两个点**（200/100 ns），所以外推值更接近粗网格趋势，
与 12.5 ns 的 5.0107753 V 并不重合。JSON 的 `note` 因此写着
“extrapolated value is an estimate, not a measured truth”。

## 6. 为什么最细步长不是绝对真值

1. **非单调**：12.5 ns 的 Vout（5.010775 V）比 50 ns（5.010399 V）高 0.38 mV，
   并不在单调收敛轨迹上，说明误差还包含求解器事件处理与采样位置的影响。
2. **更细的 25 ns 直接失败**：更小步长不一定更“真”，反而更容易触发
   “Timestep too small”。
3. **收敛判据是相对当前最细值**：`allowed` 里含 `|m(h_fine)|`，稳定只证明相邻点变化小。
4. **数值稳定不含物理正确性**：即使全部稳定，Level-1 器件模型与参数估计误差仍在
   （见 `docs/51` 的 0.33 V 模型偏差）。

所以本项目的措辞是“最细步长是数值参考”，而不是“收敛到真解”。

## 7. 指标敏感性

| 指标 | 四个成功点的极差 | 相对极差 | 敏感度 |
| --- | --- | --- | --- |
| Vout 均值 | 0.76 mV | 0.015% | 低 |
| 效率 | 0.045 个百分点 | 0.048% | 低 |
| 总损耗 | 3.50 mW | 0.49% | 中 |
| 输出纹波 Vpp | 0.65 mV | 3.34% | 高 |
| 电感纹波 | 0.44 mA | 0.068% | 低 |
| 电感峰值 | 0.80 mA | 0.034% | 低 |

结论：**纹波对时间分辨率最敏感**，因为 Vpp 由极值点决定，采样相位稍有变化就会改变峰值；
Vout 与效率是积分型指标，对步长不敏感。因此报告纹波时必须同时给出步长，不能只写一个数。

## 8. 源码位置与关键接口

| 内容 | 路径 | 真实类/函数（行号） |
| --- | --- | --- |
| 数据点结构 | `validation/convergence_analysis.py` | `TimestepPoint`(23-40) |
| 单指标收敛 | 同上 | `check_metric_convergence`(85-154) |
| 阶数估计 | 同上 | `estimate_convergence_order`(157-192) |
| Richardson 外推 | 同上 | `richardson_extrapolate`(195-219) |
| 汇总 | 同上 | `analyze_convergence`(222-257) |
| 实验编排 | `experiments/timestep_convergence.py` | `run_timestep_convergence`(30-116) |
| 指标提取 | `experiments/_stage8_common.py` | `metrics_from_result`(62-83) |
| 计划与容差 | `configs/numerical_validation.yaml` | `timestep_convergence`(4-35) |

关键函数输入/输出/错误处理：

- `TimestepPoint(maximum_step_s, metrics, run_id="")`：步长必须为正、`metrics` 必须是映射，
  否则 `ValueError`。
- `analyze_convergence(points, metric_rules, required_pairs=2)`：返回 `overall_status`、
  每指标明细、排序后的点与免责说明；空结果为 `INVALID_DATA`，任一 `NOT_CONVERGED`
  或 `INVALID_DATA` 时总体为 `NOT_CONVERGED`（`:239-248`）。
- `run_timestep_convergence(...)`：单步失败只记 `ERROR` 并继续；成功点少于 2 个时返回
  `INSUFFICIENT_REFINEMENT`，不生成假收敛结论。

## 9. 图表

`results/stage8/figures/timestep_convergence.png`：横轴为最大步长（200 → 12.5 ns，反向排列），
左轴为 Vout 均值，右轴为输出纹波 Vpp；标题直接写 “not an absolute truth”。
图中 50 ns 处两条曲线都到达最低点，12.5 ns 又回升，直观展示非单调性。

## 10. 已知局限与失败案例

- 25 ns 运行失败，收敛曲线缺一个点；失败原因被保留为 ERROR。
- 收敛阶只用最粗三点估计，且要求步长比近似常数（容差 15%），不能证明全局阶数。
- 只对 VAL001/E 做了细化；其它工况的数值敏感性未逐一验证。
- 12.5 ns 的非单调说明“收敛”结论依赖所选容差；换个更严的容差可能变成 `NOT_CONVERGED`。
- 数值稳定不能替代硬件精度。

## 11. 技术面试题

1. **时间步长和输出采样间隔有什么区别？** 采样间隔决定保存哪些点；内部步长由 LTE 控制，
   受 `TMAX` 上限约束。本实验把 `step_time_s` 与 `max_step_time_s` 设为同一个值。
2. **为什么用相邻两点的变化判断收敛，而不是和解析解比较？** 开关电路没有可用的解析解；
   只能看细化是否让指标稳定，并用 Richardson 估计经验阶数。
3. **为什么 12.5 ns 的结果反而偏离 50 ns？** 误差里除离散化还有求解器事件处理与采样相位；
   更细网格不保证单调，25 ns 甚至直接失败。
4. **Vpp 为什么比 Vout 对步长更敏感？** Vpp 由极值点决定，采样相位变化会直接改变峰值；
   Vout 与效率是积分量，误差被平均掉。
5. **效率的收敛阶为什么是 `NOT_RESOLVED`？** 四个点非单调，三点比值法中
   `(m3−m2)/(m2−m1)` 不为正，代码拒绝给出阶数。
6. **Richardson 外推值能当“真值”用吗？** 不能。它基于有限点和假设的阶数，本实现还取最粗两点，
   只能作为趋势参考；JSON 明确标注“not a measured truth”。
7. **数值收敛后还需要做什么验证？** 需要模型对照、守恒检查、容差/角点分析与硬件测量；
   收敛只回答“离散误差是否受控”。
