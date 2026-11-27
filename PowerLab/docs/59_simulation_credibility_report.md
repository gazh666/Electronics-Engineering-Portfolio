# 59 仿真可信度核查指南

> 面向复核者：给定 `results/stage8/` 下的一堆 JSON 与 `run_*` 目录，如何判断
> “这条结论是有证据的，还是只是模型自说自话”。本文只描述真实产物与真实路径，
> 不补造缺失数据。配套报告：`results/stage8/stage8_validation_report.html`，
> 生成器：`reports/validation_report.py`。

## 1. 目标与读者

读者需要在 10 分钟内回答：这条 run 是谁跑的、用什么网表、什么求解器、
波形从哪来、误差怎么算、能否续跑后继续引用。本文给出固定检查顺序：

```
run_id → circuit.cir → 求解器选项 → 波形来源 → 误差统计
      → 收敛 → 守恒 → Monte Carlo → 结论是否 resume-safe
```

## 2. 证据目录结构

```
results/stage8/
├── validation_summary.json          # 任务汇总与 budget
├── stage8_acceptance.json/.csv      # 13 项 ACC 检查
├── credibility_matrix.csv/.json     # 证据 × 维度矩阵
├── checkpoint.json                  # 已完成任务与预算
├── experiments/                     # 7 个实验 JSON
├── monte_carlo/samples.csv          # 采样与状态
├── runs/<run_id>/                   # circuit.cir + metadata + metrics
├── figures/*.png                    # 5 张真实数据图
└── stage8_validation_report.html
```

`runs/` 下没有 `waveform.csv.gz`（§6）。

## 3. 如何定位一个 run_id

`run_id` 形如 `20261125_165348_649a10e6`：`本地时间戳 + uuid4 前 8 位`，
由 `simulations/runner.py:64` 的 `new_run_id()` 生成，保证每次运行不覆盖历史。

三种入口：`experiments/*.json` 的 `run_id`/`run_dir`（如 corner nominal
`20261125_165348_649a10e6`）；`metadata.json` 的 `label`/`config` 快照；
`metrics.json` 的 `data_source`/`variant`/`run_id`。三者一致才算同一证据链。

注意：robustness 的 run 目录只有 `circuit.cir` 与 `metadata.json`，指标写在
`robustness.json` 的 `closed_loop_spice_runs[].metrics`；失败的 25 ns
收敛点没有 run 目录，原因只在 `timestep_convergence.json` 的 `runs[]`。

## 4. 如何找原始网表

打开 `results/stage8/runs/<run_id>/circuit.cir`。写入位置：

- 通用实验：`experiments/_stage8_common.py:86` 的 `save_run_evidence`，
  第 117–118 行写 `circuit.cir`；
- 守恒实验：`_stage8_common.py:198` 的 `run_conservation_case`，第 268–271 行；
- 鲁棒性：`experiments/robustness_comparison.py:100–101` 显式写网表。

网表应含器件参数、模型卡、`.tran` 步长/终止时间、`.options TEMP/TNOM`
与控制方式（E 变体受控源 `ECDRV`，开环 `VDRV ... PULSE`）。网表缺失时，
不能只凭指标 JSON 声称是 SPICE 结果。

示例（闭环 robustness）：`20261125_164922_2cecfc03/circuit.cir` 含
`BCERR/.../BCPWM/ECDRV`，`.tran 2.5e-08s 0.012s 0.0s 2.5e-08s uic`。

## 5. 如何检查求解器配置

1. 看网表 `.options`：求解器对照把注入项写在开头，例如
   `20261125_165327_e08a3644/circuit.cir:3` 为 `.options reltol=0.001`；
   baseline 不注入，只有 `.options TEMP/TNOM`。
2. 看实验 JSON 的 `solver_settings`（name/method/reltol/abstol/vntol/
   injected_options/use_ngspice_defaults），由 `SolverSettings`
   （`validation/solver_validation.py:27`）生成；`spice_line()` 在 74 行拼
   `.options`，`apply_solver_options` 在 91 行注入。
3. 看 `.tran` 的打印/最大步长；`TEMP/TNOM` 是显式假设，不是实测。
4. 失败设置看 `solver_comparison.json` 的 `diagnosis`（`classify_failure`，
   `validation/solver_validation.py:158`）。`reltol_1e-4`、`reltol_1e-5`
   属步长过小类失败；`failure_reason` 只存通用文本，`category="unknown"`，
   不能反推 ngspice 日志。

## 6. 如何核对波形来源

- `metadata.json` 的 `data_source` 必须是 `spice_simulation`；
  `algorithms` 写 `PerformanceAnalyzer.analyze`；`raw_point_count`
  （如 nominal 角点 122460）说明原始点数。
- `metrics.json` 的 `data_source`、`variant`、`run_id` 必须与目录一致；
  `waveform_sample_count`（如 4903）是分析窗口点数，不是原始点数。
- **原始波形默认不落盘**：`_stage8_common.py:93` 的 `save_waveform=False`，
  第 119–120 行只有显式开启才写 `waveform.csv.gz`。本阶段 runs 目录没有该文件。
  因此可以“按网表重跑复现”，但不能“从磁盘重新画原始波形”。
- 来源标记：`analytical_theory` / `averaged_model` / `comparison` /
  `spice_derived`；`validation/models.py:49` 的 `validate_data_source`
  负责校验，混用即证据瑕疵。

## 7 如何读误差统计

入口：`stage8_acceptance.json.findings` 与 `experiments/theoretical_comparison.json`。

字段含义：

| 字段 | 含义 |
| --- | --- |
| `actual_value` | SPICE/实测值 |
| `reference_value` | 理论/参考值 |
| `absolute_error` | actual − reference |
| `relative_error_percent` | 相对参考的百分比 |
| `tolerance` | 该指标允许的绝对误差 |
| `status` | PASS / FAIL / NOT_APPLICABLE / INSUFFICIENT_DATA |
| `intended_use` | 该比较的用途（如 ideal baseline only） |

本次 5 个工况 × C/E 共 70 项理论检查：40 PASS、16 FAIL、14 NOT_APPLICABLE。
16 个 FAIL 全部来自理想公式：8 个 `TH-VOUT-IDEAL`、8 个 `TH-VRIPPLE-IDEAL`。
VAL001 C：实测 Vout 5.017905 V，理想 5.342407 V（低 0.324502 V）；
实测纹波 0.019407 V，理想 0.007883 V（理想偏低，因忽略 ESR）。
非理想检查全部 PASS，说明“理想公式偏差”不是仿真崩坏，而是理想假设不适用。

模型交叉检查另计：22 PASS、8 FAIL、5 INSUFFICIENT_DATA、10 NOT_APPLICABLE。
`INSUFFICIENT_DATA` 不得当 0 或当 PASS。

## 8 如何读收敛结果

入口：`experiments/timestep_convergence.json` 的 `analysis` 与
`convergence_orders`；汇总在 `validation_summary.json.convergence`。

- 步长：请求 200/100/50/25/12.5 ns，完成 200/100/50/12.5 ns；
  25 ns 为 `ERROR`，保留在 `runs[]`。
- 每个指标有 `stable_pairs`、`required_pairs=2`、`worst_change`、
  `details[]`（相邻步长的 `coarse_value/fine_value/absolute_change/allowed_change`）。
  7 个指标全部 `NUMERICALLY_STABLE`。
- 观测阶：Vout −2.39、纹波 −1.56、IL 纹波 −1.13、IL 峰值 +1.03、总损耗 −3.90；
  效率和功率残差 `NOT_RESOLVED`（非单调/振荡）。
- 判读：最细步长只是“数值参考”，不是绝对真值；`NUMERICALLY_STABLE`
  只说明对步长不敏感，不证明器件模型或硬件准确。阶次是经验阶，
  JSON 写明 “empirical order only; not proof of correctness”。

## 9 如何读守恒结果

入口：`experiments/conservation.json` 的 `result.checks[]`；四项：

| 检查 | 值 | 限值 | 状态 |
| --- | --- | --- | --- |
| 伏秒平衡 | 1.731e-5 | 0.02 | PASS |
| 电荷平衡 | 1.824e-5 | 0.02 | PASS |
| 节点电流一致性 | 6.92e-8 | 0.02 | PASS |
| 能量平衡 | 0.04242 | 0.05 | PASS |

`Pin=11.4908 W`、`Pout=10.0417 W`、`Ploss=0.9616 W`。
能量残差 4.24% 远大于瞬时功率残差 9e-6：前者是窗口积分与储能变化的近似，
后者是同一时刻功率和，不能互相替代。守恒只证明波形自洽，不是硬件精度。

## 10 如何读 Monte Carlo 结果

入口：

1. `monte_carlo/samples.csv`：`sample_id`、6 个参数、`status`、`run_id`、
   `failure_reason`；采样见 `monte_carlo_standard.json.sampling`（seed 42、
   PCG64、30 个、独立均匀、`manufacturer_distribution_verified=false`）。
2. `records[]`：每个样本的 `status`、`metrics`、`reused_from_cache`；
   3 个 `ERROR`（mc-001/013/015）保留，不静默删除。
3. `statistics` 与 `pass_ratio`：27 个有效样本的均值/标准差/p5–p95；
   `all_samples` 27/30=0.9（Wilson 0.743789–0.965400），
   `valid_samples` 27/27=1.0（0.875445–1.0），由
   `validation/statistical_analysis.py:50` 计算。

判读原则：通过比例是“假设样本中的条件比例”，**不是产品良率**；
独立同分布是简化；3 个未收敛样本说明尾部有数值风险。`reused_from_cache=true`
的样本不是本次重跑。

## 11 如何判断结论是否 resume-safe

`validation/validation_runner.py` 的 `ValidationRunner`：

- 初始化时若 `resume=True` 且 `checkpoint.json` 存在，载入 `completed`（第 98–100 行）；
- `run_task` 在 `resume` 且任务已记录、结果文件存在时，直接读 JSON，不重跑（第 131–132 行）；
- 每任务完成后写 checkpoint（117–127、167–171 行）。

“resume-safe”指结论绑定磁盘结果与 checkpoint，而非“今天又跑一遍”的叙述。

| 结论 | 可否引用 | 理由 |
| --- | --- | --- |
| 8 任务、76 SPICE、budget | 可以（文件齐全时） | summary + checkpoint + experiments |
| 理论 40/16/14、模型 22/8/5/10 | 可以 | 对应实验 JSON |
| MC 27/30 与分位数 | 可以，但非良率 | 3 个 ERROR 保留 |
| 闭环角点筛查 PASS | 可以，须带线性化限定 | `averaged_model` |
| 收敛阶 −2.39 等 | 仅“经验阶” | empirical note |
| 硬件精度/良率 | 不可以 | `NOT_VERIFIED` |
| 全局最坏 | 不可以 | 7 个显式角点 |
| 设计 B 改善 | 不可以 | `stage6_missing` |
| “今天重新跑过” | 需核对 | checkpoint 时间与 `reused_from_cache` |

## 12 证据路径

- 验收：`validation_summary.json`、`stage8_acceptance.json/.csv`；
- 矩阵：`credibility_matrix.csv/.json`；实验：`experiments/*.json`；
- 单次运行：`runs/<run_id>/{circuit.cir,metadata.json,metrics.json}`；
- 报告与图：`stage8_validation_report.html`、`figures/*.png`；
- 生成器：`reports/validation_report.py:155`/`:305`；`--report-only` 可重生成。

## 13 局限

1. 原始波形默认不落盘，不能从磁盘换窗重算或重做谱分析。
2. 求解器失败文本过于通用，具体 ngspice 报错需看日志（若有）。
3. 收敛只有 4 个有效点，25 ns 缺失；效率/功率残差阶未解析。
4. Monte Carlo 仅 27 个有效样本，分布假设为教学假设。
5. 可信度矩阵 `external_validation` 全为 `NOT_VERIFIED`。
6. 角点有限，不能外推全局最坏。
7. 图只使用 `results/stage8` 的 JSON；缺数据返回 `None`，不补零。

## 14 面试题

**Q1：为什么 run 目录里常常没有 waveform？**
A：`save_run_evidence` 默认 `save_waveform=False`，只落网表、配置快照和指标；
复现靠网表重跑，不靠磁盘波形。

**Q2：拿到一个 Vout 数值，如何证明它来自 SPICE 而不是公式？**
A：看 `data_source=spice_simulation`、`metrics.json` 的 `run_id`/`variant`、
同目录 `circuit.cir`、`metadata.json` 的 `algorithms`/`raw_point_count`；
理论值标 `analytical_theory`，不能混。

**Q3：收敛“稳定”是否等于结果正确？**
A：不等于。它只说明该指标对步长不敏感；模型误差、器件假设与硬件差异
仍需外部验证。

**Q4：Monte Carlo 通过率 90% 能否写成良率 90%？**
A：不能。样本来自假设分布、独立采样，只有 30 点、3 个未收敛；Wilson 区间
只描述采样不确定性，JSON 写明 “not a production yield”。

**Q5：resume 后引用旧结果，最容易犯什么错？**
A：把“文件存在”当“本次重跑”。核对 checkpoint 的 `updated_at`、
`reused_from_cache` 与 run 时间戳，并注明复用。

**Q6：为什么能量残差 4.24% 还能 PASS？**
A：限值 5%，且该残差是窗口积分近似；瞬时功率残差 9e-6 不能替代。
PASS 只代表波形在设定窗口内自洽，不代表硬件效率精确。

**Q7：求解器对照 5 成功 / 2 失败，能说“求解器无关”吗？**
A：不能。5 个设置一致只说明数值接近；2 个更严 reltol 设置失败，说明网表对
步长/容差敏感，应保留为风险。
