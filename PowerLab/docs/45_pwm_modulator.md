# 45 PWM 调制器与占空比映射

## 1. 为什么需要专门的调制器模块

第七阶段有两类“占空比”：

1. 控制器输出的**指令** `d`（0～1）；
2. 开关管实际执行的**有效占空比** `D`。

正弦载波 + 比较器使二者非线性。若不区分，环路增益、稳态工作点和实验结论都会错。
`control/pwm_modulator.py` 负责映射、载波生成与脉冲统计。

## 2. 源码路径与真实接口

| 内容 | 路径 | 真实函数 |
| --- | --- | --- |
| 正弦载波 | `control/pwm_modulator.py` | `sine_carrier(time_s, frequency_hz)` |
| 锯齿载波（仅分析） | 同上 | `sawtooth_carrier` |
| 有效占空比 | 同上 | `effective_duty_sine(threshold)` |
| 反解阈值 | 同上 | `threshold_from_effective_duty(duty)` |
| 小信号增益 | 同上 | `sine_carrier_gain(duty)` |
| 脉冲统计 | 同上 | `analyze_pwm_pulses(time, pwm, period)` |
| 窗口占空比 | 同上 | `measure_duty_windows(time, pwm, window_s)` |
| SPICE 比较器 | `control/spice_controller.py` | `add_behavioral_pi_controller` 内 `pwm` 行为源 |

## 3. 公式

### 3.1 正弦载波

```text
ramp(t) = 0.5·[1 + sin(2π·fs·t)]
```

### 3.2 平滑比较器

```text
pwm = clamp( (d − ramp)/w + 0.5, 0, 1 ),  w = 0.02
```

`w` 是平滑宽度，避免理想比较器在 SPICE 中产生不连续导数导致收敛失败。
它使边沿有约 `w·T` 的过渡，属于数值建模选择，需在结论中说明。

### 3.3 有效占空比与反解

```text
D(d) = 0.5 + asin(2d − 1)/π
d(D) = 0.5·[1 − sin(π·(0.5 − D))]
```

### 3.4 小信号增益

```text
g(d) = (2/π) / sqrt(1 − (2d − 1)²)
```

在默认工作点 `d = 0.4137` 时 `g = 0.6463`，因此实际环路穿越频率低于按 `g = 1`
设计的 600 Hz。整定实验显式使用 `pwm_gain = carrier_small_signal_gain(D)`。

## 4. 脉冲统计与质量判定

`analyze_pwm_pulses` 按开关周期切窗，统计：

- 每周期脉冲数（缺失 / 多次脉冲）；
- 每周期占空比；
- 有效周期数、均值占空比。

`run_closed_loop` 的元数据写入：

- `pwm_statistics`（含启动段，可能因初始充电出现异常）；
- `pwm_statistics_after_startup`（启动后，验收使用这一组）；
- `quality`（缺脉冲、多脉冲、PWM 有效标志）。

第七阶段验收要求启动后每个周期恰好一个脉冲。启动前 1 ms 单独统计，不作为失败依据。

## 5. 实际实验结果

来源：`results/stage7/demos/loop_analysis_demo.json` 与
`results/stage7/demos/closed_loop_buck_demo.json`。

| 项目 | 数值 |
| --- | --- |
| 开关频率 | 100 kHz |
| 稳态有效占空比 | 0.4448 |
| 控制器输出阈值 `d` | 0.4137 |
| 正弦载波小信号增益 | 0.6463 |
| 启动后缺脉冲周期 | 0 |
| 启动后多脉冲周期 | 0 |

开关级波形的 PWM 高电平为 0～1 的行为源输出，驱动级再映射为 10 V（MOSFET）或
5 V（理想开关）。

## 6. 适用条件

1. 载波频率等于功率级开关频率（配置加载时强校验）。
2. 正弦载波模型；锯齿波只用于平均模型与 PWM 分析，不进入 SPICE。
3. 平滑宽度 `w = 0.02` 适用于本阶段 25 ns / 50 ns 步长。

## 7. 局限性

- 正弦载波不是工业常用的三角/锯齿载波，占空比到电压的映射不同。
- 平滑比较器不是理想比较器，边沿时间与真实栅极驱动不同。
- 脉冲统计基于记录采样点，极窄脉冲可能被漏计。
- 没有死区、最小导通/关断时间建模。

## 8. 技术面试题

1. 为什么正弦载波的有效占空比需要 `asin` 映射，而锯齿载波不需要？
2. 平滑比较器的宽度 `w` 对环路增益和仿真收敛分别有什么影响？
3. 如果 `w` 取 0.001，SPICE 可能出现什么问题？
4. 如何从 `pwm_cycles.csv` 判断某个周期出现了多次脉冲？
5. 为什么启动前 1 ms 的 PWM 异常不能直接算作控制失败？
6. 三角载波与正弦载波在小信号增益上的差异会如何影响相位裕度？
