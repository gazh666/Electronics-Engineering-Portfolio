# 29 FFT 与谐波分析

本文解释时域与频域、傅里叶变换、FFT、采样定理、奈奎斯特频率、频率分辨率、
窗函数、谱泄漏、混叠、非均匀采样、重采样、幅值谱、PSD、谐波与 dBV，
并结合真实 Buck 频谱数据说明为什么电源波形 FFT **不等于** EMC 认证。

代码位置：`analysis/spectrum_analysis.py`（`choose_sample_rate`、
`resample_uniform`、`analyze_spectrum`、`ResampleInfo`、`SpectrumResult`）、
`analysis/harmonic_analysis.py`（`analyze_harmonics`、
`total_harmonic_distortion`）、`analysis/performance_analyzer.py`。
算法验证测试：`tests/test_spectrum_analysis.py`。

真实数据：`results/performance/run_20261125_143528_3011f8e8/`
（`spectrum.csv`、`spectrum_metadata.json`、`harmonics.csv`），
Model E，5 ms 瞬态，原始 SPICE 数据点 **221 247**。
A/E 对照来自 `scripts/spectrum_demo.py` 的
`run_20261125_143430_3fe93959`（A）与 `run_20261125_143434_0180ce6a`（E）。

## 1. 时域与频域

时域给出 $v(t)$：纹波、边沿、过冲都直接可见。频域给出各频率成分的幅值，
便于定位开关频率、谐波、振铃频率和干扰源。两者是同一信号的不同表示，
不是两套独立数据；本项目所有频谱都由真实时域波形 FFT 得到。

## 2. 傅里叶变换与 FFT

连续傅里叶变换：

$$
V(f)=\int_{-\infty}^{\infty}v(t)e^{-j2\pi ft}\,dt
$$

有限长离散序列的 DFT：

$$
X[k]=\sum_{n=0}^{N-1}x[n]e^{-j2\pi kn/N},\qquad k=0,\dots,N-1
$$

FFT 只是 DFT 的快速算法，不改变数学定义。本项目用 `numpy.fft.rfft`
（实信号单边谱），再用窗函数相干增益归一化。

## 3. 采样定理与奈奎斯特频率

采样率 $f_s$ 必须大于信号最高频率的两倍：

$$
f_s>2f_{max},\qquad f_{Nyq}=\frac{f_s}{2}
$$

本项目按每周期固定点数选择采样率：

$$
f_s=N_{cycle}\cdot f_{sw}
$$

`choose_sample_rate` 中 `samples_per_cycle=200`、`maximum_samples=10⁶`，
基线得到 $f_s=20$ MHz、$f_{Nyq}=10$ MHz。

## 4. 频率分辨率

$$
\Delta f=\frac{f_s}{N}=\frac{1}{T}
$$

其中 $T$ 是观测时长。**提高采样率不会提高频率分辨率**，只有延长观测时间才行。
基线：$f_s=20$ MHz、$N=67\,679$、$\Delta f=295.513$ Hz、完整周期 338。

## 5. 窗函数与谱泄漏

有限长截断相当于乘矩形窗，频谱会与窗的频谱卷积，产生泄漏。本项目默认 Hann 窗：

$$
w[n]=0.5-0.5\cos\left(\frac{2\pi n}{N-1}\right)
$$

加窗后必须做相干增益补偿，否则幅值被系统性压低：

$$
A_k=\frac{2|X_k|}{\sum_n w[n]}
$$

矩形窗（`boxcar`）只用于 Parseval 对照，不用于正式幅值报告。Hann 窗主瓣更宽
（约 4 个 bin），频率定位略差，但泄漏显著更小，适合开关谐波这种非整数 bin 场景。

实测基波检出频率 99 883.27 Hz，与理想 100 kHz 相差 −116.73 Hz，小于一个
$\Delta f$（295.513 Hz），这正是有限观测与非整数周期造成的频点离散化。

## 6. 混叠

若信号含有高于 $f_{Nyq}$ 的成分，会被折叠到低频：

$$
f_{alias}=|f_{signal}-k f_s|
$$

本项目用“可信上限”限制这种风险：

$$
f_{trusted}=\min\left(f_{Nyq},\ \frac{0.5}{h_{max}}\right)
$$

$h_{max}$ 是原始 SPICE 数据的最大采样间隔。重采样是线性插值，**不能创造原始
数据中不存在的带宽**。超过 $f_{trusted}$ 的谐波一律标记 `NOT_RESOLVED`。
基线 $h_{max}$ 足够小，$f_{trusted}=10$ MHz。

## 7. 非均匀采样与重采样

SPICE 瞬态输出是非均匀时间步：开关边沿附近步长小，稳态段步长大。FFT 要求
等间隔采样，因此必须先重采样。`resample_uniform` 在稳态窗口内做线性插值，
并记录：

- `original_points` / `resampled_points`
- `sample_rate_hz` / `nyquist_hz`
- `frequency_resolution_hz`
- `median_step_s` / `max_step_s`
- `trusted_max_hz`
- `window_start_s` / `window_end_s`
- `complete_cycles`
- `interpolation = "linear"`

基线：原始 221 247 点 → 重采样 67 679 点，$f_s=20$ MHz，窗口覆盖 338 个完整周期。

## 8. 幅值谱与 PSD

幅值谱（峰值）：

$$
A^{peak}_k=\frac{2|X_k|}{\sum_n w[n]}
$$

单边 RMS 幅值 $A^{rms}_k=A^{peak}_k/\sqrt{2}$（DC 与 Nyquist 点除外）。
本项目用 `scipy.signal.periodogram(..., scaling="density")` 计算 PSD，单位 V²/Hz：

$$
S_{vv}(f)=\frac{|X(f)|^2}{f_s\sum_n w^2[n]}
$$

PSD 适合比较不同分辨率下的噪声底，幅值谱适合读谐波大小，两者在
`spectrum.csv` 中同时保存（`amplitude_peak_v`、`amplitude_rms_v`、
`amplitude_dbv`、`psd_v2_per_hz`）。

## 9. dBV

$$
A_{dBV}=20\log_{10}\left(\frac{A^{rms}}{1\ \mathrm{V}}\right)
$$

基线前十阶谐波实测（`harmonics.csv`）：

| 阶次 | 期望频率 | 检出频率 | 峰值幅值 | RMS 幅值 | dBV | 状态 |
| ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 100 kHz | 99 883.27 Hz | 7.811 mV | 5.523 mV | −45.16 | AVAILABLE |
| 2 | 200 kHz | 200 062.06 Hz | 0.983 mV | 0.695 mV | −63.16 | AVAILABLE |
| 3 | 300 kHz | 299 945.33 Hz | 0.621 mV | 0.439 mV | −67.14 | AVAILABLE |
| 4 | 400 kHz | 400 124.12 Hz | 0.382 mV | 0.270 mV | −71.37 | AVAILABLE |
| 5 | 500 kHz | 500 007.39 Hz | 0.086 mV | 0.061 mV | −84.28 | AVAILABLE |
| 6 | 600 kHz | 599 890.66 Hz | 0.201 mV | 0.142 mV | −76.93 | AVAILABLE |
| 7 | 700 kHz | 700 069.45 Hz | 0.037 mV | 0.027 mV | −91.53 | AVAILABLE |
| 8 | 800 kHz | 799 952.72 Hz | 0.107 mV | 0.075 mV | −82.46 | AVAILABLE |
| 9 | 900 kHz | 900 131.50 Hz | 0.059 mV | 0.042 mV | −87.57 | AVAILABLE |
| 10 | 1 MHz | 1 000 014.78 Hz | 0.041 mV | 0.029 mV | −90.69 | AVAILABLE |

总谐波失真：

$$
THD=\frac{\sqrt{\sum_{k\ge2}A_k^2}}{A_1}\times100\%=16.0156\%
$$

前十阶全部 `AVAILABLE`。频谱可信上限 10 MHz，远高于第 10 阶的 1 MHz；
本阶段只提取前 10 阶，因此“可可靠解析的最高阶次”是**分析配置的 10 阶**，
不是带宽极限（带宽理论上允许到 100 阶）。

## 10. FFT 算法验证（已知信号）

`tests/test_spectrum_analysis.py::test_task_19_known_signal_fft_validation`
用解析已知信号 5 V + 1 kHz×0.02 V + 3 kHz×0.005 V 验证 FFT 链路：

| 成分 | 设定值 | FFT 恢复值 | 相对误差 |
| --- | ---: | ---: | ---: |
| DC | 5 V | 5.000000219 V | 4.4×10⁻⁸ % |
| 1 kHz | 0.02 V | 0.019998710 V | −0.00645 % |
| 3 kHz | 0.005 V | 0.004997098 V | −0.058 % |

Parseval 校验（boxcar 窗，时域方差 vs 频域功率和）相对误差 **5.10×10⁻¹⁶**。
非整数周期（103 个周期）时 1 kHz 幅值恢复为 0.01999871 V，说明 Hann 窗
相干增益补偿在非整数 bin 下仍然有效。

真实 Buck 波形上，FFT 峰值幅值与正弦最小二乘拟合幅值存在差异：

- 平均相对误差 **6.0146 %**
- 最大相对误差 **14.0152 %**
- 基波误差 **9.5960 %**

原因是非整数 bin、Hann 主瓣宽度与相邻谐波泄漏；因此报告同时给出
`amplitude_peak` 与 `sine_fit_amplitude` 两列，不把 FFT 峰值当作唯一真值。

## 11. 为什么电源 FFT 不等于 EMC 认证

电源波形 FFT 与传导/辐射发射测试的差别：

| 项目 | 本项目 FFT | EMC 认证测试 |
| --- | --- | --- |
| 测量对象 | 电路内部节点电压 | LISN 上的传导电压 / 天线接收场强 |
| 频段与检波 | 任意频段，峰值谱 | CISPR 频段，准峰值/平均值检波 |
| 带宽 | 由采样率与窗决定 | 接收机分辨率带宽（如 9 kHz） |
| 阻抗与布置 | 无 | 50 Ω LISN、接地平板、线缆布置 |
| 探头/天线 | 无 | 电压探头、电流探头、天线、前置放大器 |
| 环境 | 无数值环境噪声 | 屏蔽室/开阔场，本底噪声受控 |
| 结论 | 机理与趋势 | 是否满足限值线 |

所以本项目只能说“某阶谐波在仿真节点上有多大”，不能说“通过/不通过 EMC”。
器件模型还缺少反向恢复、封装寄生与 PCB 参数，这一限制在
`docs/33_stage5_validation.md` 中单独列出。

## 12. 面试题

1. 为什么不能直接对非均匀 SPICE 数据做 FFT？
   FFT 要求等间隔采样；直接使用会产生频率搬移与幅值误差。
2. 频率分辨率由什么决定？提高采样率能提高分辨率吗？
   $\Delta f=1/T$，由观测时长决定；提高采样率只提高奈奎斯特频率。
3. 为什么可信上限还要受原始最大步长限制？
   重采样是插值，无法恢复原始数据中不存在的带宽。
4. Hann 窗的代价是什么？
   主瓣变宽、频率定位变差，但泄漏显著减小，适合非整数 bin 谐波。
5. 混叠如何产生？怎样避免？
   高于 $f_{Nyq}$ 的成分折叠到低频；提高采样率或前置抗混叠滤波。
6. 幅值谱和 PSD 的区别？
   幅值谱读各频率成分大小；PSD 归一化到每赫兹功率，便于比较噪声底。
7. 为什么 FFT 峰值与正弦拟合幅值不一致？
   非整数 bin、窗主瓣宽度与邻近谐波泄漏都会使峰值偏移；两者应交叉验证。
8. 为什么 THD 只统计 `AVAILABLE` 的谐波？
   未解析阶次超出可信频段，计入会把插值噪声当成信号。
9. 电源 FFT 能替代 EMC 认证吗？
   不能。缺少 LISN、天线、检波方式、布置与环境控制，只能用于机理分析。
