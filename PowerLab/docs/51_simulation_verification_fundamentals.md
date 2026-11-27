# 51 仿真验证的基本概念：数值一致不等于物理确认

> 本文件说明第八阶段在“验证”一词下区分的几种不同工作，并只用 `results/stage8/`
> 中的真实运行结果作证据。所有数字都能在对应 JSON 或 `runs/<run_id>/` 证据目录中追溯，
> 没有外部硬件测量数据。

## 1. 目的与范围

范围：解释仿真验证、物理确认、模型误差、数值误差、参数不确定性、软件测试与工程验证
的区别，并说明本项目如何用字段和标签把这几件事分开记录。

不在范围：控制器设计、器件选型、热设计、量产良率。本文件不给出任何“硬件精度达标”的结论。

判断标准只有一条：**仿真结果之间一致，只能证明数值与模型自洽；不能证明真实电路性能。**
该原则写在 `validation/models.py:1-7` 的模块说明和 `results/stage8/experiments/*.json`
的 `disclaimer` 字段里。

## 2. 五个必须分开的概念

### 2.1 仿真验证与物理确认

| 概念 | 定义 | 本项目状态 |
| --- | --- | --- |
| 仿真验证 | 在给定模型、参数、求解器下，检查公式 / 平均模型 / 开关 SPICE 是否互相自洽 | 已执行，结果见 `results/stage8/validation_summary.json` |
| 物理确认 | 在真实 PCB、真实器件上用示波器与电子负载测量 | **未执行**：`data_source_policy.external_validation = "not_available"` |

验收项 `ACC-HARDWARE` 的 evidence 就是 `external_validation=NOT_VERIFIED`
（`results/stage8/stage8_acceptance.json`，`validation/validation_runner.py:482-488`）。
它被保留为 `NOT_VERIFIED`，而不是伪造一个 PASS。

### 2.2 模型误差

模型误差来自抽象本身：理想公式忽略导通压降、ESR 与开关过程；平均模型没有纹波；
Level-1 MOSFET 没有温度、沟道长度调制和厂商寄生参数。

VAL001（12 V / 2.5 Ω，占空比 0.445201）的真实对照：

| 指标 | 理想 CCM | 非理想 CCM 估计 | SPICE C | SPICE E |
| --- | --- | --- | --- | --- |
| 平均 Vout (V) | 5.3424 | 5.0000 | 5.0179 | 5.0104 |
| 电感纹波 (A) | 0.6306 | 0.6631 | 0.6519 | 0.6497 |
| 输出纹波 Vpp (V) | 0.007883 | —（未建模 ESR） | 0.019407 | 0.019397 |

理想 Vout 相对偏差为 −6.07%（C）与 −6.21%（E）；理想纹波低估 +146.2% / +146.1%
（即实测约为理想值的 2.46 倍）。非理想公式的 Vout 偏差仅 +0.36% / +0.21%。
来源：`results/stage8/experiments/theoretical_comparison.json` 的 `theory_checks`。

结论：这里的偏差主要不是求解器造成的，而是“理想公式不含 Rds(on)、VF、DCR、ESR”造成的。

### 2.3 数值误差

数值误差来自时间离散、Newton 迭代容差与波形插值。时间步长收敛实验（VAL001，变体 E）
在 200 / 100 / 50 / 12.5 ns 四个成功点上给出：

| 最大步长 | Vout (V) | Vpp (V) | 效率 (%) | 总损耗 (W) |
| --- | --- | --- | --- | --- |
| 200 ns | 5.011164 | 0.020044 | 93.3487 | 0.713969 |
| 100 ns | 5.011042 | 0.019881 | 93.3762 | 0.714188 |
| 50 ns | 5.010399 | 0.019397 | 93.3315 | 0.717464 |
| 12.5 ns | 5.010775 | 0.019482 | 93.3456 | 0.716171 |

25 ns 运行失败。四个成功点的 Vout 极差约 0.76 mV，而 2.2 节的模型偏差是 0.33 V，两者
相差两个数量级以上。**这只能说明本工况下数值误差小于模型误差，不能外推到其它工况。**

### 2.4 参数不确定性

参数不确定性来自器件容差、温度与模型参数本身不确定：

- 单参数一阶容差覆盖 6 个参数、18 行；Vout 与效率的主导参数都是 `inductor_dcr_ohm`，
  电感纹波的主导参数是 `inductance_h`（`validation_summary.json` 的 `tolerance`）。
- 角点分析执行 7 个有限显式角点，7 个通过，但 `coverage_note` 明确写着
  “finite explicit corners only; not a proof of global worst case; full factorial was not run”。
- Monte Carlo standard 档 30 个样本、27 个完成；全部样本通过比例 27/30 = 0.9，
  Wilson 95% 区间 0.744–0.965；有效样本 27/27。JSON 明确注明这是“在假设分布下的抽样不确定性，
  不是良率保证”。

另外，每个工况的占空比是用平均 CCM 模型反解出来的（`validation/reference_cases.py:152-158`
的 `calibrated_duty_for_case` → `solve_operating_duty`），属于 `project_assumption`，
不是实时闭环搜索结果。

### 2.5 软件测试与工程验证

| 层次 | 回答的问题 | 本项目证据 |
| --- | --- | --- |
| 软件测试 | 代码路径、边界与错误处理是否正确 | `tests/` 下的 pytest 用例 |
| 仿真验证 | 不同数值模型是否自洽、公式在适用区是否吻合 | 40 PASS / 16 FAIL / 14 NOT_APPLICABLE（理论检查） |
| 工程验收 | 流程是否完整、失败与缺口是否被如实记录 | 13 项检查：12 PASS + 1 NOT_VERIFIED → `COMPLETE_WITH_OPEN_ITEMS` |
| 硬件确认 | 真实电路是否满足规格 | 未执行 |

`stage8_acceptance.json` 的 `note` 明确写着：FAIL findings 是验证结果，不是流程失败；
总体状态只描述流程完整性，不描述硬件精度。16 个 FAIL 全部来自理想公式的高估/低估，
非理想 Vout / 平均电流 / 纹波检查全部 PASS。

## 3. 数据来源标签与状态机

`validation/models.py:29-37` 定义 7 个允许的数据来源：

| 标签 | 含义 | 本阶段是否使用 |
| --- | --- | --- |
| `analytical_theory` | 解析公式 | 是 |
| `averaged_model` | 周期平均状态空间 | 是 |
| `spice_simulation` | 开关级 SPICE 波形 | 是 |
| `spice_derived` | 由 SPICE 样本统计出的量 | 是（Monte Carlo 统计） |
| `synthetic_test_data` | 测试用合成数据 | 仅测试 |
| `project_assumption` | 项目假设（如容差范围、占空比校准） | 是 |
| `experimental_measurement` | 真实测量 | **未使用**；硬件状态写作 `not_available` |

`ValidationStatus`（`validation/models.py:17-25`）共 8 个取值，语义不可混用：

| 状态 | 含义 |
| --- | --- |
| `PASS` | 在给定限值内通过，不代表硬件通过 |
| `FAIL` | 超出限值，是真实结果 |
| `ERROR` | 运行或数值失败（如求解器报错） |
| `NOT_APPLICABLE` | 公式/模型在该工况不适用，不用 0 冒充 |
| `NOT_VERIFIED` | 未执行或无法验证（如硬件） |
| `INSUFFICIENT_DATA` | 数据缺失，不能判定 |
| `BLOCKED` / `SKIP` | 前置缺失 / 未请求 |

汇总规则见 `summarize_status`（`models.py:145-162`）：ERROR > FAIL > 全 PASS 才 PASS；
全部为 NA/SKIP 时为 NOT_APPLICABLE；其余混合作 NOT_VERIFIED。

## 4. 源码位置与关键接口

| 内容 | 路径 | 真实类/函数（行号） |
| --- | --- | --- |
| 状态与数据来源枚举 | `validation/models.py` | `ValidationStatus`(17)、`DATA_SOURCES`(29)、`validate_data_source`(49) |
| 单项检查结构 | 同上 | `ValidationCheck`(55)、`to_dict`(73) |
| 结果容器与计数 | 同上 | `ValidationResult`(92)、`counts`(117) |
| 检查构造与限值判定 | `validation/theoretical_validation.py` | `make_check`(121-191) |
| 理论对照 | 同上 | `evaluate_theory`(194-309) |
| 稳态窗口指标 | `experiments/_stage8_common.py` | `metrics_from_result`(62-83) |
| 验收检查生成 | `validation/validation_runner.py` | `build_acceptance`(368-523)、ACC-HARDWARE(482) |
| 可信度矩阵 | 同上 | `credibility_matrix`(299-353) |
| 硬件可用性标记 | `configs/validation_limits.yaml` | `metadata.hardware_validation_available: false`(44) |

关键函数的输入/输出/错误处理：

- `validate_data_source(source: str) -> str`：白名单校验，未知标签抛 `ValueError`。
- `make_check(...) -> ValidationCheck`：`actual` 或 `reference` 为 `None` 返回
  `INSUFFICIENT_DATA`；`applicable=False` 返回 `NOT_APPLICABLE`；非有限值返回 `ERROR`；
  否则按 `allowed = max(abs_tol, rel_tol * |reference|)` 判定 PASS/FAIL（`theoretical_validation.py:135-191`）。
- `build_acceptance(summary, outputs) -> dict`：按 13 项检查生成总体状态，存在 FAIL 才是
  `PARTIAL_FAILURE`，存在 NOT_VERIFIED/INSUFFICIENT_DATA/NOT_APPLICABLE 时为
  `COMPLETE_WITH_OPEN_ITEMS`（`validation_runner.py:497-511`）。
- `metrics_from_result(result, config)`：从最后 5 个开关周期的稳态窗口取 Vout 均值、
  电感电流谷值/均值/纹波，并写入 `data_source` 与 `run_id`。

## 5. 真实运行证据

标准运行（环境：Python 3.11.18、PySpice 1.5 + ngspice-34、numpy 1.26.4、scipy 1.17.1、
pandas 3.0.6、matplotlib 3.11.2）：

```powershell
conda run -n kaifa_power python -m scripts.buck_stage8_demo --profile standard --max-runs 120
```

| 项目 | 实际值 | 来源 |
| --- | --- | --- |
| SPICE 运行次数 / 上限 | 76 / 120 | `stage8_acceptance.json` → ACC-BUDGET |
| 平均模型运行次数 | 0 | 同上 |
| 验收总耗时 | 94.65 s | 同上 `wall_clock_s` |
| 验收检查 | 13 项，12 PASS，1 NOT_VERIFIED | `results/stage8/stage8_acceptance_checks.csv` |
| 总体状态 | `COMPLETE_WITH_OPEN_ITEMS` | `results/stage8/stage8_acceptance.json` |
| 理论检查（5 工况 × 2 变体 × 7 项） | 40 PASS / 16 FAIL / 14 NOT_APPLICABLE | `theoretical_comparison.json` → `summary` |
| 收敛状态 | `NUMERICALLY_STABLE` | `validation_summary.json` → `convergence` |
| 求解器对照 | 12 PASS + 2 ERROR | `solver_comparison.json` → `summary` |

图：`results/stage8/figures/theory_comparison.png`（VAL001 五种模型的 Vout 柱状图）。
图中理想 CCM 柱明显高于 5.0 V 目标线，非理想估计、平均模型、SPICE C、SPICE E 四柱都在
5.0 V 附近——这正是“模型误差远大于数值误差”的直观表现，而不是硬件精度证明。

## 6. 为什么仿真不能替代硬件测量

1. 器件模型是教学级 Level-1，没有厂商的电容、栅电荷、反向恢复与温度系数。
2. 没有热设计：结温、热阻、温漂与降额完全未建模。
3. 没有 PCB 寄生：走线电感、地弹、探头负载与测量带宽。
4. 没有 EMI/EMC、纹波高频分量与开关振铃的真实频谱。
5. 参数是标称值加假设分布，没有批次一致性、老化与焊接差异。
6. 占空比校准本身是平均模型假设；它在硬件上是否成立未被验证。

## 7. 已知局限与失败案例

- 外部硬件实验完全未执行，`ACC-HARDWARE` 永远为 `NOT_VERIFIED`。
- Monte Carlo 的通过比例依赖假设分布，JSON 明确“不是量产良率”。
- 角点只覆盖 7 个有限组合，不是全局最坏情况。
- 第六阶段闭环设计缺失，鲁棒性设计 B 标记为 `NOT_APPLICABLE`（`known_gaps: stage6_missing`）。
- 16 个理论 FAIL 是真实的高估/低估，没有被“修波形”或放宽限值消除。

## 8. 技术面试题

1. **仿真验证通过是否等于硬件达标？** 不等于。PASS 只表示在给定限值内自洽；本项目
   `external_validation` 始终是 `not_available`，硬件项是 `NOT_VERIFIED`。
2. **如何区分模型误差和数值误差？** 固定模型、只改步长/求解器得到的变化是数值误差
   （本项目 Vout 极差约 0.76 mV）；换模型层级得到的变化是模型误差（理想 vs SPICE 约 0.33 V）。
3. **为什么理想公式的 Vout 偏高 6%？** 它忽略 Rds(on)、二极管 VF、DCR 与 ESR 的直流压降；
   非理想公式把 Vout 从 5.3424 V 拉回到 5.0000 V，SPICE 实测 5.0104 V。
4. **`NOT_APPLICABLE` 与 `NOT_VERIFIED` 有何区别？** 前者是“公式在该工况不成立”（如 DCM 下的
   CCM 公式），后者是“根本没有执行验证”（如硬件测量）。
5. **为什么 50 Ω 工况的 14 项 CCM 检查全部 NOT_APPLICABLE？** 实测电感谷值为 −0.02755 A，
   电流断续，CCM 公式前提不成立；强行比较会得到无意义的 FAIL。
6. **软件测试全部通过说明什么？** 说明代码路径、边界与错误处理正确；它不验证电路物理，
   也不能替代工程验收或硬件测量。
7. **平均模型算出的效率能作为系统效率结论吗？** 不能。它只含导通与二极管损耗，
   不含开关过渡损耗；本阶段平均模型的纹波与效率对照都被标记为 `NOT_APPLICABLE`。
