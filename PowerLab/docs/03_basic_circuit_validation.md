# 03 基础电路验证：电阻分压与 RC 充电

> 本文的理论值用于对照，仿真值全部来自本机 ngspice-34 真实求解。
> 运行时间：2026-11-25；环境见 `docs/01_environment_setup.md`。

## 1. 电阻分压电路

### 1.1 欧姆定律

\[
I = \frac{U}{R}, \qquad U = I R
\]

### 1.2 电阻串联

R1 与 R2 串联，回路总电阻：

\[
R_{total} = R_1 + R_2 = 1000 + 1000 = 2000\ \Omega
\]

回路电流：

\[
I = \frac{V_{in}}{R_1 + R_2} = \frac{12}{2000} = 6\ \text{mA}
\]

### 1.3 分压公式与节点电压

输出节点 `out` 对地的电压等于 R2 上的压降：

\[
V_{out} = V_{in}\frac{R_2}{R_1 + R_2} = 12 \times \frac{1000}{2000} = 6\ \text{V}
\]

### 1.4 直流工作点分析

工作点分析把电容视为开路、电感视为短路，求直流稳态下的所有节点电压与支路电流。
PySpice 调用：`simulator.operating_point()`；网表中的分析指令由 PySpice 在求解时追加。

### 1.5 理论与 SPICE 对照（真实结果）

| 项目 | 理论值 | ngspice 仿真值 | 绝对误差 | 相对误差 |
| --- | --- | --- | --- | --- |
| 输入节点 `vin` | 12.000000 V | 12.000000 V | 0 V | 0 % |
| 输出节点 `out` | 6.000000 V | 6.000000 V | 0 V | 0 % |
| 回路电流 | 6.000000 mA | 由 12 V / 2 kΩ 决定 | — | — |

实际网表（`results/divider_20261125_104442_aa61595c/netlist.cir`）：

```spice
.title Voltage Divider
Vinput vin 0 12.0V
R1 vin out 1000.0Ohm
R2 out 0 1000.0Ohm
```

产物：

- `results/divider_20261125_104442_aa61595c/netlist.cir`
- `results/divider_20261125_104442_aa61595c/result.json`

## 2. RC 充电电路

### 2.1 电容的作用与电流关系

电容的电压不能突变，电流与电压变化率成正比：

\[
i_C(t) = C\frac{dV_C}{dt}
\]

### 2.2 RC 充电过程

输入阶跃为 5 V，R = 1 kΩ，C = 1 μF。回路方程：

\[
V_{in} = R i + V_C, \qquad i = C\frac{dV_C}{dt}
\]

解得：

\[
V_C(t) = V_{in}\left(1 - e^{-t/\tau}\right), \qquad \tau = RC
\]

### 2.3 时间常数

\[
\tau = 1000 \times 1\times10^{-6} = 1\times10^{-3}\ \text{s} = 1\ \text{ms}
\]

### 2.4 为什么 1τ 约等于最终值的 63.2%

\[
1 - e^{-1} = 1 - 0.367879 = 0.632121
\]

因此 1τ 时电容电压约为 5 V × 63.2% = 3.1606 V；2τ 为 86.47%，3τ 为 95.02%，
5τ 为 99.33%。

### 2.5 瞬态仿真设置

| 参数 | 实际值 |
| --- | --- |
| 输入幅值 | 5 V |
| 上升/下降时间 | 1 μs |
| 仿真步长 | 10 μs |
| 仿真总时长 | 6 ms |
| 实际采样点 | 619 |
| 数据时间范围 | 0 – 6 ms |

ngspice 采用自适应时间步，因此采样点不是简单的 6 ms / 10 μs + 1。

### 2.6 理论与 SPICE 对照（真实结果）

| 时刻 | 理论值（理想阶跃） | ngspice 仿真 | 绝对误差 |
| --- | --- | --- | --- |
| 1τ = 1 ms | 3.160603 V | 3.159684 V | 0.919 mV |
| 2τ = 2 ms | 4.323324 V | 4.322991 V | 0.332 mV |
| 3τ = 3 ms | 4.751065 V | 4.750944 V | 0.120 mV |
| 5τ = 5 ms | 4.966310 V | 4.966295 V | 0.0157 mV |
| 6 ms（终点） | 4.987606 V | 4.987601 V | 约 0.0000056 V |

全区间指标：

| 指标 | 实际值 |
| --- | --- |
| 最大绝对误差 | 2.498 mV，出现在 t = 1 μs |
| RMSE | 0.760 mV |
| 最终仿真电压 | 4.987601 V |

误差解释：

- 理论公式假设**理想瞬时阶跃**，实际脉冲源有 1 μs 上升时间；
- 最大误差出现在 t = 1 μs，正是上升沿结束的位置，符合物理差异；
- 随着时间推进，误差迅速衰减到微伏级，说明求解结果与一阶 RC 理论一致；
- 不能用“每个点都必须完全相等”作为验收标准。

实际网表（`results/rc_20261125_104453_606bded9/netlist.cir`）：

```spice
.title RC Charging
Vinput vin 0 DC 0V PULSE(0V 5.0V 0s 1e-06s 1e-06s 0.02s 0.04s)
R1 vin out 1000.0
C1 out 0 1e-06
```

产物：

- `results/rc_20261125_104453_606bded9/rc_transient.csv`（620 行，含表头）
- `results/rc_20261125_104453_606bded9/rc_transient.png`（46,728 字节）
- `results/rc_20261125_104453_606bded9/metrics.json`
- `results/rc_20261125_104453_606bded9/netlist.cir`

CSV 列：`time_s, vin_v, spice_vout_v, ideal_step_theoretical_v`。
图中实线为 ngspice 波形，虚线为理想阶跃理论。

## 3. 与后续 Buck 电路的关系

- Buck 的输出滤波本质上是 LC 网络；电容电压纹波与 `i = C dv/dt` 直接相关。
- 本阶段 RC 实验建立的“时间常数、指数响应、瞬态采样、误差评估”方法，可直接迁移到
  Buck 启动过程与负载瞬态。
- Buck 存在开关非线性、电感电流连续/断续、寄生参数与器件模型，稳态公式无法覆盖，
  必须依赖 SPICE 时域仿真。
- 因此后续阶段的顺序应是：先掌握一阶 RC → 再引入电感与开关 → 再做纹波、效率与
  瞬态指标，而不是直接套用理想 Buck 公式。

## 4. 复现命令

```powershell
conda run -n kaifa_power python -m scripts.voltage_divider_demo
conda run -n kaifa_power python -m scripts.rc_transient_demo
conda run -n kaifa_power python -m pytest tests -v
```

每次执行都会生成新的 `results/` 运行目录，历史结果不会被覆盖。
