# 52 理论公式与 SPICE 的对照方法

> 本文件逐项说明理想 CCM 公式、非理想 CCM 近似、CCM/DCM 适用性、误差指标与波形对齐，
> 并引用 `results/stage8/experiments/theoretical_comparison.json` 的真实对照结果。
> 理论量一律标记 `analytical_theory`，SPICE 量一律标记 `spice_simulation`，
> 对照结果标记 `comparison`，三者不混用。

## 1. 目的与范围

目的：给出“公式算出来的数”与“开关级 SPICE 算出来的数”如何被公平比较的规则：
先确认公式适用，再对齐统计口径，最后用绝对/相对误差与限值判定。

范围：5 个统一工况（VAL001–VAL005，变体 C/E），稳态 5 ms，步长 50 ns。
不在范围：瞬态恢复时间、环路稳定性、硬件精度（见 `docs/51`、`docs/50`）。

## 2. 模型层级

| 层级 | 模型 | 数据来源 | 是否含纹波 | 是否含开关损耗 |
| --- | --- | --- | --- | --- |
| A | 理想解析 CCM | `analytical_theory` | 否 | 否 |
| B | 平均状态空间 | `averaged_model` | 否（周期平均） | 否（只含导通/二极管损耗） |
| C | 开关 SPICE（受控开关） | `spice_simulation` | 是 | 是 |
| D/E | 非理想 MOSFET SPICE | `spice_simulation` | 是 | 是 |

层级定义在 `validation/model_cross_validation.py:40-77` 的 `MODEL_LEVELS`。
交叉验证统一以 D（变体 E）为参考，但“更详细”不等于“真实硬件”（同文件 `:9`）。

## 3. 公式

### 3.1 理想 CCM（`analysis/buck_theory.py:88-123`）

```text
Vout      = D·Vin
ΔIL       = (Vin − Vout)·D / (L·fs)
ΔVpp      = ΔIL / (8·fs·C)
Iout      = Vout / Rload
Icrit     = ΔIL / 2 ,   Rcrit = Vout / Icrit
CCM 条件   = (Iout − ΔIL/2) > 0
```

DCM 理想变换比（`buck_theory.py:126-143`）：

```text
K = 2L/(Rload·T) ,  T = 1/fs
M = Vout/Vin = 2 / (1 + sqrt(1 + 4K/D²)) ,  仅当 K < 1 − D
```

### 3.2 非理想 CCM 近似（`validation/theoretical_validation.py:61-95`）

MOSFET 导通电阻用 Level-1 平方律估计（`validation/reference_cases.py:92-106`）：

```text
Rds(on) ≈ 1 / [KP·(W/L)·(VGS − VTO)] + RD + RS
```

二极管压降用 Shockley 方程并叠加串联电阻（`reference_cases.py:109-124`）：

```text
Vt  = k·T/q            (k=1.380649e-23, q=1.602176634e-19)
VF  = n·Vt·ln(I/IS) + I·Rs_diode
```

恒阻负载下的非理想稳态式：

```text
Vout = [D·Vin − (1−D)·VF] / [1 + (D·Rds + DCR)/Rload]
ΔIL  = (Vin − Vout)·D / (L·fs)
```

平均模型另用 ESR 把电容电压映射到端电压（`docs/42` 第 3.2 节）：

```text
vout = (vC + rESR·iL) / (1 + rESR/Rload)
```

### 3.3 CCM / DCM 适用性

判定以**实测电感电流谷值**为准，而不是只看配置：`evaluate_theory`
（`theoretical_validation.py:212-218`）用 `valley > 0` 决定 CCM 公式是否适用；不适用时
7 项检查全部返回 `NOT_APPLICABLE`。配置层的辅助判断在 `theory_applicability`
（同文件 `:312-321`）。

### 3.4 误差指标

```text
absolute_error = actual − reference
relative_error = (actual − reference) / |reference| × 100%
allowed        = max(abs_tol, rel_tol · |reference|)
```

MAE / RMSE 用于逐点波形比较（`analysis/error_metrics.py:67-81` 的 `calculate_error_metrics`）：

```text
MAE  = mean(|e_k|)
RMSE = sqrt(mean(e_k²))
```

时间加权版本 `MAE_time = ∫|e|dt / ∫dt`、`RMSE_time = sqrt(∫e²dt/∫dt)`
（`error_metrics.py:98-140` 的 `time_weighted_error_metrics`）。本阶段的稳态对照只用绝对/相对误差与限值；
MAE/RMSE 用于连续波形（如 RC/RL 瞬态与纹波重建）。

### 3.5 波形对齐

不同仿真的时间网格不同，直接逐点相减会把采样误差当成模型误差
（`validation/waveform_alignment.py:1-6`）：

- `common_interval`（`:53-60`）：取两条波形的公共时间区间，无重叠抛 `ValueError`。
- `align_waveforms`（`:63-94`）：在公共区间线性插值到统一网格（默认 2000 点），
  返回 `AlignmentResult` 与 `max_time_shift_s`。
- `alignment_is_usable`（`:152-159`）：要求公共区间非空且时间偏移占比 ≤ 1%。
- `pwm_cycle_average` / `cycle_mean_waveform`（`:107-149`）：按开关周期做相位平均或逐周期均值，
  让平均模型能在“周期平均”口径下比较；这不是开关波形的替代品。

## 4. 源码位置与关键接口

| 内容 | 路径 | 真实类/函数（行号） |
| --- | --- | --- |
| 理想 CCM | `analysis/buck_theory.py` | `calculate_ideal_buck`(88)、`calculate_ideal_dcm`(126) |
| 理想理论包装 | `validation/theoretical_validation.py` | `ideal_ccm_theory`(32-58) |
| 非理想理论 | 同上 | `nonideal_ccm_theory`(61-95) |
| 检查构造 | 同上 | `make_check`(121-191) |
| 理论对照 | 同上 | `evaluate_theory`(194-309) |
| Rds(on) / VF 估计 | `validation/reference_cases.py` | `mosfet_rds_on_estimate`(92)、`diode_forward_voltage_estimate`(109) |
| 占空比校准 | 同上 | `calibrated_duty_for_case`(152)、`build_case_config`(161-176) |
| 四层模型矩阵 | `validation/model_cross_validation.py` | `MODEL_LEVELS`(40)、`model_matrix`(108)、`cross_validate`(152) |
| 实验编排 | `experiments/theoretical_comparison.py` | `run_theoretical_comparison`(36-131) |
| 误差指标 | `analysis/error_metrics.py` | `calculate_error_metrics`(67)、`time_weighted_error_metrics`(98) |

关键函数输入/输出/错误处理：

- `nonideal_ccm_theory(config)`：输入 `NonidealBuckConfig`，输出 Vout、Iout、ΔIL、峰值/谷值、
  `rds_on_ohm`、`diode_forward_v`、`dcr_ohm` 与 `formula`；不做适用性判断。
- `evaluate_theory(measured, theory, limits=None, case=None)`：`measured` 必须包含
  Vout 均值、纹波、峰谷电流等键；非 dict 抛 `ValueError`；谷值缺失或不正时把 7 项检查标为
  `NOT_APPLICABLE`；非有限值标 `ERROR`。
- `run_theoretical_comparison(cases=None, budget=None, save=True, profile="standard")`：
  逐工况逐变体运行 SPICE（50 ns、5 ms），单变体失败时该工况记 `PARTIAL`/`ERROR`，
  不中断整批；返回 JSON 并写 `results/stage8/experiments/theoretical_comparison.json`。
- `cross_validate(rows, reference_key="D_MOSFET_SPICE")`：参考层缺失时返回
  `INSUFFICIENT_DATA`；平均模型的纹波与效率对照强制 `NOT_APPLICABLE`（`:220`、`:237`）。

## 5. 真实对照结果

### 5.1 工况与理论值

| 工况 | Vin (V) | Rload (Ω) | 校准占空比 | 理想 Vout (V) | 非理想 Vout (V) | 理想 ΔIL (A) | 理想 Vpp (V) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| VAL001 | 12 | 2.5 | 0.445201 | 5.3424 | 5.0000 | 0.6306 | 0.007883 |
| VAL002 | 9 | 2.5 | 0.587890 | 5.2910 | 5.0000 | 0.4639 | 0.005799 |
| VAL003 | 16 | 2.5 | 0.336351 | 5.3816 | 5.0000 | 0.7599 | 0.009499 |
| VAL004 | 12 | 5.0 | 0.440397 | 5.2848 | 5.0000 | 0.6292 | 0.007865 |
| VAL005 | 12 | 50 | 0.436088 | 5.2331 | 5.0000 | 0.6279 | 0.007848 |

占空比由 `solve_operating_duty`（平均 CCM 模型）以 5 V 为目标反解，属于
`project_assumption`；因此非理想 Vout 全部精确等于 5.0000 V，这是校准结果，不是独立预测。

### 5.2 VAL001 逐项检查（限值：Vout 2% + 20 mV，ΔIL 5%，Vpp 30%）

| 检查 | 变体 C | 变体 E | 参考 | 结论 |
| --- | --- | --- | --- | --- |
| Vout vs 理想 | 5.0179（−6.07%） | 5.0104（−6.21%） | 5.3424 | FAIL |
| ΔIL vs 理想 | 0.6519（+3.38%） | 0.6497（+3.03%） | 0.6306 | PASS |
| 峰值 vs 理想 | 2.3333（−4.85%） | 2.3293（−5.01%） | 2.4523 | PASS |
| Vpp vs 理想 | 0.019407（+146.2%） | 0.019397（+146.1%） | 0.007883 | FAIL |
| Vout vs 非理想 | 5.0179（+0.36%） | 5.0104（+0.21%） | 5.0000 | PASS |
| 平均电流 vs 非理想 | 2.0133（+0.66%） | 1.9971（−0.14%） | 2.0000 | PASS |
| ΔIL vs 非理想 | 0.6519（−1.68%） | 0.6497（−2.01%） | 0.6631 | PASS |

其余工况 E 变体：VAL002 5.0083 V（−5.34%）、纹波 0.014517 V；VAL003 5.0151 V（−6.81%）、
0.023978 V；VAL004 5.0309 V（−4.80%）、0.019894 V。规律一致：理想 Vout 高估 5%–7%，理想纹波低估约 145%–153%；
非理想 Vout/平均电流在 1% 内、ΔIL 在 2.1% 内吻合。注意：本阶段没有建立
“非理想输出纹波”检查，ESR 主导的 Vpp 只能用开关 SPICE 或平均模型的 ESR
映射解释，不能声称非理想纹波公式已验证。

### 5.3 汇总与 50 Ω 断续工况

- 理论检查 70 项：**40 PASS / 16 FAIL / 14 NOT_APPLICABLE**。16 个 FAIL 恰好是
  8 个 `TH-VOUT-IDEAL` 与 8 个 `TH-VRIPPLE-IDEAL`（VAL001–VAL004 共 4 个 CCM 工况 × 2 变体），
  VAL005 的 14 项全部是 `NOT_APPLICABLE`，没有其它 FAIL。
- 模型交叉检查 45 项：**22 PASS / 8 FAIL / 5 INSUFFICIENT_DATA / 10 NOT_APPLICABLE**。
  8 个 FAIL 是：VAL001–VAL005 的 A-理想 Vout（5 个，含 VAL005 的 −30.10%）、
  VAL005 的 A-理想 ΔIL（+38.41%）、VAL005 的 B-平均 Vout（5.0000 vs 7.4866，−33.21%）、
  VAL005 的 C-效率（101.365% vs E 的 97.343%）。
- 5 个 `INSUFFICIENT_DATA` 是 A 层效率（理想公式不含损耗）。
- 10 个 `NOT_APPLICABLE` 是 B 层的纹波与效率（平均模型本来就没有这两项）。

VAL005（50 Ω）：E 实测 Vout 7.4866 V、电感谷值 −0.02755 A、效率 97.343%；C 实测 7.5104 V、
效率 101.365%。平均模型仍预测 5.0 V，与实测差 −33.21%，说明 **CCM 平均模型在 DCM 下失效**，
14 项 CCM 检查也因此全部标为 `NOT_APPLICABLE`。C 的效率 >100% 是 DCM 下输入功率记账失效的
直接证据，而不是“效率真的超过 100%”。

图：`results/stage8/figures/theory_comparison.png`（VAL001 五模型 Vout 柱状图，含 5.0 V 目标线）。

## 6. 平均模型与开关模型的差异

| 维度 | 平均模型 B | 开关 SPICE C/E |
| --- | --- | --- |
| 输出 | 周期平均，无纹波 | 逐点波形，含纹波与边沿 |
| 损耗 | 导通 + 二极管 | 另含开关过渡损耗与寄生充放电 |
| 适用 | 控制设计、稳态占空比校准 | 纹波、峰值、效率、DCM 判定 |
| 本阶段对照 | 纹波/效率标 `NOT_APPLICABLE`；Vout 在 CCM 4 工况 PASS | 作为参考层 |

“平均模型 Vout 吻合”只说明低频平均行为一致；它对纹波、峰值和 DCM 没有发言权。

## 7. 已知局限与失败案例

- 理想公式族系统性高估 Vout、低估纹波；16 个 FAIL 被保留，未修改限值。
- 非理想公式的 Rds(on) 与 VF 是 Level-1 估计，忽略温度、沟道长度调制与反向恢复。
- 非理想 Vout 由占空比校准而来，不是独立预测能力。
- VAL005 的 DCM 下，理想/非理想 CCM 公式与平均模型全部不适用；C 的效率记账失真。
- 只评估稳态，不评估瞬态与稳定性。

## 8. 技术面试题

1. **为什么理想 Buck 的 Vout 会高估 6%？** 公式 `D·Vin` 不含 Rds(on)、VF、DCR 与 ESR 的
   直流通路压降；把非理想项加入后 Vout 从 5.3424 V 降到 5.0000 V，SPICE 为 5.0104 V。
2. **理想纹波为什么低估 146%？** 理想 `ΔV=ΔIL/(8fsC)` 只算电容积分纹波，忽略 ESR；
   本设计 ESR 压降主导，实测 19.4 mV 而理想 7.9 mV。
3. **如何判断 CCM 公式是否可用？** 看实测电感电流谷值是否大于 0；VAL005 谷值 −0.02755 A，
   所以 14 项 CCM 检查全部 `NOT_APPLICABLE`。
4. **绝对误差、相对误差、MAE、RMSE 各自回答什么？** 绝对误差给带单位的偏差；相对误差便于
   跨工况比较；MAE 是平均偏差水平；RMSE 对大偏差更敏感，适合检查局部尖峰。
5. **对照前为什么必须先做波形对齐？** 两条波形的时间网格、步长与起点不同，直接相减会把
   插值/采样误差当成模型误差；对齐后还要检查时间偏移是否 ≤1%。
6. **平均模型为什么不能给出纹波和效率对照？** 它只保留周期平均状态，没有开关纹波与过渡损耗；
   强行比较会得到 0 或虚高值，因此代码强制标 `NOT_APPLICABLE`。
7. **VAL005 中 C 的效率 101.365% 说明了什么？** DCM 下电感电流反向，输入/输出功率记账
   假设失效；这是模型适用范围问题，不是物理上的超额效率。
