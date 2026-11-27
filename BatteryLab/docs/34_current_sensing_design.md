# 34 双向电流采集设计

## 1. 电路拓扑

```text
PACK− ──┬──[Rshunt 10 mΩ]──┬── PACK−
        │                  │
       SRP                SRN
        │                  │
        └── INA240A2 ──────┘
                │
              OUT ──1 kΩ──┬── ADC
                          │
                        0.1 µF
                          │
                         GND
```

分流电阻放在低侧，INA240A2 差分采样，输出以 1.65 V 为零点。

## 2. 专业原理

- 分流电阻把电流转为毫伏电压：`Vshunt = I*Rshunt`。
- 双向电流必须加零点偏置，否则负电流会被单电源输出截断。
- 放大器增益 50 V/V，把 ±25 mV 放大到 ±1.25 V，叠加 1.65 V 零点。
- 输出 RC 抑制 PWM/开关噪声，但会限制电流环带宽。

## 3. 公式推导

```text
Vout = Vref + G*I*Rshunt = 1.65 + 50*0.01*I = 1.65 + 0.5*I
I = (Vout − 1.65)/0.5
Pshunt = I²*Rshunt
I_lsb = LSB/(G*Rshunt) = (3.3/4096)/0.5 = 1.611 mA
```

输出滤波：

```text
fc = 1/(2π*R*C) = 1/(2π*1000*0.1e-6) = 1591.55 Hz
ts(1%) ≈ 4.605*R*C = 460.5 µs
```

## 4. 变量及单位

| 量 | 数值 | 单位 |
| --- | --- | --- |
| Rshunt | 10 | mΩ |
| G | 50 | V/V |
| Vref | 1.65 | V |
| 量程 | ±2.5 | A |
| 分流压降 | ±25 | mV |
| 分流功耗 | 62.5 | mW @2.5 A |
| 输出滤波 | 1 kΩ / 0.1 µF | — |

## 5. 实际器件参数来源

INA240A2，TI SBOS662C（2021-12）：

| 参数 | 数值 | 页码 |
| --- | --- | --- |
| 增益 | 50 V/V | p.5 |
| 共模范围 | −4–80 V | p.5 |
| CMRR | 120 dB min / 132 dB typ | p.5 |
| 输入失调 | ±25 µV max | p.5 |
| 增益误差 | ±0.20% max | p.5 |
| 带宽 | 400 kHz | p.5 |
| 静态电流 | 2.4 mA typ / 2.6 mA max | p.5 |
| 供电 | 2.7–5.5 V | p.5 |

**这些是 Datasheet 规格，不是本人实测。** 分流电阻为教学假设 10 mΩ。

## 6. 实际核心源码

- `circuits/current_sensing.py`
- `circuits/opamp_models.py`
- `sensing/current_decoder.py`
- `scripts/current_sensing_demo.py`

## 7. 函数名称及行号

| 名称 | 位置 | 作用 |
| --- | --- | --- |
| `CurrentSenseConfig` | `circuits/current_sensing.py:27` | 电流采集配置 |
| `build_current_sense_circuit` | `circuits/current_sensing.py:66` | 真实网表 |
| `solve_current` | `circuits/current_sensing.py:100` | 单点工作点 |
| `sweep_current_fast` | `circuits/current_sensing.py:157` | 一次 DC 扫描含饱和 |
| `run_output_filter_ac` | `circuits/current_sensing.py:199` | 输出滤波 AC |
| `run_output_filter_step` | `circuits/current_sensing.py:226` | 输出滤波阶跃 |
| `shunt_selection_table` | `circuits/current_sensing.py:275` | 分流电阻选型 |
| `amplifier_output` | `sensing/current_decoder.py:37` | 电流→电压 |

## 8. 核心代码逐行解释

```python
circuit.R("shunt", "srp", circuit.gnd, config.shunt_ohm)   # 分流电阻
circuit.I("load", circuit.gnd, "srp", float(current_a))    # 正电流注入
add_spec_reference_current_amplifier(...)                   # INA240 行为模型
```

- 电流源方向保证正电流在 SRP 产生正压降；
- 行为模型把输入失调折算到输入端，避免把它误当输出失调；
- `sweep_current_fast` 用一次 DC 扫描得到整条传输曲线与饱和边界，节省真实求解次数。

## 9. 实际运行命令

```powershell
conda run -n kaifa_battery python -m scripts.current_sensing_demo
```

## 10. 实际图表及原始结果路径

Run ID：`sensing_20261126_135555_720959`

- `results/sensing/run_sensing_20261126_135555_720959/plots/09_bidirectional_current_transfer.png`
- `results/sensing/run_sensing_20261126_135555_720959/plots/10_shunt_power.png`
- `results/sensing/run_sensing_20261126_135555_720959/plots/11_current_saturation.png`
- `results/sensing/run_sensing_20261126_135555_720959/plots/12_current_output_filter_bode.png`

实际结果：

| 指标 | 数值 |
| --- | --- |
| 实测跨导 | 0.500000063 V/A |
| 理论跨导 | 0.500000000 V/A |
| 最大理论 vs SPICE 误差 | **0.000157 mV** |
| 2.5 A 分流压降 | 25.000 mV |
| 2.5 A 分流功耗 | 62.500 mW |
| 输出滤波截止 | 1591.55 Hz |
| 阶跃建立 | 100.02 µs |
| 真实 SPICE 求解 | 3 次 |

饱和工况：

| 电流 | 输出 | 状态 |
| --- | --- | --- |
| −3.50 A | 0.100 V | 放大器下限饱和 |
| −3.25 A | 0.100 V | 放大器下限饱和 |
| −3.00 A | 0.150 V | 正常 |
| +3.25 A | 3.275 V | 正常 |
| +3.50 A | 3.400 V | ADC 上限饱和 |

## 11. 常见错误

1. 单电源不加油点偏置，负电流被截断。
2. 把 25 mV 分流压降当“越大越好”；功耗随 I² 增长。
3. 把 INA240 行为模型当芯片内部电路。
4. 把 Datasheet ±25 µV 失调说成本人实测。
5. 忘记 ±3.3 V 输出限制：3.5 A 时 3.4 V 已超过 ADC 参考。

## 12. 独立学习练习

1. 把 Rshunt 改为 1 mΩ，重算 ±2.5 A 压降、功耗与电流分辨率。
2. 把零点从 1.65 V 改为 0.5 V，观察负电流饱和点。
3. 计算 1 kΩ/0.1 µF 的 1% 建立时间并与仿真比较。

## 13. 面试问题

1. 为什么双向电流检测需要零点偏置？
2. 采样电阻为什么不能无限增大？
3. INA240 的高共模范围解决了什么问题？
4. 输入失调与输出失调如何区分？
5. 电流采集的饱和应如何在上层软件中表示？
