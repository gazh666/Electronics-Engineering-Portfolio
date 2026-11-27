# 05 RC 低通交流分析与频率响应

> 数据来源：`.ac` 真实复数解（`spice_simulation`）；理论曲线为 `analytical_theory`。

## 1. 分析目标

- 用 AC 小信号分析得到 RC 低通的幅频、相频特性。
- 从真实离散频点插值估计 -3 dB 截止频率，并与 \(1/(2\pi RC)\) 对比。
- 验证交流结果必须保留复数实部/虚部，禁止提前取绝对值。

## 2. 理论公式

一阶 RC 低通传递函数：

\[
H(j\omega)=\frac{1}{1+j\omega RC}
\]

幅值与相位：

\[
|H|=\frac{1}{\sqrt{1+(\omega RC)^2}}, \qquad
\varphi=-\arctan(\omega RC)
\]

截止频率与 -3 dB 点：

\[
f_c=\frac{1}{2\pi RC}=159.154943\text{ Hz}, \qquad
|H(j2\pi f_c)|=\frac{1}{\sqrt{2}}, \qquad
20\lg|H|=-3.0103\text{ dB}
\]

相位在 \(f_c\) 处为 \(-45^\circ\)。

## 3. 真实网表

`results/basic_circuits/run_20261125_111918_7d32f26f/circuit.cir`：

```spice
.title RC Low Pass Filter
Vinput vin 0 DC 0V AC 1.0V SIN(0V 1V 1000Hz 0s 0Hz)
R1 vin out 1000.0
C1 out 0 1e-06
.options TEMP = 25.0C
.options TNOM = 25.0C
.ac dec 50 1.0Hz 100000.0Hz
.end
```

`AC 1.0V` 是 AC 分析必需的交流激励；`SIN(...)` 只影响瞬态，不参与 AC 小信号求解。

## 4. 代码路径

| 层 | 文件 | 作用 |
| --- | --- | --- |
| 电路 | `circuits/rc_circuit.py` | `build_rc_lowpass`，强制 `ac_magnitude_v > 0` |
| 执行 | `simulations/runner.py` | `run_ac` 拆分 real/imag 列，保留复数语义 |
| 频响 | `analysis/frequency_response.py` | `gain_to_db`、`estimate_cutoff_frequency`、`peak_metrics` |
| 理论 | `analysis/theory.py` | `rc_cutoff_frequency`、`rc_frequency_response` |
| 脚本 | `scripts/rc_ac_demo.py` | 真实 AC 运行、截止频率插值、Bode 图 |

## 5. 真实结果（251 点，1 Hz–100 kHz，50 点/十倍频）

| 指标 | 仿真值 | 理论值 | 误差 |
| --- | --- | --- | --- |
| 截止频率 | 159.1482465 Hz | 159.1549431 Hz | -0.00670 Hz（-0.00421%） |
| 截止点增益 | -3.010495 dB | -3.010300 dB | \(1.95\times10^{-4}\) dB |
| 截止点相位 | -44.998763° | -45.000000° | 0.001237° |
| 全频段最大增益误差 | — | — | \(7.11\times10^{-15}\) dB |
| 全频段最大相位误差 | — | — | \(1.42\times10^{-14}\)° |

低频端 1 Hz：增益 -0.000171 dB，相位 -0.360°；高频端 100 kHz：
增益 -55.964 dB，相位 -89.909°，符合一阶低通每十倍频 -20 dB 的渐近斜率。

截止频率的插值区间为 158.489 Hz（0.70859）到 165.959 Hz（0.69216），
方法为“对 \(\log_{10} f\) 线性插值”，比直接对频率线性插值更符合对数扫频网格。

## 6. 理论与仿真对比及误差来源

- 最大增益/相位误差在 \(10^{-14}\) 量级，说明 AC 求解器与解析式在该理想模型下几乎完全一致。
- 截止频率误差 -0.0042% 并非求解误差，而是**离散频点 + 插值**带来的估计误差：
  真实 -3 dB 点落在两个扫频点之间。
- 若把扫频密度从 50 点/十倍频提高到 200 点/十倍频，插值误差会进一步减小。
- 模型未包含电阻寄生电容、电感 ESL，因此高频段理论仍能贴合；真实器件在高频会偏离。

## 7. 面试题（5 道）

1. AC 分析为什么必须给源加 `AC` 幅值？
   答：AC 分析在工作点附近线性化，需要明确的小信号激励幅值；没有 `AC` 时源在小信号域为 0。
2. 为什么保存 AC 波形时不能只存幅值？
   答：幅值丢失相位信息，无法正确合成时域波形、无法判断相位裕度，也无法做复数运算。
3. -3 dB 截止频率为什么用对数频率插值？
   答：扫频按十倍频均匀分布，\(\log f\) 上线性插值更接近真实响应；直接按 f 插值会有系统偏差。
4. 一阶 RC 的相位在截止频率为什么是 -45°？
   答：此时 \(\omega RC=1\)，\(H=1/(1+j)\)，幅值 \(1/\sqrt2\)，相角 \(-\arctan 1=-45^\circ\)。
5. 这个实验能证明仿真器“完全准确”吗？
   答：只能证明在该理想线性模型和该频段内一致；不能外推到寄生参数、非线性或高频效应。

## 8. 复现命令

```powershell
conda run -n kaifa_power python -m scripts.rc_ac_demo
conda run -n kaifa_power python -m pytest tests/test_frequency_response.py -v
```
