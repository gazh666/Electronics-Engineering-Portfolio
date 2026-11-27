# 56 角点与最坏情况分析

本文说明第八阶段的**角点分析（corner analysis）**：如何挑选参数组合、每个角点
代表什么工程风险、如何用全因子网格描述覆盖范围、为什么“最坏角点”不等于
“全局最坏点”，以及一次真实的步长回退是如何被完整保留的。数值全部来自
`results/stage8/experiments/corner.json`。

> 结论先行：7 个显式角点全部 `COMPLETED`，记录的最坏输出纹波是
> `low_l_high_esr` 的 **0.031306 V**（标称 0.019397 V 的 **1.61 倍**），
> 该角点是在 50 ns 失败后按文档化流程回退到 25 ns 才跑通的。所有角点指标都在
> 工程限值内；`limit_status` 的字段名缺陷已在复核中修复并重跑（见第 8 节），
> 当前 PASS 是真实的限值判定结果。

## 1. 目标与范围

- 目标：在容差区间的**顶点**上检查性能是否越界，并给出可审查的组合理由。
- 范围：6 个参数、7 个显式角点，工况 `VAL001` / 变体 E，`Vin=12 V`、
  `Rload=2.5 Ω`、`fsw=100 kHz`、`end_time_s=0.005`。
- 不做：全因子 64 点、随机内点搜索、温度角点、器件老化角点。

代码入口：`experiments/corner_experiment.py:40` 的 `run_corner_experiment`；
角点定义在 `validation/corner_analysis.py:37` 的 `default_corners`。

## 2. 角点定义与选择理由

| 角点 | 参数组合 | 理由（`rationale`） |
| --- | --- | --- |
| `nominal` | 全部标称 | 基线 |
| `all_low` | 6 参数全 low | 最小储能/最小损耗的极端 |
| `all_high` | 6 参数全 high | 最大寄生/最大损耗的极端 |
| `low_l_high_esr` | L low + ESR high | 最小电感配最大 ESR：纹波最坏 |
| `low_l_high_dcr` | L low + DCR high | 最小电感配最大 DCR：导通+纹波 |
| `high_low_c` | L high + C low | 大电感小电容：电流慢、电压纹波大 |
| `low_kp_high_losses` | KP low + DCR high + DRS high | 弱 MOSFET + 最大寄生电阻 |

`Corner` 数据类（`validation/corner_analysis.py:20`）校验名字非空、level 只能是
`low/nominal/high`；`build_corner_config`（第 91 行）把 level 映射成 YAML 中
的具体数值，再交给 `apply_parameters`。若角点引用了未登记的容差参数，直接抛
`ValueError`，不会静默跳过。

角点不是随机抽样，而是**人为构造的风险切片**。例如 `all_high` 在现实中几乎
不会同时发生（DCR 大通常意味着线径细，ESR 大通常意味着电解液/介质不同），
它的作用是压力测试，而不是概率估计。

## 3. 参数组合与覆盖范围

6 个参数、每参数 2 档（low/high）共有

$$
2^6 = 64
$$

个顶点；若把 nominal 也算作档位，则是 `3^6 = 729` 个组合。
`full_factorial_corners`（`validation/corner_analysis.py:104`）支持 1–6 个参数
的全因子枚举，超过 6 个直接报错。本阶段**只执行了 7 个显式角点**，没有跑全因子，
`corner.json` 的 `summary.coverage_note` 原文即为：

```
finite explicit corners only; not a proof of global worst case; full factorial was not run
```

7 / 64 ≈ 10.9 % 的顶点覆盖率。这个数字只能说明“覆盖了 7 个代表性方向”，
不能说明“剩余的 57 个顶点不会更差”。

## 4. 真实结果

| 角点 | Vout (V) | 输出纹波 (V) | 效率 (%) | 电感峰值 (A) | 总损耗 (W) |
| --- | ---: | ---: | ---: | ---: | ---: |
| nominal | 5.010399 | 0.019397 | 93.3315 | 2.32934 | 0.717464 |
| all_low | 5.029293 | 0.018660 | 93.6858 | 2.41812 | 0.682317 |
| all_high | 4.990754 | 0.020877 | 92.9995 | 2.26741 | 0.750143 |
| low_l_high_esr | 5.010044 | **0.031306** | 93.2763 | 2.41038 | 0.723823 |
| low_l_high_dcr | 4.990981 | 0.024199 | 92.9691 | 2.40280 | 0.753669 |
| high_low_c | 5.010493 | 0.016255 | 93.3598 | 2.27512 | 0.714203 |
| low_kp_high_losses | 4.984263 | 0.019352 | 92.8530 | 2.31880 | 0.765011 |

工程限值（`corner.json` → `engineering_limits`）：输出电压 4.9–5.1 V、
输出纹波 ≤ 0.05 V、系统效率 ≥ 85 %。逐项人工核对：

- Vout 范围 4.984263–5.029293 V，全部在 ±100 mV 内；最靠近边界的是
  `low_kp_high_losses`（-15.7 mV）与 `all_low`（+29.3 mV）。
- 纹波最大 0.031306 V，仅为 0.05 V 限值的 62.6 %。
- 效率最低 92.8530 %，比 85 % 限值高 7.85 个百分点。

因此“7 个角点都满足限值”这个结论成立；修复后的自动判定与手工核对一致
（第 8 节）。

## 5. 最坏纹波：为什么是 `low_l_high_esr`

输出纹波可近似分解为电容充电分量与 ESR 分量：

$$
V_{pp}\approx \frac{\Delta i_L}{8 f_{sw} C}+\Delta i_L\cdot ESR
$$

`low_l_high_esr` 同时把 `Δi_L` 推到最大（L 最小）并把 ESR 乘到最大，两项同向
叠加。实测支持这个分解：

| 分量（V） | `low_l_high_esr` | `nominal` | 备注 |
| --- | ---: | ---: | --- |
| `output_voltage_esr_ripple_vpp` | 0.031181 | 0.019259 | 占主导 |
| `output_voltage_capacitor_ripple_vpp` | 0.010039 | 0.008081 | 次要 |
| `output_voltage_ripple_vpp` | 0.031306 | 0.019397 | 合计 |

ESR 分量 0.031181 V 已占总纹波 0.031306 V 的 99.6 %，说明该角点的纹波几乎
完全由 ESR 决定。反观 `high_low_c`（C 最小），纹波只有 0.016255 V，反而低于
标称，因为 L 增大把 `Δi_L` 压小了——这正是“单看 C 会误判”的例子。

效率最差的是 `low_kp_high_losses`（92.8530 %），不是 `all_high`；原因是该角点
同时叠加了 KP 低（MOSFET 损耗上升）与 DCR/DRS 高，而 `all_high` 的 KP 是高的。

## 6. 内点与“最坏点”

`worst_corner`（`validation/corner_analysis.py:171`）只在**已执行的记录**里按
`|metric|` 取最大，因此 JSON 中的 `worst_ripple` 必然是某个角点，而不是连续
参数空间里的真正极值。JSON 记录：

- `worst_ripple` = `low_l_high_esr`，0.031306 V；
- `worst_output_voltage` = `all_low`，5.029293 V（按绝对值取最大）。

为什么有限角点不能证明全局最坏：

1. 顶点只覆盖边界，**内点**（例如 L=-10 %、ESR=+15 %、DCR=+5 % 同时出现）未评估；
   若某个指标对参数非单调（如效率在某个 DCR/KP 组合处出现拐点），极值可能落在
   内部。
2. 角点之间没有插值或代理模型，无法给出“任意组合的上界”。
3. 6 维空间只取了 7 个点，覆盖率约 11 %；相关性假设为独立，真实批次的相关
   方向可能放大某个组合。
4. 因此正确表述是“在 7 个显式角点上未越界”，而不是“设计在所有容差组合下安全”。

若要把结论做强，下一步应做全因子 64 点或拉丁超立方 + 代理模型（如 Kriging），
再对代理模型做内点优化。

## 7. 一次真实的步长回退（50 ns → 25 ns）

`low_l_high_esr` 在标准步长 50 ns 下 SPICE 报错，实验按
`experiments/corner_experiment.py:70-85` 的逻辑做了**唯一一次**更细步长重试：

```json
"step_fallback": {
  "requested_step_time_s": 5e-08,
  "used_step_time_s": 2.5e-08,
  "attempts": [
    {"step_time_s": 5e-08, "status": "ERROR"},
    {"step_time_s": 2.5e-08, "status": "COMPLETED"}
  ]
}
```

三点必须讲清楚：

1. **原始失败被保留**：`attempts` 里 50 ns 的 `ERROR` 没有被删掉或改写。
2. **只允许一次回退**：代码不是循环降步长，25 ns 再失败就记录 `ERROR` 结束。
3. **回退改变了解析口径**：该角点的波形采样密度高于其他 6 个角点，因此它的
   纹波数值与 50 ns 角点不是完全同口径；这也是它单独标注 `step_fallback` 的原因。

其余 6 个角点的 `attempts` 都只有一条 50 ns `COMPLETED` 记录。`budget` 中
`spice_runs=44` 同样是跨任务累计计数器，不等于“44 次角点仿真”。

## 8. 判定口径与一个已修复的实现缺陷

`corner_records`（`validation/corner_analysis.py:116`）最初只用
`rule.get("minimum")` / `rule.get("maximum")` 读取限值，但
`_engineering_limits`（`experiments/corner_experiment.py:28`）从
`configs/performance_limits.yaml` 读出的键是 `min` / `max`。两者不匹配时，
上下限都是 `None`，`ok` 恒为 `True`，`limit_status` 必然 `PASS`——这是**空真**。

该缺陷在文档复核时被发现并修复：`corner_analysis.py:135-136` 现在同时接受
`minimum/maximum` 与 `min/max`。修复后重新执行 standard 验收，7 个角点的
`limit_status` 由真实的 4.9–5.1 V、≤0.05 V、85–100% 限值计算得出，结果仍为
7 PASS / 0 FAIL / 0 ERROR（`results/stage8/experiments/corner.json`）。
修复前任何“7 PASS”的结论都不能作为证据；修复后的 PASS 才是限值判定结果。

## 9. 输入、输出与错误处理

- 输入：`configs/component_tolerances.yaml`、`configs/performance_limits.yaml`
  （`profiles.target_5v_design`）、`VAL001` 参考工况、7 个 `Corner` 定义。
- 输出：`results/stage8/experiments/corner.json`；每个角点的
  `results/stage8/runs/<run_id>/`（`circuit.cir`、`metadata.json`、
  `metrics.json`）；图 `results/stage8/figures/corner_comparison.png`。
- 错误处理：`run_case` 捕获异常并返回 `status="ERROR"` + `failure_reason` +
  `diagnosis`（`experiments/_stage8_common.py:182`）；`corner_experiment`
  只对失败角点重试一次 25 ns；仍失败则 `status="ERROR"` 且
  `corner_records` 把 `limit_status` 标成 `ERROR`，不会混入 PASS。
- 本次 7 个角点全部 `COMPLETED`，`summary.errors=0`。

## 10. 已知局限

1. 只覆盖 7 个显式角点，不是全因子，也不是全局最坏证明。
2. `limit_status` 的键名缺陷已修复并重跑；当前 PASS 为真实限值判定，但仍只覆盖显式角点。
3. 角点是人为组合，`all_low`/`all_high` 在真实批次中几乎不可能同时出现。
4. 参数独立假设；真实 MOSFET 的 KP 与寄生、电容的 C 与 ESR 可能相关。
5. 无温度角点（全部 25 °C），无老化角点。
6. `low_l_high_esr` 使用 25 ns，与其他角点 50 ns 不同口径，比较时需注明。

## 11. 面试题

**Q1：角点分析和 Monte Carlo 的区别是什么？**
角点是确定性的边界压力测试，回答“极端组合会不会坏”；Monte Carlo 按分布
随机抽样，回答“在假设分布下指标如何分布”。前者覆盖性弱但可解释，后者
需要分布假设且样本有限。

**Q2：为什么 7 个角点不能证明全局最坏？**
顶点不覆盖内点，指标可能非单调；没有插值/代理模型给出上界；6 维空间只取了
7 个点；相关性被忽略。只能声明“已检查的角点未越界”。

**Q3：`low_l_high_esr` 的纹波为什么远大于 `all_high`？**
纹波 ≈ Δi_L/(8fC) + Δi_L·ESR。`low_l_high_esr` 的 L 最小使 Δi_L 最大，
ESR 又最大，两项同向；`all_high` 的 L 最大，Δi_L 小，抵消了 ESR 增大。

**Q4：步长回退会不会让结果不可比？**
会带来采样密度差异，但方向与量级仍可用；正确做法是保留原始失败、记录
`used_step_time_s`，并在比较时注明该角点口径不同。本项目只允许一次回退，
避免“不断降步长直到通过”的隐性调参。

**Q5：`limit_status` 全 PASS 有什么问题？**
本次开发中曾出现限值字典用 `min/max`、判定函数读 `minimum/maximum` 的键名
不匹配，导致上下限为 `None`、`ok` 恒真、PASS 空真。修复方式是判定函数同时
接受两种键名，并重新执行验收；这说明“检查通过”本身也必须被测试，不能只看
状态字段。

**Q6：如何把角点分析升级为可信的最坏情况分析？**
先做 64 点全因子确认单调性，再用拉丁超立方/代理模型拟合，最后在代理模型上
做内点优化并回到 SPICE 复核；同时把温度与相关性纳入因素。
