# 09 半波整流：真实二极管与理想公式对比

> 真实瞬态 5008 点（0.1 s，2×10⁻⁵ s 步长）；理想正弦半波公式为 `analytical_theory`。

## 1. 分析目标

- 用 10 V 峰值、50 Hz 正弦源 + 二极管 + 1 kΩ 负载，观察半波整流波形。
- 用时间加权积分计算平均电压、RMS 电压与负载平均功率。
- 量化“真实二极管压降 + 源内阻”导致的非理想性。

## 2. 理论公式

理想半波整流（无压降、无内阻）：

\[
V_{avg}=\frac{V_p}{\pi}=3.1831\text{ V}, \qquad
V_{rms}=\frac{V_p}{2}=5.0000\text{ V}
\]

\[
P_{avg}=\frac{V_{rms}^2}{R}=\frac{V_p^2}{4R}=0.025\text{ W}
\]

真实电路还需满足：

\[
v_{out}(t)=\max\left(v_{in}(t)-v_D(t),\; -I_S R_{load}\right)
\]

其中 \(v_D\) 包含二极管正向压降与 \(R_S\) 压降，因此输出峰值低于输入峰值；
导通角也小于 \(180^\circ\)。

## 3. 真实网表

`results/basic_circuits/run_20261125_111922_6fad9935/circuit.cir`：

```spice
.title Half Wave Rectifier
Vinput vin 0 DC 0V AC 1V SIN(0V 10.0V 50.0Hz 0s 0Hz)
Rsource vin anode 1.0
D1 anode out DTEST
Rload out 0 1000.0
.model DTEST D (IS=1e-09 N=1.8 RS=0.5)
.options TEMP = 25.0C
.options TNOM = 25.0C
.tran 2e-05s 0.1s 0.0s
.end
```

注意 `Rsource=1 Ω` 是刻意加入的源内阻，使峰值电流不会无限大，也更接近真实信号源。

## 4. 代码路径

| 层 | 文件 | 作用 |
| --- | --- | --- |
| 电路 | `circuits/rectifier.py` | `build_half_wave_rectifier`，复用 `add_diode_model` |
| 参数 | `circuits/models.py` | `RectifierParameters` 校验峰值、频率、负载 |
| 执行 | `simulations/runner.py` | `run_transient` |
| 理论 | `analysis/theory.py` | `half_wave_average_voltage/rms/power` |
| 脚本 | `scripts/rectifier_demo.py` | 梯形积分、导通占比、峰值与误差 |
| 绘图 | `visualization/plots.py` | `plot_rectifier` |

## 5. 真实结果

| 指标 | 仿真值 | 理想值 | 相对误差 |
| --- | --- | --- | --- |
| 平均电压 | 2.831794 V | 3.183099 V | -11.04% |
| RMS 电压 | 4.534981 V | 5.000000 V | -9.30% |
| 平均负载功率 | 0.020566 W | 0.025000 W | -17.74% |
| 输入峰值 | 9.999985 V | 10.0 V | -0.00015% |
| 输出峰值 | 9.244344 V | 10.0 V | -7.56% |
| 输出最小值 | -1.01 µV | 0 V | 反偏漏电 |
| 导通采样占比 | 0.4900 | 0.5 | — |
| 等效导通角 | 176.4° | 180° | — |

输出最小值 -1.01 µV 不是数值错误：反偏时二极管约有 -1 nA 漏电流，
在 1 kΩ 负载上产生约 -1 µV 电压。因此质量检查使用“负压不超过 2 µV”的物理容差，
而不是强行要求严格非负。

## 6. 理论与仿真对比及误差来源

1. **二极管正向压降**：约 0.6–0.8 V，直接削减输出峰值，是平均电压偏低的主因。
2. **串联电阻 \(R_S=0.5\ \Omega\) + 源内阻 \(1\ \Omega\)**：大电流时额外压降，进一步降低峰值。
3. **导通角小于 180°**：输入电压必须超过二极管导通电压才有输出，导致平均/RMS 下降；
   功率与 RMS 平方相关，因此功率误差（-17.7%）大于电压误差。
4. **反偏漏电**：输出出现约 -1 µV，说明真实模型不是理想开关。
5. **数值积分**：使用梯形法对 2×10⁻⁵ s 均匀采样积分；对 50 Hz 信号每周期 1000 点，
   积分误差远小于模型误差。
6. **起始相位**：正弦从 0° 开始，0.1 s 正好 5 个周期，避免截断造成平均偏差。

## 7. 面试题（5 道）

1. 理想半波整流的平均值为什么是 \(V_p/\pi\)？
   答：对半波正弦在整周期积分：\(\frac{1}{2\pi}\int_0^\pi V_p\sin\theta\,d\theta=V_p/\pi\)。
2. RMS 为什么是 \(V_p/2\)？
   答：半波整流后只有半个周期有输出，\(\sqrt{\frac{1}{2\pi}\int_0^\pi V_p^2\sin^2\theta\,d\theta}=V_p/2\)。
3. 为什么功率误差比电压误差更大？
   答：\(P=V_{rms}^2/R\)，电压的相对误差在平方后近似翻倍，且导通角减小进一步降低 RMS。
4. 输出出现微小负值是否说明仿真错误？
   答：不是；反偏漏电流在负载上产生 µV 级负压，是真实模型行为。
5. 如何把半波整流改成全波整流？
   答：使用桥式整流或中心抽头变压器，使两个半周期都向负载供电；
   输出平均值约翻倍，纹波频率翻倍。

## 8. 复现命令

```powershell
conda run -n kaifa_power python -m scripts.rectifier_demo
conda run -n kaifa_power python -m pytest tests/test_rectifier.py -v
```
