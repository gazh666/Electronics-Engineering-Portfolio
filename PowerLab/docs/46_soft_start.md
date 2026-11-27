# 46 软启动设计

## 1. 目标

软启动通过缓慢抬升参考电压，限制启动瞬间的占空比与电感电流，避免输出超调和
输入电流冲击。第七阶段用**同一闭环控制器**只改变 `Vref(t)`，不改变功率级与 PI 参数。

## 2. 源码与配置

| 内容 | 路径 | 真实接口 |
| --- | --- | --- |
| 参考生成 | `control/soft_start.py` | `soft_start_reference`、`soft_start_points`、`ramp_rate_v_per_s` |
| 配置 | `control/models.py` / `configs/controller_config.yaml` | `SoftStartConfig(enabled, duration_s, initial_reference_v)` |
| SPICE 实现 | `control/spice_controller.py` | 行为源 `V(ref)` 使用 PWL 或分段表达式 |
| 实验 | `experiments/soft_start.py` | `run_soft_start_experiment(durations_s)` |
| 指标 | `analysis/startup_analysis.py` | `analyze_startup` |

默认配置：`enabled = true`，`duration_s = 0.002`，`initial_reference_v = 0`。

## 3. 公式

```text
Vref(t) = Vinitial + (Vtarget − Vinitial)·min(t / Tss, 1)
```

- `Tss = 0` 或 `enabled = false` 时，参考在 0.1 µs 内到达目标（作为“无软启动”对照）。
- 上升斜率 `Vtarget / Tss`；默认 5 V / 2 ms = 2500 V/s。

启动指标（`analyze_startup`）：

- 输出延迟：首次达到 `0.1·Vtarget`
- 上升时间：`0.1·Vtarget → 0.9·Vtarget`
- 超调：`100·(Vpeak − Vtarget)/Vtarget`
- 调节时间：周期均值进入 ±2 % 并保持 20 个开关周期
- 峰值 `iL`、峰值 `iin`、占空比饱和时间/比例

## 4. 实际实验结果

来源：`results/stage7/experiments/soft_start.json`（E 变体，50 ns 步长，真实 SPICE）。

| 配置 | Tss | 超调 | 峰值 iL | 峰值 iin | 上升时间 | 判定 | run_id |
| --- | --- | --- | --- | --- | --- | --- | --- |
| no_soft_start | 0 ms | 61.72 % | 9.164 A | 9.232 A | 0.0647 ms | FAIL | `20261125_154805_3bfb5373` |
| soft_start_2ms | 2 ms | 0.458 % | 2.445 A | 3.831 A | 1.775 ms | PASS | `20261125_154811_787c3399` |
| soft_start_5ms | 5 ms | 0.175 % | 2.360 A | 3.783 A | 4.586 ms | PASS | `20261125_154836_9cc198e4` |
| soft_start_10ms | 10 ms | 0.534 % | 2.359 A | 3.640 A | 9.106 ms | PASS | `20261125_154844_383ad677` |

观察：

1. 无软启动时超调 61.7 %、峰值电感电流 9.16 A，均超过本阶段限值（10 %、4 A）。
2. 2 ms 已把超调压到 0.46 %、峰值电流压到 2.45 A；继续加长到 5/10 ms 对峰值电流
   改善很小（2.36 / 2.36 A），只是延长上升时间。
3. 10 ms 的超调（0.534 %）略高于 5 ms（0.175 %），差异来自开关纹波与周期均值判定，
   不能宣称“越长越好”。

## 5. 图表

- `results/stage7/experiments/soft_start.json`：四次运行的全部启动指标与限值判定
- `results/stage7/figures/soft_start_summary.png`：由报告脚本生成的超调/峰值电流图
- 每次运行的 `runs/<run_id>/waveform.csv.gz`：vref/vout/iL/iin 原始波形（按需保存）

## 6. 适用条件

1. 输出电压目标固定、启动时无大负载。
2. 控制器积分器从 0 开始；参考从 0 或已知初值开始。
3. 软启动时间长于输出 LC 的自然上升时间，才能有效限制电流。

## 7. 局限性

- 只限制参考斜率，不直接限制电感电流；重载启动仍可能触发限流。
- 没有“软启动结束后平滑切换”的额外逻辑，依赖 PI 自身跟踪。
- 无软启动的 FAIL 是真实结果，未针对该工况放宽限值。
- 10 ms 与 5 ms 的差异在数值波动范围内，不能据此给出最优时长结论。

## 8. 技术面试题

1. 软启动为什么能降低峰值电感电流？限制的是电压还是电流？
2. 为什么 2 ms 之后继续加长软启动，峰值电流几乎不变？
3. 软启动期间积分器在做什么？是否仍会饱和？
4. 如果负载在软启动期间突然加重，会发生什么？
5. 无软启动时 61.7 % 的超调用什么指标定义？为什么不用瞬时峰值？
6. 如何在不修改功率级的前提下，进一步降低启动时的输入电流峰值？
