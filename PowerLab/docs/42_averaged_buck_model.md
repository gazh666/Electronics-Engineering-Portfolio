# 42 平均 Buck 模型与状态空间实现

## 1. 目的与边界

本文件说明第七阶段用于**控制器设计、开环占空比校准和线性化环路分析**的平均 Buck 模型。
它不是开关级仿真：输出曲线中没有开关纹波，也不包含 PWM 采样效应，禁止把本模型的波形当作真实开关波形。

- 开关级真实波形：`circuits/closed_loop_buck.py` + `simulations/closed_loop_runner.py`
- 平均模型：`control/averaged_buck.py` + `simulations/averaged_model_runner.py`

## 2. 源码路径与真实接口

| 内容 | 路径 | 真实类/函数 |
| --- | --- | --- |
| 平均模型参数 | `control/averaged_buck.py` | `AveragedBuckParameters` |
| 解析工作点 | 同上 | `operating_point(duty, parameters, nonideal=False)` |
| 状态导数 | 同上 | `buck_derivatives`、`nonideal_derivatives` |
| 小信号线性化 | 同上 | `linearize(parameters, duty)` |
| 连续导通判定 | 同上 | `ccm_check(il_mean, vout, duty, parameters)` |
| 参数提取 | `simulations/averaged_model_runner.py` | `averaged_parameters_from_config`、`estimate_diode_forward_v`、`estimate_mosfet_rds_on` |
| 时域积分 | 同上 | `run_averaged_closed_loop(config, mode, sample_dt_s, max_step_s)` |
| 指标 | 同上 | `averaged_metrics` |

`AveragedBuckParameters.to_dict()` 固定写入 `"model_source": "averaged_model"`；
`ClosedLoopRun`/averaged 运行元数据中另有 `not_a_switching_waveform=True`。

## 3. 数学模型

### 3.1 状态与参数

状态向量取 `x = [iL, vC, xI]`，其中 `xI` 是控制器积分状态。

物理参数：`Vin`、`L`、`C`、`R_load`、`r_DCR`、`r_ESR`、`R_ds(on)`、`V_F`，开关频率 `fs`。
第七阶段默认值：12 V / 47 µH / 100 µF / 2.5 Ω / 0.05 Ω / 0.03 Ω / 100 kHz。

### 3.2 理想平均方程

导通与关断区间按占空比 `D` 加权：

```text
L diL/dt = D·Vin − vC − iL·(D·Rds + rDCR) − (1−D)·VF
C dvC/dt = iL − vC/R_load
```

其中二极管压降按 `VF ≈ n·Vt·ln(iL/IS) + iL·RS` 估计，MOSFET 导通电阻由 Level-1 参数
`KP`、`W/L`、`VGS` 估计（`estimate_mosfet_rds_on`）。ESR 通过

```text
vout = (vC + rESR·iL) / (1 + rESR/R_load)
```

映射到端电压，因此平均模型也包含 ESR 造成的直流偏移与瞬时压降。

### 3.3 解析工作点

令导数为零，得到

```text
D·Vin − VF(1−D)
iL = ────────────────────────────────
      R_load·[1 + (D·Rds + rDCR)/R_load]
```

`operating_point(..., nonideal=False)` 退化为 `Vout = D·Vin`、`iL = D·Vin/R_load`，
用于单元测试与公式核对；非理想版本用于开环占空比校准。

实测（第七阶段默认配置，`results/stage7/demos/averaged_buck_demo.json`）：
解出 `D ≈ 0.4448` 才得到 5 V，写回 `configs/closed_loop_config.yaml` 的
`open_loop_duty_cycle`。

### 3.4 sine 载波的有效占空比映射

SPICE 载波为正弦，比较器阈值 `d` 与实际占空比 `D` 不是线性关系：

```text
D = 0.5 + asin(2d − 1) / π
d = 0.5·[1 − sin(π·(0.5 − D))]
```

平均模型在控制器输出 `d` 后应用上式，保证与 SPICE 的稳态占空比一致。
小信号增益

```text
∂D/∂d = (2/π) / sqrt(1 − (2d − 1)²)
```

在 `d = 0.4137` 时实测为 `0.6463`（`results/stage7/demos/loop_analysis_demo.json`）。

### 3.5 数值积分

`run_averaged_closed_loop` 用 `scipy.integrate.solve_ivp(RK45)`，采样间隔 1 µs，
最大步长 2 µs，返回 12 ms / 12001 点。积分状态在每步通过
`integral_increment(..., dt_s=1.0)[0]` 得到导数，再由 RK45 统一积分。

## 4. 实际实验结果

来源：`results/stage7/demos/averaged_buck_demo.json`（真实运行，非示意）。

| 指标 | 闭环（平均模型） | 开环（平均模型） |
| --- | --- | --- |
| `run_id` | `20261125_152741_a3c73b4f` | `20261125_152741_*`（同批） |
| 稳态均值 Vout | 4.9996 V | 4.906 V 左右 |
| 峰值电感电流 | 2.124 A | 7.1 A 左右 |
| 有效占空比 | 0.44478 | 0.4448（固定） |
| 占空比饱和比例 | 1.99 % | — |
| 数据来源 | `averaged_model` | `averaged_model` |

闭环平均模型峰值电流明显低于开环，是因为闭环在启动时限制占空比增长；该结论只说明
平均模型下的控制行为，不能替代开关级峰值电流结论。

## 5. 图表

- `results/stage7/demos/averaged_closed_loop.csv`：闭环时间序列（time、vout、iL、duty）
- `results/stage7/demos/averaged_open_loop.csv`：开环时间序列
- `results/stage7/demos/averaged_buck_demo.json`：指标与完整参数快照

## 6. 适用条件

1. 开关频率远高于环路带宽（默认 100 kHz vs 约 57 Hz～2.5 kHz 穿越）。
2. 电感电流连续（`ccm_fraction` 接近 1）；DCM 下平均方程不成立。
3. 用于控制器设计、稳态占空比校准、线性化环路分析。
4. 参数为教学级估计，不能用于器件选型或热设计结论。

## 7. 局限性

- 无开关纹波、无 PWM 边沿、无采样保持与数字延迟。
- 二极管压降与 `Rds(on)` 是估计值，不是器件数据手册。
- 负载阶跃的严格恢复时间必须由开关级 SPICE 波形计算，不能引用平均模型。
- 平均模型开环使用固定占空比，不代表任何实时搜索或闭环行为。

## 8. 技术面试题

1. 为什么平均模型可以直接用占空比加权电感电压，而开关级模型必须逐周期开关？
2. 平均模型在 DCM 下为什么失效？如何判断当前工作点是否 CCM？
3. 写出含 ESR 的输出电压表达式，并解释为什么 `vout ≠ vC`。
4. 正弦载波的占空比映射为什么是非线性的？它与三角载波相比对环路增益有什么影响？
5. 为什么开环占空比要用平均模型校准，而不能直接用 `Vout/Vin`？
6. 如果用平均模型算出负载阶跃恢复时间，会遗漏哪些真实效应？
7. RK45 的采样间隔 1 µs 与开关周期 10 µs 之间是什么关系？会不会掩盖开关纹波？
