# 07 RLC 串联谐振：三种阻尼与交流峰值

> 真实数据：RLC 瞬态每个工况 40017 点（20 ms，5×10⁻⁷ s 步长），
> AC 801 点（10 Hz–100 kHz，200 点/十倍频）。理论均为 `analytical_theory`。

## 1. 分析目标

- 固定 \(L=10\text{ mH}\)、\(C=1\ \mu\text{F}\)，只改变串联电阻，观察欠阻尼、临界阻尼、过阻尼三种阶跃响应。
- 用真实波形测量过冲、振荡频率、调节时间，并与二阶系统解析式对比。
- 用 AC 扫描找电容电压谐振峰，验证峰值频率与品质因数。

## 2. 理论公式

自然角频率、衰减系数、阻尼比、品质因数、临界电阻：

\[
\omega_0=\frac{1}{\sqrt{LC}}=10000\ \text{rad/s}, \qquad
f_0=\frac{\omega_0}{2\pi}=1591.5494\text{ Hz}
\]

\[
\alpha=\frac{R}{2L}, \qquad
\zeta=\frac{R}{2}\sqrt{\frac{C}{L}}, \qquad
Q=\frac{1}{2\zeta}, \qquad
R_{crit}=2\sqrt{\frac{L}{C}}=200\ \Omega
\]

阻尼振荡频率与阶跃过冲：

\[
f_d=f_0\sqrt{1-\zeta^2}, \qquad
M_p=\exp\left(-\frac{\pi\zeta}{\sqrt{1-\zeta^2}}\right)\times100\%
\]

电容电压传递函数与谐振峰：

\[
H(j\omega)=\frac{1}{1-\omega^2LC+j\omega RC}, \qquad
f_{peak}=f_0\sqrt{1-2\zeta^2}
\]

三个工况的理论值：

| R | ζ | Q | 预期行为 |
| --- | --- | --- | --- |
| 10 Ω | 0.05 | 10 | 强振荡，过冲 85.45% |
| 200 Ω | 1.00 | 0.5 | 临界阻尼，无过冲 |
| 400 Ω | 2.00 | 0.25 | 过阻尼，无过冲 |

## 3. 真实网表

欠阻尼瞬态（`run_20261125_111919_fc084e2d/circuit.cir`）：

```spice
.title Series RLC Transient
Vinput vin 0 DC 0V PULSE(0V 5.0V 0s 1e-06s 1e-06s 0.05s 0.1s)
R1 vin n1 10.0
L1 n1 out 0.01
C1 out 0 1e-06
.options TEMP = 25.0C
.options TNOM = 25.0C
.tran 5e-07s 0.02s 0.0s
.end
```

临界/过阻尼仅把 `R1` 改为 `200.0` / `400.0`。交流网表：

```spice
.title Series RLC AC
Vinput vin 0 DC 0V AC 1.0V SIN(0V 1V 1000Hz 0s 0Hz)
R1 vin n1 10.0
L1 n1 out 0.01
C1 out 0 1e-06
.ac dec 200 10.0Hz 100000.0Hz
.end
```

## 4. 代码路径

| 层 | 文件 | 作用 |
| --- | --- | --- |
| 电路 | `circuits/rlc_circuit.py` | `build_rlc_transient` / `build_rlc_ac` |
| 参数 | `circuits/models.py` | `RLCParameters`、`damping_cases` |
| 执行 | `simulations/runner.py` | 同一执行器处理 TRAN 与 AC |
| 理论 | `analysis/theory.py` | \(\omega_0,\alpha,\zeta,Q,R_{crit},f_d,M_p\) |
| 频响 | `analysis/frequency_response.py` | 内部峰值检测、Bode 数据 |
| 指标 | `scripts/rlc_demo.py` | 过冲、振荡频率、调节时间（±2%） |
| 绘图 | `visualization/plots.py` | `plot_rlc_damping`、`plot_bode` |

## 5. 真实结果

瞬态（20 ms，40017 点）：

| R | 末值 | 过冲（仿真） | 过冲（理论） | 振荡频率（仿真） | \(f_d\)（理论） | 调节时间 |
| --- | --- | --- | --- | --- | --- | --- |
| 10 Ω | 5.000057 V | 85.4443% | 85.4468% | 1591.571 Hz | 1589.559 Hz | 7.602 ms |
| 200 Ω | 5.000000 V | \(1.8\times10^{-14}\)% | 0% | 无 | — | 0.584 ms |
| 400 Ω | 5.000000 V | \(1.8\times10^{-14}\)% | 0% | 无 | — | 1.489 ms |

欠阻尼峰值 9.272322 V，出现在 0.315001 ms；临界阻尼无过冲且最快进入 ±2% 带；
过阻尼更慢。这与二阶系统理论排序一致。

交流（801 点）：

| 指标 | 仿真 | 理论 | 偏差 |
| --- | --- | --- | --- |
| 电容电压峰值 | 10.006906 V | 10.012523 V（精确峰） | -0.056% |
| 峰值频率 | 1584.893 Hz | 1587.566 Hz | -0.168% |
| 电感电流峰值 | 0.099651 A | 0.1 A | -0.349% |

峰值频率落在扫频网格 1584.893 Hz 上，说明误差主要来自频率分辨率（200 点/十倍频）。

## 6. 理论与仿真对比及误差来源

1. **有限上升时间**：脉冲源 1 µs 上升沿使实际激励不是理想阶跃，过冲略低。
2. **频率网格**：AC 峰值只能落在离散频点上，1584.893 Hz 与 1587.566 Hz 相差一个网格间隔。
3. **峰值幅值定义**：脚本用 \(Q=10\) 作理论近似，而精确峰值为
   \(1/(2\zeta\sqrt{1-\zeta^2})=10.0125\)，两者差 0.125%。
4. **振荡频率估计**：用过零点计数与首末过零时间估算，受采样步长与最后一个过零点影响；
   仿真 1591.571 Hz 与理论 \(f_d=1589.559\) Hz 相差 0.13%，小于一个频率分辨率量级。
5. **调节时间**：±2% 带定义对噪声敏感；临界阻尼 0.584 ms、过阻尼 1.489 ms 与极点实部
   \(-2679.5\ \text{s}^{-1}\) 的 \(4/\alpha\) 估算一致。

## 7. 面试题（5 道）

1. 临界阻尼电阻为什么是 \(2\sqrt{L/C}\)？
   答：令 \(\zeta=1\)，即 \(R=2\sqrt{L/C}\)；此时特征方程有重根，响应无振荡且最快单调收敛。
2. 欠阻尼过冲公式的适用条件是什么？
   答：仅适用于标准二阶低通/阶跃响应且 \(\zeta<1\)；本电路电容电压在阶跃下符合该模型。
3. 为什么仿真峰值频率略低于 \(f_0\)？
   答：电容电压谐振峰在 \(f_0\sqrt{1-2\zeta^2}\)，且离散扫频进一步量化到网格点。
4. 为什么过阻尼的调节时间反而比临界阻尼长？
   答：过阻尼的慢极点更靠近虚轴（\(s=-2679.5\ \text{s}^{-1}\)），包络衰减更慢。
5. 如何判断“无过冲”不是绘图漏看？
   答：用数值全局最大值与末值比较，并断言差值在 \(10^{-6}\) V 内；同时检查峰值是否在边界。

## 8. 复现命令

```powershell
conda run -n kaifa_power python -m scripts.rlc_demo
conda run -n kaifa_power python -m pytest tests/test_rlc_circuit.py -v
```
