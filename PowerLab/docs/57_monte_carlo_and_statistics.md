# 57 Monte Carlo 与统计分析

本文说明第八阶段的 **Monte Carlo 采样与统计口径**：随机数生成、均匀分布与
截断正态的区别、样本均值/标准差/中位数/分位数、Wilson 区间、Pearson 与
Spearman 相关，以及为什么“样本通过比例”不是“真实产品良率”。所有数值来自
`results/stage8/experiments/monte_carlo_standard.json`、
`results/stage8/monte_carlo/samples.csv` 与
`configs/monte_carlo_config.yaml`。

> 结论先行：standard profile 实际执行 30 个样本，27 个 `COMPLETED`，
> 3 个 `ERROR` 被保留；Vout 均值 5.011879 V、样本标准差 0.012503 V；
> 27/30 = 0.9 的 Wilson 95 % 区间为 [0.743789, 0.965400]。
> 这是**给定假设样本集下的比例不确定性**，不是良率、不是硬件置信区间。

## 1. 目标与范围

- 目标：在 6 个容差参数的假设分布下，观察 Vout、纹波、效率、峰值电流、
  损耗的分布与参数影响力。
- 规模：`smoke 5 / standard 30 / extended 100` 三档
  （`configs/monte_carlo_config.yaml:17`）；本阶段执行 standard 30。
- 固定条件：`VAL001`、变体 E、`Vin=12 V`、`Rload=2.5 Ω`、`fsw=100 kHz`、
  `end_time_s=0.005`、步长上限 50 ns、温度 25 °C（不采样）。

代码入口：`experiments/monte_carlo_experiment.py:85` 的 `run_monte_carlo`；
采样在 `validation/monte_carlo.py`，统计在
`validation/statistical_analysis.py`。

## 2. 采样方法与随机性

`generate_samples`（`validation/monte_carlo.py:63`）使用
`numpy.random.default_rng(seed)`，即 **PCG64**，种子 `42`（`DEFAULT_SEED`，
第 20 行）。参数按名称排序后逐个抽取，样本 ID 为 `mc-001 … mc-030`。
相同种子 + 相同参数顺序 + 相同 count 必然复现同一组参数值：

```
mc-001: C=0.000110958, ESR=0.0288998, DRS=0.0171516,
        L=5.07105e-05, DCR=0.0418835, KP=1.190249
mc-002: C=0.000110446, ESR=0.0351492, DRS=0.0127687,
        L=4.60673e-05, DCR=0.0474160, KP=1.170706
```

`sampling_provenance`（第 86 行）把 `random_seed`、`numpy_rng`、
`profile`、`sample_count`、`distribution_source`、`correlation_assumption`
全部写入 JSON，保证可审计。`cache_signature`（第 163 行）把参数与工况拼成
缓存键，参数完全相同的组合会复用结果；本次 `reused_from_cache` 全为 `False`。

## 3. 均匀分布与截断正态

`_sample_one`（`validation/monte_carlo.py:43`）支持四种分布：

| 分布 | 实现 | 本阶段是否使用 |
| --- | --- | --- |
| `fixed` | 直接返回 nominal | 否 |
| `uniform` | `rng.uniform(lower, upper)` | **是（全部 6 参数）** |
| `truncated_normal` | `truncnorm`，`scale=(upper-lower)/4`，再 clip | 否 |
| `discrete` | 在 low/nominal/high 三点等概率 | 否 |

`component_tolerances.yaml` 中 6 个参数全部声明 `distribution: uniform`，
因此本阶段**只用了均匀分布**。截断正态虽然实现了，但没有运行，也没有对应结果；
若要使用，需要先把 YAML 改成 `truncated_normal` 并重跑，不能拿均匀分布的结果
冒充。

均匀分布意味着区间内每点等概率，样本会均匀铺满 [lower, upper]；截断正态会把
样本集中在标称附近，尾部被截断。两者对通过率与分位数的估计不同，比较时不可混用。

## 4. 统计量定义与实测

`summarize_metric`（`validation/statistical_analysis.py:32`）对有效样本计算：

$$
\bar x=\frac{1}{n}\sum x_i,\qquad
s=\sqrt{\frac{1}{n-1}\sum (x_i-\bar x)^2}
$$

注意 `ddof=1`（样本标准差）。分位数用 `numpy.percentile` 默认的线性插值。
中位数即 `p50`。结果（`statistics.metrics`，仅 27 个 `COMPLETED` 样本）：

| 指标 | mean | std | min | p5 | p50 | p95 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Vout (V) | 5.011879 | 0.012503 | 4.991883 | 4.992889 | 5.010862 | 5.028845 | 5.031178 |
| 输出纹波 (V) | 0.020093 | 0.004178 | 0.012512 | 0.013221 | 0.021548 | 0.025959 | 0.027207 |
| 电感电流纹波 (A) | 0.658497 | 0.070995 | 0.543226 | 0.557381 | 0.652404 | 0.800404 | 0.808838 |
| 电感峰值 (A) | 2.334281 | 0.035520 | 2.270787 | 2.279735 | 2.332630 | 2.403594 | 2.407785 |
| 效率 (%) | 93.374059 | 0.238182 | 92.977381 | 93.002411 | 93.366847 | 93.699147 | 93.748588 |
| 总损耗 (W) | 0.713160 | 0.023939 | 0.675253 | 0.680541 | 0.713955 | 0.750451 | 0.753571 |

工程限值（`engineering_limits`）：Vout 4.9–5.1 V、纹波 ≤ 0.05 V、效率 ≥ 85 %。
按 p5/p95 看，Vout 的 90 % 区间约 4.9929–5.0288 V，纹波 p95 为 0.025959 V，
效率最低 92.98 %，均未触限。

均值的不确定性可用 `s/√n` 描述（n=27），但本文不把它当置信区间；样本均值
只是对“假设分布下真实均值”的一次估计。

## 5. 通过比例与 Wilson 区间

`pass_ratio_summary`（`validation/statistical_analysis.py:171`）刻意给出三种
分母，禁止混用：

| 口径 | 分子/分母 | 比例 | Wilson 95 % 区间 |
| --- | --- | ---: | --- |
| `all_samples` | 27 / 30 | 0.9 | [0.743789, 0.965400] |
| `valid_samples` | 27 / 27 | 1.0 | [0.875445, 1.0] |
| `numerical_valid` | 27 / 27 | 1.0 | [0.875445, 1.0] |

Wilson 得分区间（`wilson_interval`，第 50 行）：

$$
\text{center}=\frac{\hat p+\frac{z^2}{2n}}{1+\frac{z^2}{n}},\qquad
\text{margin}=\frac{z\sqrt{\frac{\hat p(1-\hat p)}{n}+\frac{z^2}{4n^2}}}{1+\frac{z^2}{n}}
$$

`z = norm.ppf(0.5+confidence/2) ≈ 1.96`。Wilson 比 Wald 区间更适合小样本与
接近 0/1 的比例，且不会给出负下界。`total=0` 时返回
`INSUFFICIENT_DATA`，不虚构区间。

三种口径的含义必须说清：

- `all_samples` 把 3 个数值失败算作不通过 → 0.9；
- `valid_samples` 只在成功样本内统计是否满足工程限值 → 1.0；
- `numerical_valid` 只问“数值是否有效”，不问限值 → 1.0。

报告里若只引用 1.0，会掩盖 3 个 SPICE 失败；若只引用 0.9，又混淆了“数值失败”
与“性能不达标”。三者并列才是完整信息。

## 6. Pearson 与 Spearman

`pearson_correlation`（第 88 行）与 `spearman_correlation`（第 92 行）共用
`_correlation`（第 96 行），要求至少 3 对有效值，方差为 0 时返回
`NOT_VERIFIED`，样本不足返回 `INSUFFICIENT_DATA`。

$$
r=\frac{\sum(x_i-\bar x)(y_i-\bar y)}
{\sqrt{\sum(x_i-\bar x)^2\sum(y_i-\bar y)^2}}
$$

Spearman 是对秩做 Pearson，衡量单调关系，对非线性单调与离群点更稳健。

**必须说明的口径差异**：本实验 JSON 的 `parameter_influence` 只记录了
**Spearman**（36 处 `spearman`，0 处 `pearson`）；Pearson 函数已实现但本实验
未落盘 Pearson 数值。因此本文只引用 Spearman，不编造 Pearson 系数。

按 |Spearman| 排序（n=27）：

| 指标 | 第 1 位 | 第 2 位 | 第 3 位 |
| --- | --- | --- | --- |
| Vout | DCR −0.9792 (p≈7.5e-19) | DRS −0.4322 (p=0.0243) | ESR +0.3144 (p=0.110) |
| 输出纹波 | ESR +0.8883 (p≈6.3e-10) | L −0.4847 (p=0.0104) | DCR −0.2589 |
| 电感电流纹波 | L −0.9988 (p≈3.5e-34) | C +0.2491 | KP −0.1270 |
| 电感峰值电流 | L −0.9609 (p≈1.9e-15) | DRS −0.2204 | C +0.1990 |
| 效率 | DCR −0.9676 (p≈1.8e-16) | DRS −0.4615 (p=0.0154) | ESR +0.3181 |
| 总损耗 | DCR +0.9670 | DRS +0.4609 | ESR −0.3223 |

这些是**关联**，不是因果：例如 ESR 与纹波高度正相关，与纹波公式
`Δi_L·ESR` 的机理一致，但 Spearman 本身不能证明因果；DCR 与效率的强负相关
同理。JSON 每条都带 `note: "association only; no causal claim"`。

## 7. 采样通过率 ≠ 产品良率

`statistical_analysis.py` 的模块注释与 JSON `disclaimer` 都写明：

```
pass fraction is conditional on assumed ranges and a teaching model;
it is not a production yield and not a hardware confidence interval
```

原因至少有五条：

1. 参数区间是教学假设，`manufacturer_distribution_verified=false`；
2. 假设独立，真实批次存在相关；
3. 只有 30 个样本，Wilson 区间跨约 22 个百分点（0.744–0.965）；
4. 3 个样本因数值失败被排除，真实产品不会“因为仿真不收敛就不存在”；
5. 全部 25 °C、无老化、无 DC-bias，未覆盖真实使用条件。

因此正确表述是“在本假设、本模型、本样本集下，27/27 个有效样本满足限值”，
而不是“良率 100 %”。

## 8. 失败样本的保留

`records` 共 30 条，状态分布 `COMPLETED 27 / ERROR 3`。保留的失败：

| sample_id | 状态 | 原因（原文） |
| --- | --- | --- |
| `mc-001` | ERROR | transient simulation failed … Model E: Command 'run' failed |
| `mc-013` | ERROR | 同上 |
| `mc-015` | ERROR | 同上 |

`summarize_samples`（第 217 行）生成 `preserved_failures`，`ACC-NO-SILENT-DELETE`
也校验“记录数 = 采样数”。需要注意一个细节：`samples.csv` 是在循环前写出的
（`monte_carlo_experiment.py:120`），所以它的 `status` 列**全部是 `PENDING`**，
最终状态在 `records` 与 `checkpoint_standard.json` 中；CSV 是采样参数台账，
不是结果台账。引用时不能把 CSV 的 PENDING 当成“未执行”。

## 9. 输入、输出与错误处理

- 输入：`configs/monte_carlo_config.yaml`（profile、seed、分位数、指标）、
  `configs/component_tolerances.yaml`、`configs/performance_limits.yaml`、
  `VAL001` 工况。
- 输出：`results/stage8/experiments/monte_carlo_standard.json`；
  `results/stage8/monte_carlo/samples.csv`；
  `results/stage8/monte_carlo/checkpoint_standard.json`（逐样本断点）；
  每个成功样本的 `results/stage8/runs/<run_id>/`；
  图 `results/stage8/figures/monte_carlo_vout.png`。
- 校验：`validate_sample_values`（第 182 行）检查缺失、非有限、越界，失败样本
  标为 `INVALID_SAMPLE` 并记录原因，不进入仿真；`generate_samples` 拒绝
  非正 count 与非 `independent_random` 方法；`wilson_interval` 拒绝
  `successes > total`。
- 失败处理：SPICE 异常由 `run_case` 捕获成 `ERROR` + `failure_reason`
  + `diagnosis`；支持 `resume` 断点续跑（`monte_carlo_experiment.py:115`），
  不会重复计数也不会删除历史失败。

## 10. 已知局限

1. 30 个样本对 6 维空间偏少；p5/p95 与 Wilson 区间都只反映采样不确定性。
2. 只有均匀分布被实际使用；截断正态未运行。
3. 参数独立、无相关性；无温度、无老化、无 DC-bias。
4. JSON 只落盘 Spearman，Pearson 虽实现但本实验无数据，不能引用。
5. 3 个数值失败未归因到具体参数组合之外（仅保留报错文本），无法判断是否
   与极端容差相关。
6. 通过率不等于良率；Wilson 区间不是硬件置信区间。

## 11. 面试题

**Q1：为什么用 PCG64 + 固定种子？**
PCG64 状态空间大、统计性质好；固定种子保证任何人用同一配置能复现同一组
参数值，便于审计与回归测试。

**Q2：样本标准差为什么用 `ddof=1`？**
总体方差未知时用 `n-1` 得到无偏估计；`ddof=0` 会系统性低估方差，尤其小样本。

**Q3：Wilson 区间比 Wald 好在哪里？**
Wald 在 p 接近 0/1 或 n 小时会越界（负下界、上界 >1）；Wilson 通过中心与
边际修正，边界始终在 [0,1]，小样本覆盖更稳。

**Q4：Spearman 显著就说明参数导致指标变化吗？**
不。Spearman 只说明秩相关；因果需要控制变量、机理模型或干预实验。本项目
只声明 association。

**Q5：为什么 27/27 通过不能叫 100 % 良率？**
分母是“成功仿真且满足限值的样本”，排除了 3 个数值失败，且分布是教学假设、
25 °C、独立采样；真实良率需要批次数据、温度/老化覆盖与硬件测试。

**Q6：如何提高 Monte Carlo 结论的可信度？**
增加样本（extended 100）、改用有依据的分布、引入相关性与温度、对失败样本
做归因、并用实测数据校准模型；同时报告多种通过口径与区间。
