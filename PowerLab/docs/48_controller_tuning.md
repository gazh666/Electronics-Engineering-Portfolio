# 48 控制器整定与参数矩阵

## 1. 整定流程

1. 由平均模型得到控制到输出的 `Gp(s)`；
2. 按目标穿越频率 `fc` 与 PI 零点 `fz` 设计 `Kp`、`Ki`；
3. 计算正弦载波小信号增益 `Gpwm`；
4. 在 3×3 参数矩阵上评估相位裕度、闭环极点、阶跃指标；
5. 选出的参数用真实 SPICE 复核负载阶跃与启动；
6. 失败或“更激进但表现更好”的结果如实保留，不反向修改结论。

## 2. 源码路径与接口

| 内容 | 路径 | 真实函数 |
| --- | --- | --- |
| 设计公式 | `control/controller_tuning.py` | `design_pi(plant, crossover_hz, zero_hz, pwm_gain, sensor_gain)` |
| 单点评估 | 同上 | `evaluate_candidate` |
| 3×3 矩阵 | 同上 | `tuning_matrix(plant, base_kp, base_ki, factors=(0.5,1,2))` |
| 候选筛选 | 同上 | `select_candidates` |
| 实验 | `experiments/controller_tuning.py` | `run_controller_tuning_experiment` |
| 稳定性 | `analysis/stability_analysis.py` | `stability_report`、`judge_stability_limits` |

## 3. 设计公式

```text
Kp = 1 / (|Gp(jωc)|·Gpwm·H·sqrt(1+(fz/fc)²))
Ki = 2π·fz·Kp
```

默认 `fc = 600 Hz`、`fz = 80 Hz`，`Gpwm = 0.6463`（由工作点计算，不取 1）。
设计结果写入 `configs/controller_config.yaml` 的 `design` 与 `controller` 小节；
实际配置保留 `Kp = 0.0585`、`Ki = 117.66`（设计基准，未按矩阵最优替换）。

## 4. 3×3 矩阵结果（线性化平均模型）

来源：`results/stage7/experiments/controller_tuning_matrix.csv`。

| Kp 系数 | Ki 系数 | 相位裕度 | 闭环带宽 | 分类 | 评分 |
| --- | --- | --- | --- | --- | --- |
| 0.5 | 2.0 | 100.76° | 258.0 Hz | stable | 2.99 |
| 0.5 | 1.0 | 101.98° | 125.9 Hz | stable | 5.98 |
| 1.0 | 1.0 | 63.49° | 113.9 Hz | stable | 6.64 |
| 1.0 | 2.0 | 54.79° | 232.3 Hz | stable | 8.49 |
| 0.5 | 0.5 | 102.59° | 62.3 Hz | stable | 12.01 |
| 1.0 | 0.5 | 67.56° | 56.5 Hz | stable | 13.32 |
| 2.0 | 2.0 | 32.08° | 214.0 Hz | stable | 31.82 |
| 2.0 | 1.0 | 35.12° | 105.1 Hz | stable | 32.70 |
| 2.0 | 0.5 | 36.63° | 52.2 Hz | stable | 39.08 |

矩阵评分只用于排序，不是“最优控制器”的证明；评分权重包含裕度、超调、调节时间与 IAE。

## 5. 真实 SPICE 复核

来源：`results/stage7/experiments/controller_tuning.json`（负载阶跃 1 A → 2 A，E 变体）。

| 参数组 | Kp | Ki | 负载阶跃最大偏差 | 启动超调 | run_id |
| --- | --- | --- | --- | --- | --- |
| selected（实际配置） | 0.0585 | 117.66 | 0.5493 V | 7.979 % | `20261125_154856_cbfae974` |
| aggressive（2×Kp、2×Ki） | 0.117 | 235.32 | 0.4799 V | 7.642 % | `20261125_154946_7cdd1947` |

结论必须如实陈述：

1. 线性化模型认为默认参数相位裕度 63.49°，矩阵最优为 0.5×Kp/2×Ki（PM 100.76°）。
2. 真实 SPICE 中，2×/2× 的负载阶跃偏差更小（0.4799 V vs 0.5493 V），
   说明线性化评分不能完全预测大信号行为。
3. 本阶段**没有**因为“激进参数在 SPICE 更好”就替换默认配置；默认配置的
   启动超调更低、裕度更保守，替换需要更多工况验证。
4. 两种参数都未达到 0.30 V 的负载阶跃限值，这是真实 FAIL。

## 6. 图表

- `results/stage7/figures/tuning_matrix.png`：Kp/Ki 系数散点，颜色为相位裕度，标签为评分
- `results/stage7/experiments/controller_tuning_matrix.csv`：完整矩阵
- `results/stage7/experiments/selected_loop_bode.csv`：默认参数 Bode 数据
- `results/stage7/experiments/selected_closed_loop_poles.csv`：闭环极点

## 7. 适用条件

1. 线性化平均模型 + 正弦载波增益；适用于小信号稳定性初筛。
2. 参数矩阵只覆盖 `0.5×～2×`，不能外推更极端取值。
3. SPICE 复核使用与主实验相同的功率级、负载与步长（允许显式记录的回退）。

## 8. 局限性

- 评分函数是启发式权重，不同权重会得到不同“最优”。
- 只做电压模式 PI，没有电流环、没有前馈滤波器设计。
- 未做蒙特卡洛、温度与器件容差分析。
- SPICE 复核只覆盖一个负载阶跃工况。

## 9. 技术面试题

1. 为什么设计 `Kp` 时要除以 `sqrt(1+(fz/fc)²)`？
2. 为什么矩阵最优参数在 SPICE 中反而不一定最好？列出至少三个原因。
3. 相位裕度从 63° 提高到 100°，代价是什么？
4. 如果要求负载阶跃偏差小于 0.3 V，你会先改功率级还是改控制器？为什么？
5. 评分函数加入 IAE 后，为什么慢而稳的参数可能得分更高？
6. 如何设计实验，判断“激进参数更好”是真实结论还是单工况偶然？
