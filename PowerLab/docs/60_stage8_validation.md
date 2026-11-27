# 60 第八阶段验收报告：仿真可信度与鲁棒性验证

> 本文件是第八阶段的**持久验收记录**，只记录真实运行结果。所有数值可在
> `results/stage8/` 的 JSON/CSV 与 `runs/<run_id>/` 中追溯。未通过与未解析项
> 按原样保留；本文不替代 60 项对话式汇报，也不把“过程完整”包装成“硬件准确”。

## 1 验收结论

| 项目 | 实际值 | 来源 |
| --- | --- | --- |
| profile | `standard` | `results/stage8/validation_summary.json` |
| 任务 | 8/8（theory、convergence、solver、conservation、tolerance、corner、monte-carlo、robustness） | 同上 `tasks_completed` |
| SPICE 运行 | 76 / 120 | 同上 `budget.spice_runs` |
| 平均模型运行 | 0 / 40 | 同上 `budget.averaged_runs` |
| 验收墙钟 | 94.65 s | 同上 `budget.wall_clock_s` |
| ACC 检查 | 13 项：12 PASS + 1 NOT_VERIFIED | `stage8_acceptance.json` |
| 总体状态 | `COMPLETE_WITH_OPEN_ITEMS` | 同上 `overall_status` |
| 全量测试 | 659 passed，34.99 s | `pytest tests -q` |
| 测试构成 | 532 基线（阶段 1–7）+ 127 新增（阶段 8，15 个文件） | 测试文件清单 |

结论：验证流程完整执行，数值自洽性、收敛性、求解器一致性、容差与角点均有
真实证据；但**没有外部硬件验证**（ACC-HARDWARE = `NOT_VERIFIED`），
且存在 16 个理想公式 FAIL、2 个求解器设置失败、3 个 Monte Carlo 样本未收敛、
效率/功率残差收敛阶未解析等开放项。`COMPLETE_WITH_OPEN_ITEMS` 描述的是
“过程完成、开放项已登记”，不是“硬件精度通过”。

## 2 交付物

### 2.1 15 个验证模块

| 文件 | 关键类/函数 |
| --- | --- |
| `validation/reference_cases.py` | `ValidationCase`、`load_validation_cases`、`build_case_config`、`averaged_parameters_for_case` |
| `validation/models.py` | `ValidationStatus`、`ValidationCheck`、`ValidationResult`、`validate_data_source` |
| `validation/theoretical_validation.py` | `ideal_ccm_theory`、`nonideal_ccm_theory`、`make_check`、`evaluate_theory` |
| `validation/model_cross_validation.py` | `ModelLevel`、`cross_validate`、`averaged_metrics` |
| `validation/waveform_alignment.py` | `align_waveforms`、`pwm_cycle_average`、`cycle_mean_waveform` |
| `validation/convergence_analysis.py` | `TimestepPoint`、`check_metric_convergence`、`estimate_convergence_order`、`analyze_convergence` |
| `validation/solver_validation.py` | `SolverSettings`、`apply_solver_options`、`classify_failure`、`compare_solver_runs` |
| `validation/conservation_checks.py` | `check_volt_second`、`check_charge_balance`、`check_node_current`、`check_energy_balance`、`run_conservation_checks` |
| `validation/tolerance_analysis.py` | `ParameterTolerance`、`load_component_tolerances`、`one_factor_plan` |
| `validation/corner_analysis.py` | `Corner`、`default_corners`、`build_corner_config`、`summarize_corners` |
| `validation/monte_carlo.py` | `MonteCarloSample`、`generate_samples`、`sampling_provenance`、`write_samples_csv` |
| `validation/statistical_analysis.py` | `summarize_metric`、`wilson_interval`、`pass_ratio_summary` |
| `validation/uncertainty_analysis.py` | `central_sensitivity`、`propagate_first_order`、`sensitivity_from_one_factor` |
| `validation/robustness_analysis.py` | `compare_designs`、`closed_loop_corner_screen`、`summarize_closed_loop_screen`、`unavailable_design` |
| `validation/validation_runner.py` | `ValidationRunner`、`build_summary`、`build_acceptance`、`write_credibility_matrix` |

### 2.2 5 个配置

`configs/validation_cases.yaml`、`configs/numerical_validation.yaml`、
`configs/component_tolerances.yaml`、`configs/monte_carlo_config.yaml`、
`configs/validation_limits.yaml`。

### 2.3 7 个实验 + 公共流水线

`experiments/theoretical_comparison.py`、`timestep_convergence.py`、
`solver_comparison.py`、`corner_experiment.py`、`tolerance_experiment.py`、
`monte_carlo_experiment.py`、`robustness_comparison.py`，
以及 `experiments/_stage8_common.py`（运行、指标提取、证据落盘）。

### 2.4 9 个脚本

`scripts/theory_validation_demo.py`、`timestep_convergence_demo.py`、
`solver_validation_demo.py`、`tolerance_demo.py`、`corner_analysis_demo.py`、
`monte_carlo_demo.py`、`robustness_demo.py`、`model_comparison_demo.py`、
`buck_stage8_demo.py`（主 CLI）。

### 2.5 报告与图

`reports/validation_report.py` 生成
`results/stage8/stage8_validation_report.html`，并输出 5 张真实数据图：
`figures/theory_comparison.png`、`timestep_convergence.png`、
`tolerance_sensitivity.png`、`monte_carlo_vout.png`、`corner_comparison.png`。
缺数据时绘图函数返回 `None`，不补零。

### 2.6 测试

15 个新增测试文件：`test_validation_models.py`、`test_theoretical_validation.py`、
`test_waveform_alignment.py`、`test_model_cross_validation.py`、
`test_convergence_analysis.py`、`test_solver_validation.py`、
`test_conservation_checks.py`、`test_tolerance_analysis.py`、
`test_corner_analysis.py`、`test_monte_carlo.py`、
`test_statistical_analysis.py`、`test_uncertainty_analysis.py`、
`test_robustness_analysis.py`、`test_validation_report.py`、
`test_stage8_integration.py`。

### 2.7 文档

阶段八文档编号 `docs/51`–`docs/60`（共 10 份）。其中
`docs/58_design_robustness.md` 为设计鲁棒性，
`docs/59_simulation_credibility_report.md` 为可信度核查指南，本文件为 60。

## 3 复用与缺口

- 复用第四/五阶段非理想 Buck 功率级与器件模型（`circuits/nonideal_buck.py`、
  `circuits/nonideal_config.py`）、性能分析器
  （`analysis/performance_analyzer.py`）与仿真运行器；
- 复用第七阶段闭环配置与运行器（`circuits/closed_loop_config.py`、
  `simulations/closed_loop_runner.py`）做闭环鲁棒性 SPICE；
- **仓库缺少第六阶段交付物**（无 `docs/34`–`41` 及对应模块），因此优化设计
  `design_b_optimized` 标为 `NOT_APPLICABLE`，验收记录写
  `known_gaps: stage6_missing`，未合成基线；
- 平均模型与理论指标在离线计算，**没有单独的“平均模型 SPICE runner”**，
  所以 `budget.averaged_runs=0`；这不是“平均模型未验证”，而是口径不同。

## 4 环境与运行命令

环境：Windows 10、conda `kaifa_power`、Python 3.11.18、PySpice 1.5 +
ngspice-34、numpy 1.26.4、scipy 1.17.1、pandas 3.0.6、matplotlib 3.11.2、
PyYAML 6.0.4。`scripts.verify_environment` 状态 OK（12 V 分压 → 6.0 V），
`pip check` 无 broken requirements。仓库没有 ruff 配置，因此**未运行 ruff**，
不声明 lint 通过。

```powershell
conda run -n kaifa_power python -m scripts.buck_stage8_demo --dry-run
conda run -n kaifa_power python -m scripts.buck_stage8_demo --profile smoke
conda run -n kaifa_power python -m scripts.buck_stage8_demo --profile standard --max-runs 120
conda run -n kaifa_power python -m pytest tests -q
```

`--dry-run` 只打印计划，不执行 ngspice；`--report-only` 可根据已有结果重生成
HTML；`--resume` 从 `results/stage8/checkpoint.json` 续跑。

## 5 13 项 ACC 检查

| 检查 | 说明 | 状态 | 证据 |
| --- | --- | --- | --- |
| ACC-THEORY-EXECUTED | 至少一个统一工况的理论/平均/SPICE 对照 | PASS | 5 cases |
| ACC-CCM-APPLICABILITY | 轻载不强行套 CCM 公式 | PASS | VAL005 checks: 14 |
| ACC-CONVERGENCE | 时间步长收敛状态已记录 | PASS | NUMERICALLY_STABLE |
| ACC-SOLVER | 至少两种求解器设置完成对照 | PASS | 5 completed / 7 attempted |
| ACC-CONSERVATION | 伏秒/电荷/节点电流/能量四项守恒 | PASS | 4 checks |
| ACC-TOLERANCE | 单参数容差覆盖至少 6 个参数 | PASS | 6 parameters |
| ACC-CORNER | 角点分析执行并记录有限覆盖 | PASS | 7 corners |
| ACC-MONTE-CARLO | 不少于 30 个样本且失败样本保留 | PASS | 30 records |
| ACC-ROBUSTNESS | 闭环容差筛查完成，缺失设计如实标记 | PASS | design_b=NOT_APPLICABLE |
| ACC-DATA-SOURCE | SPICE 指标全部标 `spice_simulation` | PASS | theory experiment metrics |
| ACC-NO-SILENT-DELETE | MC 记录数与采样数一致 | PASS | 30 records / 30 declared samples |
| ACC-HARDWARE | 外部硬件未执行的事实被保留 | NOT_VERIFIED | external_validation=NOT_VERIFIED |
| ACC-BUDGET | SPICE 预算未突破 | PASS | `{max_spice_runs:120, spice_runs:76, averaged_runs:0, wall_clock_s:94.65}` |

计数：PASS 12、NOT_VERIFIED 1；总体 `COMPLETE_WITH_OPEN_ITEMS`。
`build_acceptance`（`validation/validation_runner.py:368`）只在出现 FAIL 时
给 `PARTIAL_FAILURE`；存在 NOT_VERIFIED/INSUFFICIENT_DATA/NOT_APPLICABLE
时给 `COMPLETE_WITH_OPEN_ITEMS`。

## 6 预算

| 项 | 值 |
| --- | --- |
| SPICE 上限 / 实际 | 120 / 76 |
| 平均模型上限 / 实际 | 40 / 0 |
| 墙钟（standard） | 94.65 s |
| 上限覆盖参数 | `--max-runs 120` |

预算由 `experiments.BudgetCounter` 统一计数，所有实验共享；没有实验私开
SPICE 而不计数。

## 7 真实发现

### 7.1 理论对照（5 工况 × C/E）

工况：VAL001 12 V/2.5 Ω、VAL002 9 V/2.5 Ω、VAL003 16 V/2.5 Ω、
VAL004 12 V/5 Ω、VAL005 12 V/50 Ω。检查 70 项：**40 PASS、16 FAIL、
14 NOT_APPLICABLE**；模型交叉检查：**22 PASS、8 FAIL、5 INSUFFICIENT_DATA、
10 NOT_APPLICABLE**。

VAL001（C 变体）实测 Vout 5.017905 V、纹波 0.019407 V；E 变体
5.010399 V / 0.019397 V / 效率 93.331% / 总损耗 0.71746 W。
理想公式 Vout 5.342407 V、理想纹波 0.007883 V。

16 个 FAIL 全部来自理想公式：8 个 `TH-VOUT-IDEAL` 高于实测 0.25–0.37 V
（忽略导通压降等），8 个 `TH-VRIPPLE-IDEAL` 低于实测（理想公式忽略
ESR 等非理想项）。**非理想公式检查全部 PASS**，因此这不是仿真异常或
“通过率包装”，而是理想假设不适用。

VAL005 轻载/高阻进入 DCM：14 项 `NOT_APPLICABLE`；E 变体 Vout 7.4866 V、
电感谷值 −0.02755 A（DCM）；C 变体效率 101.365%，属于 DCM 下功率记账口径
失效，不能当物理效率；平均模型 5.0 V 检查 FAIL。轻载未强行套 CCM 公式，
这正是 ACC-CCM-APPLICABILITY 的证据。

### 7.2 时间步长收敛

请求 200/100/50/25/12.5 ns，完成 200/100/50/12.5 ns（25 ns ERROR 保留）。
成功点按步长排序后形成 3 个相邻对：200–100、100–50、50–12.5 ns；7 个指标
在这 3 对上都满足 `max(1 mV, 2%|m|)`（要求 2 对），因此工具给出
`NUMERICALLY_STABLE`。但 50→12.5 ns 的变化方向非单调（Vout 回升 +0.38 mV、
纹波回升 +0.085 mV），只是仍在容差内。结论应表述为“在当前 4 个成功步长上
按给定容差数值稳定”，而不是“已收敛到 12.5 ns 或真值”。
观测阶用 200/100/50 三点估计：Vout −2.39、输出纹波 −1.56、IL 纹波 −1.13、
IL 峰值 +1.03、总损耗 −3.90；效率与功率残差 `NOT_RESOLVED`（非单调/振荡）。
总体 `NUMERICALLY_STABLE`。阶次是经验值，JSON 注明“不是正确性证明”。

### 7.3 求解器对照

baseline 使用 ngspice 默认；7 个设置中 5 个完成、2 个失败。
`reltol_1e-4`、`reltol_1e-5` 属步长过小类失败，结果文件保留
`failure_reason`（通用 “Command 'run' failed”，`diagnosis.category=unknown`）；
`reltol_1e-3`、`method_gear`、`abstol_1e-10`、`vntol_1e-5` 完成。
12 个指标一致性检查 PASS（阈值：Vout 1 mV、纹波 0.5 mV、效率 0.1 个百分点）。
完成设置的结果接近只说明“数值等价”，不是物理验证。

### 7.4 守恒

| 检查 | 值 | 限值 | 状态 |
| --- | --- | --- | --- |
| 伏秒平衡 | 1.731e-5 | 0.02 | PASS |
| 电荷平衡 | 1.824e-5 | 0.02 | PASS |
| 节点电流一致性 | 6.92e-8 | 0.02 | PASS |
| 能量平衡 | 0.04242 | 0.05 | PASS |

`Pin=11.4908 W`、`Pout=10.0417 W`、`Ploss=0.9616 W`。
能量残差 4.24% 远大于瞬时功率残差 9e-6，这是窗口积分/储能近似造成的口径差，
不能互相替代。

### 7.5 容差

6 参数 × 3 水平 = 18 行，SPICE 全部执行。主导参数：
Vout→`inductor_dcr_ohm`、IL 纹波→`inductance_h`、效率→`inductor_dcr_ohm`。
容差为教学假设、独立均匀（L/C/DCR/KP/二极管 RS ±20%，ESR ±30%）。

### 7.6 角点

7 个显式角点全部完成，限值全部 PASS。`low_l_high_esr` 在 50 ns 失败后
按记录回退到 25 ns（`step_fallback` 保留两次尝试）。最差纹波
0.031306 V，为标称 0.019397 V 的 1.61 倍；Vout 范围
4.984263–5.029293 V（限值 4.9–5.1 V）。角点覆盖说明明确：
有限显式角点、非全局最坏、未跑全因子。

### 7.7 Monte Carlo

seed 42、PCG64、计划 30、完成 27、3 个 ERROR（mc-001/013/015）保留。
Vout 均值 5.011879 V、σ 0.012503 V、p5 4.992889 V、p95 5.028845 V；
纹波均值 0.020093 V、σ 0.004178 V、p95 0.025959 V；
效率均值 93.3741%、σ 0.23818%、p5 93.0024%；
IL 峰值均值 2.33428 A、p95 2.40359 A。
通过比例：全部样本 27/30=0.9（Wilson 0.743789–0.965400），
有效样本 27/27=1.0（0.875445–1.0）。**这不是产品良率**，是假设样本下的
条件比例；独立同分布是简化。

### 7.8 鲁棒性

- 4 个角点线性化筛查：0 失败；PM 64.666°–69.694°、带宽 112.916–113.605 Hz；
  增益裕度 NaN（未解析），并明确“非开关 SPICE AC”。
- 闭环 SPICE：nominal 最大偏差 0.014296 V、纹波 0.027530 V；
  `low_l_high_esr` 最大偏差 0.021031 V、纹波 0.039047 V（25 ns）。
- 设计 B：`NOT_APPLICABLE`，`stage6_missing`；没有改善比例。

## 8 限制与未解决问题

1. **第六阶段缺失**：无 docs 34–41 与对应模块，设计 B 鲁棒性无法对照；
   验收 JSON 记录 `stage6_missing`。
2. **无硬件验证**：`external_validation=NOT_VERIFIED`，ACC-HARDWARE 保留。
3. **3/30 Monte Carlo 样本未收敛**，分布尾部存在数值风险。
4. **2 个求解器设置失败**（更严 reltol），说明网表对步长/容差敏感。
5. **效率与功率残差收敛阶未解析**；25 ns 收敛点缺失。
6. **角点有限**（7 个），不证明全局最坏；未跑全因子。
7. **容差分布是教学假设**，非厂商批次数据，且独立采样忽略相关性。
8. **DCM 效率 101.365%** 暴露轻载功率记账局限，不能当物理效率。
9. **无温度/Monte Carlo 耦合**，温度固定 25 °C。
10. **无覆盖率测量**，测试通过不等于覆盖所有边界；仓库无 ruff 配置，未跑 lint。

## 9 产物路径

- 验收：`results/stage8/stage8_acceptance.json`、
  `stage8_acceptance_checks.csv`、`validation_summary.json`
- 矩阵：`results/stage8/credibility_matrix.csv` / `.json`
- 实验：`results/stage8/experiments/{theoretical_comparison,
  timestep_convergence,solver_comparison,conservation,tolerance,corner,
  robustness,monte_carlo_standard}.json`
- Monte Carlo：`results/stage8/monte_carlo/samples.csv`、
  `checkpoint_standard.json`
- 单次运行：`results/stage8/runs/<run_id>/{circuit.cir,metadata.json,metrics.json}`
- 报告：`results/stage8/stage8_validation_report.html`
- 图：`results/stage8/figures/{theory_comparison,timestep_convergence,
  tolerance_sensitivity,monte_carlo_vout,corner_comparison}.png`

## 10 面试题

**Q1：16 个理论检查 FAIL，为什么总体不是 PARTIAL_FAILURE？**
A：ACC 检查衡量“验证流程是否完成、是否有证据、是否保留失败”，理论 FAIL 是
验证发现（理想公式不适用），不是流程失败；总体状态也不代表硬件精度。

**Q2：为什么平均模型运行数是 0？**
A：平均模型与理论指标在离线计算并标 `averaged_model`，没有独立的平均模型
SPICE runner；`averaged_runs=0` 是口径事实，不是没做平均模型对照。

**Q3：25 ns 收敛点缺失会影响结论吗？**
A：会限制外推。25 ns 运行失败被保留，实际只有 4 个有效点；结论是“在该范围内
数值稳定”，不是“任意步长都稳定”。

**Q4：3 个 Monte Carlo 失败样本为什么不删掉？**
A：删除会抬高通过率并隐藏数值风险。结果同时给 27/30 与 27/27 两个口径，
失败原因原样保留，符合 ACC-NO-SILENT-DELETE。

**Q5：为什么设计 B 是 NOT_APPLICABLE？**
A：优化设计依赖第六阶段交付物，而仓库中没有；用合成基线会伪造改善比例，
因此明确标记 `stage6_missing`。

**Q6：VAL005 效率 101.365% 说明仿真错了吗？**
A：说明 DCM 轻载下功率记账口径失效（未覆盖全部损耗项/窗口），不是永动机；
该值不被当作物理效率，相关检查标 NOT_APPLICABLE/FAIL。

**Q7：求解器 5 个设置一致，能否说“结果与求解器无关”？**
A：不能。只有完成的 5 个设置一致，2 个更严 reltol 设置失败；一致性是数值
陈述，不是物理正确性证明。

**Q8：为什么没有 ruff 结果？**
A：仓库没有 ruff 配置；未配置就不运行，也不声称 lint 通过。环境检查只覆盖
`verify_environment` 与 `pip check`。
