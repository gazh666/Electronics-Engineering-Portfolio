# 55 器件容差与灵敏度分析

本文件说明第八阶段如何量化 Buck 变换器的**器件参数容差**：标称值、容差区间、
有效容值口径、单因素偏差、温度的处理方式、独立性与相关性假设、一阶不确定度传播
以及参数灵敏度排序。所有数值来自 `results/stage8/experiments/tolerance.json`
与 `configs/component_tolerances.yaml`，不包含任何未运行的样本。

> 结论先行：容差来源是**教学假设**（`source_type: educational_assumption`，
> `manufacturer_distribution_verified: false`），不是厂商批次分布。本阶段的
> 单因素扫描只能回答“单独改一个参数会怎样”，不能替代联合分布与真实良率。

## 1. 目标与范围

- 覆盖 6 个寄生/器件参数：`L`、`C`、`DCR`、`ESR`、MOSFET `KP` 倍率、二极管 `RS`。
- 每个参数取 low / nominal / high 三个显式档位，共 18 行结果。
- 输出三类信息：单因素偏差、解析一阶传播、SPICE 单因素灵敏度。
- 不覆盖：参数相关性、温度、老化、直流偏压导致的容值下降、批次分布。

代码入口：`experiments/tolerance_experiment.py:22` 的 `run_tolerance_experiment`，
工况固定为 `VAL001`、变体 E（`Vin=12 V`、`Rload=2.5 Ω`、`D≈0.4452`、
`fsw=100 kHz`），瞬态 `end_time_s=0.005`、步长上限 `50 ns`。

## 2. 标称值与容差

| 参数 | 键名 | 标称 | 区间 | 半宽/标称 | 分布 |
| --- | --- | ---: | --- | ---: | --- |
| 电感 | `inductance_h` | 47 µH | 37.6–56.4 µH | ±20 % | uniform |
| 电容 | `capacitance_f` | 100 µF | 80–120 µF | ±20 % | uniform |
| 电感直流电阻 | `inductor_dcr_ohm` | 0.05 Ω | 0.04–0.06 Ω | ±20 % | uniform |
| 电容 ESR | `capacitor_esr_ohm` | 0.03 Ω | 0.021–0.039 Ω | ±30 % | uniform |
| MOSFET KP 倍率 | `mosfet_kp_multiplier` | 1.0 | 0.8–1.2 | ±20 % | uniform |
| 二极管串联电阻 | `diode_series_resistance_ohm` | 0.015 Ω | 0.012–0.018 Ω | ±20 % | uniform |

半宽由 `tolerance_span_percent`（`validation/tolerance_analysis.py:174`）计算：

$$
\text{span}\% = 100\cdot\frac{upper-lower}{2\cdot nominal}
$$

注意 `mosfet_kp_multiplier` 是**倍率**，`apply_parameter`
（`validation/tolerance_analysis.py:93`）把它乘到 `config.mosfet.kp_a_per_v2`
上，而不是直接替换 KP；其余 5 个参数直接替换对应字段。白名单之外的名字一律
抛 `ValueError`，避免悄悄改动未验证字段。

## 3. 有效容值口径

本阶段没有直流偏压模型、温度模型与老化模型，因此“有效容值”只等于
`capacitance_f` 在 80–120 µF 内的抽样值，**不包含** MLCC 的 DC-bias 降容、
温度系数与寿命衰减。ESR 不改变容值，只改变阻抗与纹波：

$$
Z_C(f)=\frac{1}{j2\pi fC}+ESR
$$

所以 ESR 对平均输出电压几乎无影响，却直接决定输出纹波中的 ESR 分量。这一点在
实测中非常明显：ESR 从 0.021 Ω 升到 0.039 Ω 时，`output_voltage_ripple_vpp`
从 0.013928 V 升到 0.025160 V（约 1.81 倍），而 `output_voltage_mean_v` 只从
5.010469 V 变到 5.010305 V（约 0.16 mV）。

## 4. 温度效应：本阶段未采样

必须明确：**第八阶段的 Monte Carlo 与容差实验都把温度固定在 25 °C，温度不是
随机变量**。`configs/nonideal_buck_config.yaml:84` 写死
`temperature_c: 25.0`，仿真后端默认值 `DEFAULT_TEMPERATURE_C = 25.0`
（`simulations/backend.py:26`），`component_tolerances.yaml` 中也没有温度条目。
因此本文不给出任何“温度灵敏度”数值，也不把 25 °C 的结论外推到高低温。

若后续要做温度分析，正确做法是把温度作为第 7 个因素加入配置，并让器件模型
（阈值电压、迁移率、二极管饱和电流、ESR 温度系数）随温度变化；这需要新的
模型标定，不能靠给现有结果乘一个系数得到。

## 5. 独立性与相关性

`configs/component_tolerances.yaml:50` 明确写：

```yaml
correlation_assumption: independent
manufacturer_distribution_verified: false
```

独立采样是**显式简化**。真实器件中 MOSFET 的 KP、RDS(on) 与寄生电容同属一个
工艺批次，往往相关；同一批电容的 C 与 ESR 也相关。因此：

- 单因素扫描的“只动一个参数”不代表真实批次中会出现这种组合；
- 一阶传播把各参数方差直接相加，隐含协方差为零；
- 角点分析中的“全低/全高”是人为组合，不是概率意义上的典型批次。

这些简化都写进了 `tolerance.json` 的 `disclaimer`
（“one-factor results do not cover parameter interactions”）。

## 6. 一阶不确定度传播

实现位于 `validation/uncertainty_analysis.py`：

| 函数 | 行号 | 作用 |
| --- | ---: | --- |
| `uniform_standard_deviation` | 36 | 均匀分布等效标准差 `(upper-lower)/√12` |
| `central_sensitivity` | 41 | 中心差分求 `∂metric/∂parameter` |
| `propagate_first_order` | 63 | 逐参数累加方差并给主导项 |
| `sensitivity_from_one_factor` | 118 | 用已有单因素结果做符号/量级复核 |

公式：

$$
\sigma_p=\frac{b-a}{\sqrt{12}},\qquad
\frac{\partial m}{\partial p}\approx\frac{m(p+\delta)-m(p-\delta)}{2\delta},
\qquad
\sigma_m=\sqrt{\sum_p\left(\frac{\partial m}{\partial p}\sigma_p\right)^2}
$$

其中 `delta_fraction=0.01`（标称值的 1 %）。传播使用的是平均模型解析指标
（`validation/model_cross_validation.py` 的 `averaged_metrics`），不是开关级
SPICE，因此成本低、但会漏掉开关瞬态与 ESR 纹波。

结果（`tolerance.json` → `first_order_propagation.metrics`）：

| 指标 | 标称 | σ | 相对σ | 主导参数（方差占比） |
| --- | ---: | ---: | ---: | --- |
| 输出电压均值 | 4.99999999993 V | 0.011524 V | 0.2305 % | DCR（95.80 %），DRS（2.65 %），KP（1.55 %） |
| 电感电流纹波 | 0.663065 A | 0.076580 A | 11.55 % | L（99.98 %） |
| 系统效率 | 93.59078 % | 0.215699 % | 0.2305 % | DCR（95.80 %） |

在解析平均模型中 `capacitance_f`、`capacitor_esr_ohm`、`inductance_h` 对
**输出电压均值**的灵敏度为 0，这是因为 `averaged_metrics` 的稳态公式只通过
DCR/二极管压降/KP 影响均值。这是模型口径，不是“电容完全无影响”——开关级
SPICE 中 L 与 C 对纹波的影响是明确的（见下一节）。该结构也写入了 JSON 的
`note`：**“not a confidence interval and not a yield estimate”**。

## 7. 单因素灵敏度与主导参数

`one_factor_sensitivity` 用 SPICE 18 行结果计算
`sensitivity = (metric - nominal_metric) / (value - nominal_value)`，单位随参数
变化（例如 V/F、V/H、V/Ω），因此**原始数值排序不能跨参数直接比较**：

```
ranking (raw): capacitance_f, inductance_h, inductor_dcr_ohm,
               diode_series_resistance_ohm, mosfet_kp_multiplier, capacitor_esr_ohm
```

`capacitance_f` 的 `mean_sensitivity≈-4.645 V/F` 看似最大，只是因为电容以 F
为单位数值很小（4×10⁻⁵ F 的扰动），乘上等效 σ 后贡献可忽略。按上一节的
**归一化方差贡献**排序，输出电压与效率的主导参数都是 `inductor_dcr_ohm`。
这是本文刻意保留的方法学差异：看原始灵敏度会误判，看方差贡献才与物理一致。

SPICE 单因素实测（每行 `data_source="spice_simulation"`）：

| 参数 | Vout low / high (V) | 输出纹波 low / high (V) | 效率 low / high (%) |
| --- | --- | --- | --- |
| L | 5.010370 / 5.010443 | 0.024195 / 0.016226 | 93.33695 / 93.34851 |
| C | 5.010492 / 5.010307 | 0.019693 / 0.019503 | 93.32907 / 93.33921 |
| DCR | 5.029948 / 4.990960 | 0.019346 / 0.019521 | 93.71958 / 92.97626 |
| ESR | 5.010469 / 5.010305 | 0.013928 / 0.025160 | 93.33710 / 93.32895 |
| KP | 5.006864 / 5.013107 | 0.020170 / 0.019769 | 93.26343 / 93.37175 |
| DRS | 5.013829 / 5.007579 | 0.019339 / 0.019360 | 93.42379 / 93.31206 |

标称行：`Vout=5.010399 V`、`ripple=0.019397 V`、`eff=93.33146 %`。

可以读出三个“主导”关系：

1. **输出电压与效率 → DCR**：DCR 从 0.04 Ω 到 0.06 Ω，Vout 变化约 39 mV，
   效率从 93.72 % 降到 92.98 %（`dcr_loss_w` 从 0.163 W 升到 0.241 W）。
2. **电感电流纹波与输出电压纹波 → L**：L 在 ±20 % 区间内变化时，电感电流纹波
   从标称 0.650 A 变为 0.812 A（low）/0.542 A（high），输出电压纹波 0.024195 V
   （low）/0.016226 V（high）。
3. **输出纹波中的 ESR 分量 → ESR**：`output_voltage_esr_ripple_vpp` 从
   0.013530 V 升到 0.024957 V，几乎线性跟随 ESR。

18 行中 nominal 被 6 个参数复用同一次运行（`reused_nominal: true`，
`run_id=20261125_165333_52d6bf88`），因此实际是 13 次不同参数的 SPICE 运行。
JSON 的 `budget.spice_runs=36` 是**跨任务共享的累计计数器**
（`validation/validation_runner.py:94` 只创建一个 `BudgetCounter` 并传给所有
任务），不能当作本实验单次运行数。

## 8. 输入、输出与错误处理

- 输入：`configs/component_tolerances.yaml`（6 参数）、`VAL001` 参考工况
  （`validation/reference_cases.py`）。
- 输出：`results/stage8/experiments/tolerance.json`；每次 SPICE 运行的
  `results/stage8/runs/<run_id>/`（`circuit.cir`、`metadata.json`、
  `metrics.json`）；图 `results/stage8/figures/tolerance_sensitivity.png`。
- 校验：`ParameterTolerance.__post_init__`（`validation/tolerance_analysis.py:41`）
  要求 `lower ≤ nominal ≤ upper`、数值有限、参数名在白名单、分布受支持；
  `apply_parameter` 要求值有限且为正；`load_component_tolerances`（第 74 行）
  在 YAML 缺少 `parameters` 映射时抛 `ValueError`。
- 失败处理：若 nominal 运行失败，实验直接返回 `status="ERROR"` 的载荷
  （`tolerance_experiment.py:47`）；单参数运行失败则保留该行
  `status="ERROR"` 与 `failure_reason`，不删除、不补数。本次 18 行全部
  `COMPLETED`，没有隐藏失败。

## 9. 已知局限

1. 容差是教学假设，没有厂商批次数据；不能据此宣称“满足某型号规格”。
2. 单因素扫描不覆盖参数交互；`disclaimer` 已写明。
3. 无温度采样、无 DC-bias/老化降容，25 °C 结论不可外推。
4. 一阶传播是局部线性、独立假设，只用于排序与量级，不是置信区间或良率。
5. 解析模型的 C/ESR/L 对均值灵敏度为 0，与开关级结果的口径不同，不能混用。
6. 原始单位灵敏度排序会误导；归一化贡献才可比。

## 10. 面试题

**Q1：为什么均匀分布的等效标准差是 `(b-a)/√12`？**
均匀分布方差为 `(b-a)²/12`，标准差即开方；它把“区间宽度”折算成可与正态
传播公式对接的 σ，但样本仍按均匀分布抽取。

**Q2：一阶传播为什么不能当置信区间？**
它假设局部线性、参数独立、扰动足够小，并把输出近似为正态；本项目的输出
（纹波、峰值电流）在开关瞬态下并非线性可加，且没有协方差项，因此只能排序。

**Q3：为什么 DCR 主导 Vout 而 ESR 主导纹波？**
DCR 与电感电流的直流分量相乘形成持续压降，直接抬高/压低平均值；ESR 只与
交流纹波电流相乘，平均值近似为零，所以影响纹波而非均值。

**Q4：单因素扫描能否证明设计鲁棒？**
不能。它只覆盖 6 条一维切片，不能覆盖 2⁶ 组合、内点和相关性；鲁棒性需要
角点、Monte Carlo 与实测共同支撑。

**Q5：为什么电容 ±20 % 对 Vout 影响远小于 DCR？**
稳态占空比由输入/输出与导通压降决定，容值只改变充放电斜率与纹波幅度；
本实验是固定占空比开环，容值不改变直流工作点。

**Q6：如果要加入温度，最小改动是什么？**
把温度作为第 7 个采样维度写入 YAML，并让器件模型参数随温度变化，然后重新
标定与采样；仅给结果乘系数是伪分析。
