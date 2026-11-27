# 58 设计鲁棒性、容差与性能分布

> 本文只记录第八阶段真实运行结果。数值可在
> `results/stage8/experiments/robustness.json`、`tolerance.json`、
> `corner.json`、`monte_carlo_standard.json` 与 `results/stage8/runs/<run_id>/`
> 中追溯。缺失的设计、未通过的检查、线性化筛查与开关 SPICE 的区别都按原样保留。

## 1. 目标与范围

回答五个问题：

1. 标称设计在当前功率级与控制器下的真实性能是多少？
2. 器件参数偏离标称后，闭环是否仍然稳定、指标是否仍在限值内？
3. “成对样本”比较了什么、没有比较什么？
4. 标称点改善与性能分布稳定性是不是一回事？
5. 为什么本阶段**不**针对角点重新整定控制器？

本文不覆盖：硬件实测、全局最坏情况证明、量产良率、温度与老化耦合。
外部验证统一为 `NOT_VERIFIED`（见 `results/stage8/credibility_matrix.csv`）。

## 2. 关键概念与公式

**成对比较**（同一工况、同一限值）：

```
d_i = M_candidate,i - M_baseline,i
PASS ⇔ |d_i| ≤ max(absolute_tolerance, relative_tolerance × |M_baseline,i|)
```

**最大绝对偏差**（闭环，最后 2 ms 窗口）：

```
max_dev = max_t |Vout(t) - 5.0 V|
```

**纹波**取最后 1 ms 的峰峰值。**相位裕度**判据为 `PM ≥ 45°`。

**均匀分布一阶传播**（`validation/uncertainty_analysis.py`）：

```
σ_i = (upper_i - lower_i) / √12
Var(M) ≈ Σ_i (∂M/∂p_i)² σ_i²
```

只描述“假设分布 + 一阶线性化”下的敏感度，不是厂商批次数据。

## 3. 源码位置与数据流

| 文件 | 函数/类 | 行号（约） | 作用 |
| --- | --- | --- | --- |
| `validation/robustness_analysis.py` | `compare_designs` | 27 | 成对指标比较，输出 `RB-*` 检查 |
| 同上 | `closed_loop_corner_screen` | 93 | 角点线性化稳定性筛查（平均模型） |
| 同上 | `summarize_closed_loop_screen` | 137 | 统计 evaluated/failed |
| 同上 | `unavailable_design` | 155 | 缺失设计标记 `NOT_APPLICABLE` |
| 同上 | `robustness_summary` | 164 | 指标 min/max/span 与限值违例 |
| `experiments/robustness_comparison.py` | `_closed_loop_metrics` | 32 | 从 SPICE 波形提取均值/纹波/最大偏差/峰值 |
| 同上 | `run_robustness_comparison` | 53 | 编排筛查 + 闭环 SPICE 运行 |
| `validation/corner_analysis.py` | `default_corners` | 37 | 7 个显式角点定义 |
| `validation/tolerance_analysis.py` | `one_factor_plan` | 136 | 6 参数 × 3 水平单因子计划 |

**关键函数输入/输出/错误处理**：

- `compare_designs(baseline, candidate, metric_rules=..., limit_status=...)`
  输入两个指标字典与规则（默认 Vout 绝对 0.01 V、纹波相对 5%、效率绝对 0.5 个百分点），
  返回 `ValidationCheck` 列表。任一指标缺失时返回
  `INSUFFICIENT_DATA`，不把缺失当 0。
- `closed_loop_corner_screen(config, tolerances, corners, kp, ki, target_v, phase_margin_min_deg=45)`
  为每个角点构造配置，调用 `analysis.stability_analysis.stability_report`。
  `phase_margin_deg=None` 时状态为 `NOT_RESOLVED`；低于 45° 为 `FAIL`。
  每行显式写 `data_source="averaged_model"` 与“非开关 SPICE AC”说明。
- `run_robustness_comparison(...)` 输入 profile/预算/角点数，输出
  `designs / closed_loop_screen / closed_loop_spice_runs / budget`。
  单个角点 SPICE 抛异常时保留 `status="ERROR"` 和 `failure_reason`，
  不中断整批，也不伪造指标。
- `_closed_loop_metrics` 读取 `time_s / vout_v / il_a`，输出
  `output_voltage_mean_v`、`output_voltage_ripple_vpp`、
  `maximum_absolute_deviation_v`、`inductor_current_peak_a`、`step_fallback`。

## 4 标称性能

两种控制方式不能混为一谈：

| 运行 | 控制方式 | Vout 均值 | 纹波 | 最大偏差 | IL 峰值 | 效率 | run_id |
| --- | --- | --- | --- | --- | --- | --- | --- |
| VAL001 E（理论/角点基线） | 开环固定占空比 0.4452 | 5.010399 V | 0.019397 V | — | 2.32934 A | 93.331% | `20261125_165348_649a10e6` |
| 鲁棒性 nominal | 闭环 5 V | 4.999110 V | 0.027530 V | 0.014296 V | 2.45035 A | — | `20261125_165433_dbeecc89` |

开环基线用于理论/角点/收敛统一工况；闭环验证“参数变化后控制器还能否拉住”。
闭环纹波大于开环不矛盾：占空比轨迹、软启动与工作点不同。

## 5 鲁棒性：线性化筛查 + 闭环 SPICE

### 5.1 角点稳定性筛查（平均模型，非 SPICE AC）

| 角点 | 占空比 | 相位裕度 | 带宽 | 增益裕度 | 判定 |
| --- | --- | --- | --- | --- | --- |
| nominal | 0.445201 | 64.666° | 113.605 Hz | NaN | PASS |
| low_l_high_esr | 0.445201 | 66.914° | 113.329 Hz | NaN | PASS |
| low_l_high_dcr | 0.446819 | 66.924° | 112.916 Hz | NaN | PASS |
| low_kp_high_losses | 0.447345 | 69.694° | 113.099 Hz | NaN | PASS |

`closed_loop_screen_summary`：`evaluated=4, failed=0, status=PASS`。
增益裕度记录为 `"NaN"`（未解析），不把它当成无穷大。
代码与结果都注明：这是**线性化平均模型筛查，不替代开关级 SPICE AC**。

### 5.2 闭环 SPICE 复核（2 个角点）

| 角点 | Vout 均值 | 纹波 | 最大偏差（相对 5 V） | IL 峰值 | 步长 |
| --- | --- | --- | --- | --- | --- |
| nominal | 4.999110 V | 0.027530 V | 0.014296 V | 2.45035 A | 25 ns |
| low_l_high_esr | 4.999233 V | 0.039047 V | 0.021031 V | 2.53310 A | 25 ns |

最差纹波组合下最大偏差 14.30→21.03 mV（1.47×），纹波 1.42×；
均完成，未触步长回退。

## 6 设计容差

`configs/component_tolerances.yaml` 定义 6 个参数，均为均匀分布、独立采样、
`source_type=educational_assumption`：

| 参数 | 标称 | 下限 | 上限 | 相对范围 |
| --- | --- | --- | --- | --- |
| `inductance_h` | 47 µH | 37.6 µH | 56.4 µH | ±20% |
| `capacitance_f` | 100 µF | 80 µF | 120 µF | ±20% |
| `inductor_dcr_ohm` | 0.05 Ω | 0.04 Ω | 0.06 Ω | ±20% |
| `capacitor_esr_ohm` | 0.03 Ω | 0.021 Ω | 0.039 Ω | ±30% |
| `mosfet_kp_multiplier` | 1.0 | 0.8 | 1.2 | ±20% |
| `diode_series_resistance_ohm` | 0.015 Ω | 0.012 Ω | 0.018 Ω | ±20% |

单因子实验共 `6 参数 × 3 水平 = 18 行`（低/标称/高），SPICE 实际执行。
主导参数（一阶传播）：Vout→`inductor_dcr_ohm`，IL 纹波→`inductance_h`，
效率→`inductor_dcr_ohm`。单因子不能覆盖参数联合偏移，联合效应由角点与
Monte Carlo 另算。

## 7 成对样本

`compare_designs` 设计给“标称设计 A vs 优化设计 B”的配对指标，但仓库缺少
第六阶段交付物，`run_robustness_comparison` 将 `design_b_optimized` 标为
`NOT_APPLICABLE`，`known_gaps="stage6_missing"`，没有合成基线。因此：

- 未产生任何 `RB-*` 成对改善结论；
- 已执行的是**同工况下角点 vs 标称**的配对对照（同一网表结构、同一限值）；
- 配对只说明“在这两个已执行条件上的差异”，不推出普遍更优。

## 8 性能分布对比

| 来源 | 条件 | Vout | 纹波 | 效率 |
| --- | --- | --- | --- | --- |
| Monte Carlo（27 个有效样本） | 开环、假设分布 | 均值 5.011879 V，p5 4.992889，p95 5.028845，σ 0.012503 | 均值 0.020093 V，p95 0.025959，σ 0.004178 | 均值 93.3741%，p5 93.0024%，σ 0.23818 pp |
| 7 角点 | 开环、显式极值 | 4.984263–5.029293 V | 0.016255–0.031306 V | 92.853–93.686% |
| 闭环鲁棒性 | 闭环、2 角点 | 4.999110–4.999233 V | 0.027530–0.039047 V | — |

三行不是同一控制方式的随机样本，不能直接做显著性比较：Monte Carlo 给分布
离散度，角点给显式最坏组合，闭环给“控制器在环”偏差。共同结论只有：
纹波 p95 25.96 mV 仍低于 50 mV 限值；Vout 的 p5/p95 距 ±100 mV 有裕量。

## 9 闭环参数变化

- 4 个筛查角点的相位裕度 64.666°–69.694°，带宽 112.916–113.605 Hz，
  占空比 0.445201–0.447345；全部 `STABLE / PASS`。
- 2 个闭环 SPICE 角点的 Vout 均值只差 0.12 mV，但纹波差 11.5 mV、
  最大偏差差 6.7 mV、IL 峰值差 82.8 mA——小信号裕度接近，不代表大信号纹波不变。
- 增益裕度全为 `NaN`，属未解析，不是“很高”。

## 10 “不重新整定控制器”的含义

Kp=0.0585、Ki=117.66 在角点筛查与闭环 SPICE 中**保持不变**。原因：

1. 鲁棒性验证的对象是“一个固定控制器能否覆盖容差”，逐角点改增益等于把
   被测量本身改掉，结果必然乐观；
2. 第七阶段已确认单工况下更激进的增益可能略优，但没有据此替换默认参数；
3. 角点变化应体现在相位裕度、偏差与纹波上，而不是被重新整定掩盖。

因此本文所有闭环差异都是“控制器冻结”后的真实差异。

## 11 改善与分布稳定性

- **改善**指均值/标称点移动（例如设计 B 相对 A 的配对差）。因 `stage6_missing`，
  本阶段没有改善结论可下。
- **分布稳定性**指离散度与尾部：Vout σ=12.503 mV、p5–p95 跨度 35.956 mV；
  纹波 σ=4.178 mV；效率 σ=0.238 pp；角点 Vout 跨度 45.030 mV；
  闭环最大偏差 14.3–21.0 mV。
- 只改善均值但放大方差/尾部，不算鲁棒；验收要求“均值在限值内”且“尾部在限值内”。
  当前两者同时满足，但样本量（27）与分布假设限制了外推。

## 12 证据与图表

- `results/stage8/experiments/robustness.json`（筛查 + 2 个闭环 SPICE）
- `results/stage8/runs/20261125_165433_dbeecc89/`、`..._165442_426e0b35/`
  （`circuit.cir` + `metadata.json`）
- `results/stage8/experiments/tolerance.json`、`corner.json`、
  `monte_carlo_standard.json`、`monte_carlo/samples.csv`
- 图：`results/stage8/figures/tolerance_sensitivity.png`、
  `monte_carlo_vout.png`、`corner_comparison.png`
- HTML：`results/stage8/stage8_validation_report.html`

## 13 局限

1. 筛查不是开关 SPICE AC；大信号纹波/瞬态需看 SPICE。
2. 增益裕度 `NaN`，稳定裕度只有相位维度。
3. 闭环 SPICE 只跑 2 个角点，非全角点覆盖。
4. 7 个角点有限，不证明全局最坏。
5. 容差为教学假设、独立均匀；无厂商分布/相关性/温度耦合。
6. 设计 B 缺失，未执行真正的成对改善比较。
7. Monte Carlo 3 个未收敛，统计仅 27 个有效样本。

## 14 面试题

**Q1：线性化筛查全部 PASS，为什么还要跑闭环 SPICE？**
A：筛查只在小信号工作点附近成立，忽略占空比限幅、软启动、开关纹波与大信号饱和；
瞬态偏差和纹波必须由开关级波形确认。

**Q2：为什么不在每个角点重新整定 PI？**
A：验证对象是固定控制器对容差的鲁棒性。逐角点改增益会掩盖敏感性；
整定应在设计阶段完成，验收阶段冻结。

**Q3：成对比较比两组独立统计好在哪里？**
A：同一工况、同一限值下做差可抵消共同偏置，方差更小；但它只对已执行条件成立，
不能外推未测工况。

**Q4：为什么效率的主导参数是 DCR？**
A：导通损耗与电流平方和电阻成正比，DCR 直接进入回路串联电阻；在本工况
（约 2 A）下其变化对效率的一阶贡献最大。

**Q5：增益裕度为 NaN 代表什么？**
A：JSON 只记录 `NaN`，说明该计算频段内无法给出有限 GM；这是未解析，
不是“无穷大裕度”。

**Q6：角点最坏与 Monte Carlo p95 哪个更可信？**
A：回答不同问题。角点是显式参数组合的确定性结果；Monte Carlo 是假设分布下的概率分位。
两者都不能单独证明全局最坏或量产良率。

**Q7：为什么闭环纹波可能比开环大？**
A：控制环改变占空比轨迹，软启动与工作点也不同；纹波由实际开关波形决定，
不能从开环固定占空比直接推断。
