# 31 性能判定与数据有效性

本文解释工程限值、项目假设、Datasheet 规格、数据有效性、PASS/FAIL/ERROR、
NOT_APPLICABLE、NOT_VERIFIED、统计口径，以及为什么不能为了通过测试修改原始结果。

代码位置：`analysis/performance_judge.py`（`judge_profile`、`summarize_checks`）、
`analysis/performance_quality.py`（`QualityIssue`、`check_*`、`quality_summary`）、
`configs/performance_limits.yaml`、`configs/performance_analysis.yaml`、
`analysis/performance_models.py`（`MetricStatus`、`DataSource`）。

真实结果：`results/performance/run_20261125_143528_3011f8e8/`
（`performance_checks.json`、`data_quality.json`、`summary.json`）与
`results/buck_stage5/run_20261125_143621_dd15c905/stage5_validation.json`。

## 1. 工程限值

`configs/performance_limits.yaml` 定义五个 profile：

| profile | 用途 | 关键限值 |
| --- | --- | --- |
| `baseline_open_loop` | 开环基线 | 纹波 ≤ 50 mV、fsw 99–101 kHz、占空比误差 ≤ 0.005、系统效率 85–100 %、残差比 ≤ 0.05 |
| `target_5v_design` | 5 V 设计目标 | 输出电压 4.9–5.1 V（显式启用） |
| `light_load_open_loop` | 轻载 DCM | 放宽效率下限，避免 DCM 误判 |
| `data_quality` | 数据质量 | 残差与采样相关阈值 |
| `numerical_analysis` | 数值检查 | 频谱/边沿可信度 |

限值分为 `min`/`max`/`range` 三类，由 `judge_profile` 应用。
每个检查都记录 `metric`、`value`、`limit`、`status`、`message`。

## 2. 项目假设与 Datasheet 规格

| 类型 | 来源 | 标记 | 用途 |
| --- | --- | --- | --- |
| 项目假设 | `configs/*.yaml` | `project_assumption` | 设计目标、限值、教学参数 |
| SPICE 实测 | 真实瞬态波形 | `spice_derived` | 所有性能指标 |
| 解析理论 | 公式计算 | `analytical_theory` | 纹波/CCM 对照，不参与判定 |
| Datasheet 规格 | 未使用 | 不适用 | 本项目没有商业器件手册 |

本项目**不引用任何真实器件 datasheet 数值**。所有 MOSFET/二极管参数都是
教学模型参数（`model_source: educational_assumption`）。因此报告中不能出现
“满足某型号 datasheet”的结论；正确表述是“在项目假设的限值下 PASS/FAIL”。

## 3. 数据有效性

一个指标要可判定，必须同时满足：

1. 波形帧包含必需列（`check_waveform_frame`）；
2. 数据全部有限，无 NaN/Inf（`E_NONFINITE_DATA`）；
3. 时间轴严格递增且样本足够（`E_TIME_AXIS_INVALID`）；
4. 已达到稳态，或明确标记未稳态（`check_steady_state`）；
5. 指标值有限且与均值/极值/纹波自洽（`check_metric_consistency`）；
6. 功率残差在阈值内（`check_power_residual`）；
7. 频谱/边沿的可信度满足判据（`check_spectrum`、`check_switching`）。

任何一条失败，相关指标就降级为 `INVALID_DATA` 或 `NOT_SETTLED`，
不会用一个“看起来合理”的数值继续参与 PASS/FAIL。

## 4. 判定状态

| 状态 | 含义 |
| --- | --- |
| `PASS` | 数据有效且在限值内 |
| `FAIL` | 数据有效但超出限值 |
| `ERROR` | 指标缺失、非有限或必需项不可用 |
| `NOT_VERIFIED` | 数据存在但无法验证（未稳态、未解析） |
| `NOT_APPLICABLE` | 该模型/工况不适用 |
| `SKIP` | 限值被显式禁用或非必需项缺失 |

总体状态优先级：

$$
\text{ERROR}>\text{FAIL}>\text{INCOMPLETE}>\text{PASS}
$$

`INCOMPLETE` 由 `NOT_VERIFIED`、`NOT_APPLICABLE` 或 `SKIP` 触发。
`summarize_checks` 输出 PASS/FAIL/ERROR/未验证/跳过计数与对应清单。

## 5. 基线真实判定

`results/performance/run_20261125_143528_3011f8e8/performance_metrics.json`：

| 指标 | 实测 | 限值 | 状态 |
| --- | ---: | --- | --- |
| `output_voltage_ripple_vpp` | 19.0416 mV | ≤ 50 mV | PASS |
| `switching_frequency_hz` | 100.000 kHz | 99–101 kHz | PASS |
| `pwm_duty_absolute_error` | 7.38×10⁻¹⁵ | ≤ 0.005 | PASS |
| `efficiency_system_percent` | 92.8306 % | 85–100 % | PASS |
| `output_voltage_target` | — | 4.9–5.1 V | SKIP（禁用） |
| `power_residual_ratio` | −2.55×10⁻⁷ | ≤ 0.05 | PASS |

统计口径：总计 6 项，**5 PASS + 1 SKIP**，总体 `PASS`。
`SKIP` 不计入 FAIL，也不计入 PASS 率分母以外的任何“通过率”宣传。

## 6. 数据质量错误码与基线输出

`analysis/performance_quality.py`：

| 代码 | 级别 | 触发条件 |
| --- | --- | --- |
| `E_MISSING_WAVEFORM` | ERROR | 缺少必需列或帧对象非法 |
| `E_NONFINITE_DATA` | ERROR | 波形含 NaN/Inf |
| `E_TIME_AXIS_INVALID` | ERROR | 时间轴非严格递增或样本过少 |
| `E_METRIC_INCONSISTENT` | ERROR | 均值/极值/纹波自相矛盾 |
| `E_NEGATIVE_RIPPLE` | ERROR | 纹波为负 |
| `E_POWER_RESIDUAL_EXCESSIVE` | ERROR | 残差比超阈值 |
| `E_NOT_SETTLED` | ERROR | 未稳态却继续给指标 |
| `E_EMPTY_SPECTRUM` | ERROR | 频谱数组为空 |
| `E_UNIT_MISMATCH` | WARNING | 指标单位为空 |
| `W_EDGE_NOT_RESOLVED` | WARNING | 开关边沿样本不足 |
| `W_SPECTRUM_UNDER_RESOLVED` | WARNING | 频谱完整周期不足 |
| `W_RIPPLE_DRIFT` | WARNING | 逐周期纹波漂移（由 `performance_analyzer.py` 触发） |

基线质量结果：**0 error，2 warning**，两个 warning 都是
`W_EDGE_NOT_RESOLVED`（开通/关断各 3 个样本）。

## 7. benchmark 的真实 FAIL

`results/buck_stage5/run_20261125_143621_dd15c905/stage5_validation.json`：

| case | 名称 | Vout | 纹波 | 效率 | 状态 |
| --- | --- | ---: | ---: | ---: | --- |
| PERF001 | Model A 基线 | 4.7813 V | 8.131 mV | 95.620 % | PASS |
| PERF002 | Model E 基线 | 4.6682 V | 19.042 mV | 92.831 % | PASS |
| PERF003 | 50 Ω 轻载 | 7.1603 V | 15.623 mV | 96.736 % | PASS |
| PERF004 | ESR 0.1 Ω | 4.6682 V | **61.561 mV** | 92.810 % | **FAIL** |
| PERF005 | 9 V 输入 | 3.4540 V | 14.937 mV | 91.560 % | PASS |
| PERF006 | 16 V 输入 | 6.2903 V | 25.601 mV | 93.867 % | PASS |

PERF004 的 FAIL 是真实结果：ESR 从 30 mΩ 增到 100 mΩ 后，
$\Delta i_L\cdot ESR$ 直接把纹波推过 50 mV。没有为了让全部工况 PASS 而
放宽限值或重跑“挑数据”。

PERF005/006 使用 `baseline_open_loop`（目标电压禁用），因此 3.454 V 与
6.290 V 不触发 FAIL；这是开环固定占空比的物理结果。若切到
`target_5v_design`，这两点会 FAIL。报告中必须同时说明 profile 名称。

## 8. 统计口径

- **通过率**只在明确分母下报告，例如“基准工况 6 个中 5 PASS”。
- 不把不同 profile 的结果混在一起算通过率。
- `SKIP`、`NOT_APPLICABLE`、`NOT_VERIFIED` 单独计数，不并入 PASS。
- 所有数值保留原始精度，报告展示时才截断。
- 每次运行独立成目录，不覆盖历史结果。

## 9. 为什么不能修改原始结果

1. 修改波形/指标会让结果不可追溯，run_id 与 config 快照失去意义；
2. 放宽限值或删除失败工况等于伪造结论；
3. 未稳态、未解析的数据应标记状态，而不是换成“好看”的数值；
4. 真实 FAIL 本身是工程信息：例如 PERF004 直接指出 ESR 是纹波主因；
5. 本项目的可信度建立在“原始数据只读、分析可复算”之上。

`save_performance_run` 只写新目录，不修改 `SimulationResult.data`；
`reports/performance_report.py` 只读 `results/` 下的目录。

## 10. 面试题

1. ERROR 和 FAIL 的区别？为什么不能合并？
   ERROR 是数据不可用，FAIL 是数据可用但性能不达标；修复路径完全不同。
2. NOT_VERIFIED 和 FAIL 的区别？
   前者“无法证明”，后者“已证明不满足”。
3. 基线目标电压被禁用是否等于作弊？
   不是。目标电压单独记录为设计偏差，其他指标仍严格判定。
4. 为什么质量 warning 不直接判 FAIL？
   warning 表示可信度下降，是否影响结论取决于使用场景。
5. 高 ESR 工况 FAIL 的工程意义？
   输出电容选型不能只看容值，ESR 直接决定纹波与发热。
6. 为什么通过率必须说明分母和 profile？
   不同限值、不同工况混算会夸大或掩盖真实性能。
7. 如果某个指标单位为空，应该报错还是告警？
   本项目报 `E_UNIT_MISMATCH` 告警，数值可能有效，但读者需知道单位缺失。
8. 为什么报告不允许写入 results 目录之外？
   防止路径穿越读取源码、密钥或改写非结果文件。
