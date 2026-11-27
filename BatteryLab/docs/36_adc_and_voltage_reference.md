# 36 ADC 与电压基准

## 1. 电路拓扑

```text
模拟输入 ──采样保持── 量化器 ── 编码 ── 数字码
                │
             Vref 3.3 V
```

教学 12 位 SAR 行为模型，中点重构：`code = floor(Vin/LSB)`，`Vdec = (code+0.5)*LSB`。

## 2. 专业原理

- 分辨率是“能分多少份”，精度是“读数离真值多远”。
- 参考电压误差、输入失调、增益误差、噪声、INL 都会进入总误差。
- 量化误差在理想中点重构下不超过 ±0.5 LSB。
- 采样率低于 2 倍信号频率时会发生混叠，混叠后的低频成分无法靠平均消除。

## 3. 公式推导

```text
LSB = Vref/2^N
code = min(max(floor(Vin/LSB),0),2^N−1)
Vdec = (code+0.5)*LSB
eq = Vdec − Vin
```

非理想编码：

```text
Vin' = Vin*(1+εg) + Vos + INL + noise
code = floor(Vin'/LSB_actual)
Vdec = (code+0.5)*LSB_nominal
```

## 4. 变量及单位

| 量 | 数值 | 单位 |
| --- | --- | --- |
| Vref | 3.3 | V |
| N | 12 | bit |
| LSB | 0.805664 | mV |
| 最大量化误差 | 0.402832 | mV |
| 参考偏差 | 0.5 | mV（教学） |
| 输入失调 | 0.5 | mV（教学） |
| 增益误差 | 0.1% | — |
| 噪声 RMS | 0.2 | mV（教学） |
| INL | 0.5 | LSB（教学） |

## 5. 实际器件参数来源

- 教学 ADC 行为模型，**不是 BQ76922 内部 16 位 ADC**。
- BQ76922 单体精度 ±5 mV（25 ℃），来自 Datasheet p.7，不是 3.3/4096。
- 3.3 V 参考为理想值加教学偏差。

## 6. 实际核心源码

- `sensing/adc.py`
- `scripts/adc_demo.py`

## 7. 函数名称及行号

| 名称 | 位置 | 作用 |
| --- | --- | --- |
| `ADCConfig` | `sensing/adc.py:27` | 参考/位数/输入下限 |
| `adc_convert` | `sensing/adc.py:80` | 理想编码/解码 |
| `adc_convert_real` | `sensing/adc.py:150` | 非理想编码 |
| `quantization_staircase` | `sensing/adc.py:189` | 量化阶梯 |
| `check_monotonic` | `sensing/adc.py:113` | 单调性 |
| `theoretical_lsb_input_referred` | `sensing/adc.py:212` | 折算到输入端 |
| `compare_resolutions` | `sensing/adc.py:219` | 位数对照 |

## 8. 核心代码逐行解释

```python
code = math.floor((conditioned - input_min_v) / lsb_actual)
decoded = input_min_v + (code + 0.5) * lsb_nominal
```

- 第 1 行用**实际参考**计算码值，模拟真实芯片；
- 第 2 行用**标称参考**解码，模拟软件不知道参考偏差；
- 两者不抵消，因此参考偏差会真实反映为读数误差。

## 9. 实际运行命令

```powershell
conda run -n kaifa_battery python -m scripts.adc_demo
```

## 10. 实际图表及原始结果路径

Run ID：`sensing_20261126_135332_67fb34`（0 次 SPICE，纯数学行为模型）

- `results/sensing/run_sensing_20261126_135332_67fb34/plots/12_adc_quantization_staircase.png`
- `results/sensing/run_sensing_20261126_135332_67fb34/plots/13_adc_quantization_error.png`
- `results/sensing/run_sensing_20261126_135332_67fb34/plots/14_adc_resolution_comparison.png`
- `results/sensing/run_sensing_20261126_135332_67fb34/plots/15_adc_aliasing_samples.png`
- `results/sensing/run_sensing_20261126_135332_67fb34/plots/16_adc_aliasing_dc_offset.png`

实际结果：

| 位数 | LSB | 最大量化误差 |
| --- | --- | --- |
| 10 | 3.223 mV | 1.611 mV |
| 12 | 0.806 mV | 0.403 mV |
| 16 | 0.0504 mV | 0.0252 mV |

- 12 位最大量化误差 = 0.5 LSB，单调性 True。
- 非理想组合最大误差 2.820 mV（参考偏差+失调+增益+噪声+INL）。
- 100 kHz 干扰、1 kHz 采样：混叠到 DC，0° 相位均值 3.7024 V，90° 相位 3.8024 V；4/16 点平均仍分别停在这两个值，**数字平均不能消除**。
- 1.1 kHz 采样：混叠到 100 Hz，峰峰值 0.202 V，平均值随相位变化。

## 11. 常见错误

1. 把 12 位 LSB 当采集精度。
2. 认为参考偏差会被软件校准自动抵消。
3. 用数字平均消除已经混叠到 DC 的干扰。
4. 把 BQ76922 的 ±5 mV 与教学 ADC 的 0.4 mV 量化误差混为一谈。
5. 忽略 INL/DNL，只看理想量化。

## 12. 独立学习练习

1. 计算 2.5 V 输入在 10/12/16 位下的码值与解码值。
2. 构造 1.9 kHz 干扰、1 kHz 采样，求混叠频率。
3. 把参考偏差改为 10 mV，重算满量程误差。

## 13. 面试问题

1. ADC 分辨率与精度有什么区别？
2. 参考电压对转换精度有什么影响？
3. 什么是混叠？如何避免？
4. 为什么平均不能消除混叠到 DC 的干扰？
5. 为什么 BQ76922 的精度规格不能由 3.3 V/4096 推出？
