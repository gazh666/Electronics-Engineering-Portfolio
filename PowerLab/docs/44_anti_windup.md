# 44 抗积分饱和（Anti-Windup）设计

## 1. 问题定义

当负载突变或启动时，PI 输出 `d_raw` 超过 `d_max = 0.90` 或低于 `d_min = 0.02`，
执行器已经饱和，但积分器仍按误差继续累加，形成“积分储能”。参考回到可调范围后，
需要很长时间才能把积分器拉回，表现为大超调或长时间单向饱和。

第七阶段实现三种策略，全部在 `control/anti_windup.py`：

| 策略 | 名称 | 行为 |
| --- | --- | --- |
| `none` | 不处理 | 积分器无条件累加，仅供对照 |
| `conditional` | 条件积分 | 饱和且误差继续推向饱和方向时，停止积分 |
| `back_calculation` | 反算 | 把 `(d_limited − d_raw)` 经 `Kaw` 反馈到积分器 |

## 2. 公式

```text
raw      = ff + kp·e + xI
limited  = clamp(raw, dmin, dmax)

none:
    ΔxI = ki·e·Δt

conditional:
    w   = 0   if (raw ≥ dmax and e > 0) or (raw ≤ dmin and e < 0)
    w   = 1   otherwise
    ΔxI = ki·e·w·Δt

back_calculation:
    correction = Kaw·(limited − raw)
    ΔxI = (ki·e + correction)·Δt
```

默认 `Kaw = 2000`（`configs/controller_config.yaml` 的 `tracking_gain`）。
`integral_increment` 返回 `(增量, 修正量)`，修正量写入诊断，便于追溯。

## 3. 源码路径与接口

- `control/anti_windup.py`：`clamp_duty`、`saturation_direction`、
  `conditional_integral_weight`、`back_calculation_correction`、`integral_increment`
- `control/pi_controller.py::PIController.update`：在限幅之后调用抗饱和
- `control/spice_controller.py::add_behavioral_pi_controller`：把同一律写成行为源；
  `conditional` 用 `max(V(err),0)` / `min(V(err),0)` 实现
- `control/models.py::ControllerDiagnostics`：统计饱和次数、最大积分状态、最近修正量

## 4. 实际实验结果

### 4.1 离散演示（参考 10 ms 时从 5 V 降到 4.2 V）

来源：`results/stage7/demos/pi_controller_demo.json`，被控对象为简单平均 LC 模型，
`duty_max = 0.40` 以强制饱和。

| 策略 | 终值 | 最大积分状态 | 饱和时间比例 | 峰值 Vout |
| --- | --- | --- | --- | --- |
| none | 4.2012 V | 0.2623 | 61.41 % | 7.694 V |
| conditional | 4.2000 V | 0.0000 | 43.27 % | 7.492 V |
| back_calculation | 4.2000 V | 0.0000 | 45.92 % | 7.474 V |

三种方法都能把终值拉到 4.2 V，但 `none` 的积分储能为 0.26，是另外两种的
“零”之外的唯一非零值；峰值也最高。

### 4.2 开关级验证（0.5 A → 2 A）

来源：`results/stage7/experiments/closed_loop_validation.json` 的
`anti_windup_comparison` 小节。两种策略均真实运行：

| 策略 | 饱和比例 | 最大偏差 | 严格恢复时间 | run_id |
| --- | --- | --- | --- | --- |
| none | 0.02368 | 0.8395 V | 7.645 ms | `20261125_155146_ec81ab05` |
| back_calculation | 0.02211 | 0.8412 V | 7.645 ms | `20261125_155156_f65016d5` |

饱和比例由 `duty_raw` 与 `duty_limited` 逐点比较得到。本次工况下两种策略的
最大偏差与恢复时间几乎相同，`back_calculation` 甚至略差 0.0017 V；结论是
**该工况不足以体现抗饱和收益**，而不是“抗饱和有效/无效”的普遍证明。

## 5. 图表

- `results/stage7/demos/pi_controller_demo.csv`：三种策略的 time / vref / vout / duty / integral / saturated
- `results/stage7/demos/pi_controller_demo.json`：汇总指标
- `results/stage7/experiments/closed_loop_validation.json`：开关级抗饱和对比

## 6. 适用条件

1. 执行器存在硬限幅（占空比、电流、电压）。
2. 参考阶跃或大负载扰动导致长时间饱和。
3. `back_calculation` 需要合理选择 `Kaw`；过大引入高频抖动，过小退化为 `none`。

## 7. 局限性

- 条件积分在饱和边界附近可能抖动；本阶段未做滞环。
- 反算增益 `Kaw = 2000` 是经验值，没有做频域稳定性证明。
- 诊断只统计采样点，不区分饱和持续时间。
- SPICE 行为源没有离散采样，抗饱和效果与数字实现不完全一致。

## 8. 技术面试题

1. 什么是积分饱和？为什么单纯增大积分限幅不能根治？
2. 条件积分与反算法的本质区别是什么？分别适合什么执行器？
3. 反算增益 `Kaw` 过大会发生什么？如何从波形上识别？
4. 为什么本阶段 SPICE 中两种策略的饱和比例只差 0.0016？这说明工况有什么特点？
5. 如果占空比上限从 0.90 降到 0.50，抗饱和的重要性如何变化？
6. 如何在不断言“通过”的前提下，证明抗饱和确实改善了恢复时间？
