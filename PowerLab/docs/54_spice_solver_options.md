# 54 SPICE 求解器选项与数值失败诊断

> 本文件说明 ngspice 瞬态求解的基本机制、`RELTOL/ABSTOL/VNTOL` 与积分方法的作用，
> 并引用 `results/stage8/experiments/solver_comparison.json` 的真实七组对照。
> 原则：一次只改一个选项；失败必须保留为 `ERROR` 并记录原始报错，不得用“调参到能跑”掩盖问题。

## 1. 目的与范围

目的：说明求解器容差与积分方法如何影响结果，以及失败时如何诊断，
并证明“两种设置结果接近”只是数值等价，不是物理验证。

范围：VAL001、变体 E、50 ns、5 ms 稳态；7 次尝试（1 个 baseline + 6 个变体）。
不在范围：步长细化（见 `docs/53`）、模型误差（见 `docs/51`）。

## 2. SPICE 数值求解基础

瞬态分析在每个时间点求解改进节点方程（MNA）：

```text
G(x)·x + C·dx/dt = b(t)
```

1. 电容/电感用伴随模型（梯形或后向欧拉）离散成等效电导与电流源；
2. 非线性器件（MOSFET、二极管）在每个 Newton 迭代点线性化；
3. 迭代直到节点电压与支路电流满足容差，否则减小步长重试；
4. 步长由局部截断误差（LTE）与 `TMAX` 共同控制。

Newton 迭代的收敛判据（ngspice 形式）：

```text
|v_new − v_old| <= RELTOL·|v_new| + VNTOL      （电压）
|i_new − i_old| <= RELTOL·|i_new| + ABSTOL      （电流）
```

## 3. 三个容差与两个积分方法

| 选项 | 作用 | ngspice 默认 | 调紧的风险 |
| --- | --- | --- | --- |
| `RELTOL` | 相对容差，主导收敛难度 | 1e-3 | 迭代次数暴涨，易触发 “Timestep too small” |
| `ABSTOL` | 电流绝对容差 | 1e-12 A | 对 mA 级电流几乎无影响 |
| `VNTOL` | 电压绝对容差 | 1e-6 V | 对 mV 级纹波影响有限 |
| `method` | 积分方法 | `trap` | `gear` 更阻尼，可能压低振铃 |
| `TRTOL` | LTE 缩放因子（默认 7） | 7 | 本阶段未改动 |

- **梯形法（trap）**：二阶、精度高，但对刚性/开关电路可能产生不衰减的数值振铃。
- **Gear（BDF）**：一阶/二阶、数值阻尼更强，稳定但可能抹平真实高频成分。
- 项目实现只允许 `trap` 与 `gear` 两种取值（`validation/solver_validation.py:41-42`）。

初值与数值阻尼：

- 工作点由 DC 解给出；`.ic` 可强制节点初值，`UIC` 跳过工作点直接使用初值。
- 开关电路常用 `gmin` 步进、源步进帮助 DC 收敛；瞬态起步阶段可用 `off` 让器件从关断开始。
- 数值阻尼不是物理阻尼；用 `gear` 得到的“更平滑”波形不能当作真实电路更干净。

## 4. 源码位置与关键接口

| 内容 | 路径 | 真实类/函数（行号） |
| --- | --- | --- |
| 求解器设置结构 | `validation/solver_validation.py` | `SolverSettings`(26-88) |
| 生成 `.options` | 同上 | `spice_line`(74-88)、`injected_options`(60-72) |
| 注入网表 | 同上 | `apply_solver_options`(91-98) |
| 带选项运行 | 同上 | `run_with_solver_options`(101-145) |
| 失败模式表 | 同上 | `FAILURE_PATTERNS`(148-155)、`classify_failure`(158-174) |
| 结果对照 | 同上 | `compare_solver_runs`(188-235)、`summarize_solver_checks`(238-256) |
| 实验编排 | `experiments/solver_comparison.py` | `run_solver_comparison`(39-215) |
| 计划配置 | `configs/numerical_validation.yaml` | `solver_comparison`(37-50) |

关键函数输入/输出/错误处理：

- `SolverSettings(name, method="trap", reltol=1e-4, abstol=1e-12, vntol=1e-6, ...)`：
  方法非法或容差非正/非有限时抛 `ValueError`；`use_ngspice_defaults=True` 时不注入任何选项。
- `apply_solver_options(circuit, settings)`：把 `.options ...` 追加到 `circuit.raw_spice`；
  不修改原始网表文件，仅作用于内存中的电路对象。
- `run_with_solver_options(config, variant, settings, ...)`：覆盖终止时间/步长后校验
  `validate_for_switching`，返回带 `solver_settings` 与 `analysis_settings` 元数据的结果。
- `classify_failure(message)`：按正则匹配 6 类失败；**无法匹配时返回 `unknown` +
  `NOT_VERIFIED`**，并建议先看完整 ngspice 日志，而不是乱改参数。
- `compare_solver_runs`：以 baseline 为参考，默认 Vout 绝对 1 mV、纹波绝对 0.5 mV 或 2%、
  效率 0.1 个百分点；失败变体只生成 `ERROR` 检查，不与 0 比较。

## 5. 真实对照结果

baseline 是 `use_ngspice_defaults=True`、不注入任何 `.options`；每个变体只改一个选项。
共 7 次尝试，**5 次完成、2 次失败**：

| 变体 | 状态 | Vout (V) | Vpp (V) | 效率 (%) |
| --- | --- | --- | --- | --- |
| baseline（默认） | COMPLETED | 5.010399 | 0.019397 | 93.3315 |
| `reltol=1e-3` | COMPLETED | 5.010399 | 0.019397 | 93.3315 |
| `reltol=1e-4` | **ERROR** | — | — | — |
| `reltol=1e-5` | **ERROR** | — | — | — |
| `method=gear` | COMPLETED | 5.010513 | 0.019468 | 93.3274 |
| `abstol=1e-10` | COMPLETED | 5.010524 | 0.019460 | 93.3392 |
| `vntol=1e-5` | COMPLETED | 5.010473 | 0.019650 | 93.3319 |

- `reltol=1e-3` 与 baseline 指标逐位相同（5.010398826016712 V 等），与 ngspice 默认
  `RELTOL=1e-3` 一致。
- 三个成功变体相对 baseline 的偏差：Vout 最大 +0.13 mV、纹波最大 +0.25 mV（vntol）、
  效率最大 +0.0077 个百分点，全部远小于 1 mV / 0.5 mV / 0.1 个百分点的限值。
- 检查计数：**12 PASS + 2 ERROR**，`summary.status = ERROR`
  （`solver_comparison.json`）。12 个 PASS 是 4 个完成变体 × 3 项指标；
  2 个 ERROR 是两次 `reltol` 失败，没有被排除在统计之外。

失败细节：`reltol=1e-4` 与 `reltol=1e-5` 都报 “Timestep too small”，涉及节点
`m1#source` 与 `vlsense#branch`。外层异常只保留了
`transient simulation failed ...: Command 'run' failed`，因此 `classify_failure` 返回
`category = "unknown"`，`retry_advice` 是“先检查完整 ngspice 日志”。
这正好说明：**错误分类器只能看到 Python 层文本，真正的诊断依据在 ngspice 日志里。**

## 6. 失败诊断与教训

常见失败类别（`FAILURE_PATTERNS`）：

| 类别 | 触发文本 | 处理方向 |
| --- | --- | --- |
| `timestep_too_small` | “timestep too small” | 放宽一次最大步长并记录回退 |
| `convergence_failure` | “no convergence / gmin / source stepping” | 试 gear 或放宽 reltol，两结果都要留 |
| `singular_matrix` | “singular matrix” | 查悬空节点与初值 |
| `missing_model` | “model not found” | 检查模型卡是否进入网表 |
| `invalid_netlist` | “unknown parameter / bad number” | 查生成网表，不改结果 |
| `non_finite_output` | “nan / inf” | 按 `INVALID_DATA` 处理 |

本实验的教训：

1. **不要盲目调紧 `RELTOL`**：1e-4、1e-5 在本电路直接失败，而 1e-3 已经与默认完全一致。
2. **一次只改一个选项**，才能把差异归因；本实验的 6 个变体都只注入一个选项。
3. **失败也是证据**：两个 ERROR 保留在 `runs` 与 `checks` 中，`summary.status` 因此为 ERROR。
4. **默认值不是“低精度”**：baseline 与 1e-3 逐位相同，说明想靠收紧容差“更准”往往只是更慢。

## 7. 图表

本实验没有生成专用图片；与之最接近的数值设置图是
`results/stage8/figures/timestep_convergence.png`（步长细化，不是求解器容差）。
求解器结果的完整表格与失败文本见 `results/stage8/experiments/solver_comparison.json`。

## 8. 已知局限与失败案例

- 只在 VAL001/E 上比较；其它工况的容差敏感性未验证。
- 两次 `reltol` 失败只有外层异常文本，ngspice 日志未进入 JSON，诊断分类为 `unknown`。
- 未测试 `TRTOL`、`CHGTOL`、`gmin`、源步进等选项；默认值与 `1e-3` 的等价性是从逐位相同
  的结果推断的。
- 结果接近只说明当前工况数值等价，不能推断硬件精度；`summarize_solver_checks` 的
  `note` 明确写着 “solver agreement is a numerical statement, not hardware accuracy”。
- 数值阻尼对真实高频分量的影响未量化。

## 9. 技术面试题

1. **RELTOL、ABSTOL、VNTOL 分别约束什么？** RELTOL 是相对容差（电压和电流都用），
   ABSTOL 约束接近零的电流，VNTOL 约束接近零的电压；收敛要求同时满足。
2. **为什么调紧 RELTOL 反而会失败？** 每次 Newton 迭代要更精确，迭代次数与内部步长缩小，
   最终触发 “Timestep too small”；本实验 1e-4、1e-5 都失败，1e-3 与默认一致。
3. **梯形法和 Gear 的取舍是什么？** trap 二阶精度高但可能数值振铃；Gear 阻尼强、稳定，
   但可能压低真实高频。本实验 gear 与 baseline 的 Vout 只差 0.11 mV。
4. **“Timestep too small” 应该怎么处理？** 先看 ngspice 日志定位节点（本例 `m1#source`、
   `vlsense#branch`），再考虑放宽一次最大步长或换积分方法，并保留回退记录。
5. **为什么 baseline 指标与 reltol=1e-3 完全相同？** 因为 ngspice 默认 RELTOL 就是 1e-3，
   注入相同值不改变任何计算路径。
6. **求解器结果一致能否说明模型正确？** 不能。它只说明两种数值设置在同一模型上收敛到同一解；
   模型误差与硬件精度是完全不同的问题。
7. **失败变体为什么也要参与统计？** 否则会得到“7 项全 PASS”的假象；保留 2 个 ERROR
   才能反映真实可运行性与鲁棒性。
