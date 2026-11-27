# 31 模拟前端基础

## 1. 电路拓扑

```text
电芯组（浮地、串联）
   │
   ├─ 高压节点 ── 分压/滤波 ── 差分放大器 ── ADC ── 数字恢复
   ├─ 低压节点 ── 分压/滤波 ──┘
   ├─ 分流电阻 ── 电流放大器 ── ADC
   └─ NTC ── 上拉分压 ── ADC
```

AFE 的核心不是“把电压接进 ADC”，而是把**高共模、浮地、带噪声的模拟量**转换为 ADC 能接受的
**低共模、限带、已知增益**信号。

## 2. 专业原理

1. 串联电芯的每个节点对地电压很高，但真正要测的是相邻节点之差。
2. 差分放大器抑制共模，只放大差模；共模抑制能力由电阻匹配与运放 CMRR 共同决定。
3. RC 低通限制带宽，抑制高频干扰，但会引入延迟与建立时间。
4. 分流电阻把电流变成毫伏级电压，需要低失调、高共模范围的电流放大器。
5. NTC 分压把温度变成电压，比率式测量可抵消部分激励源误差。
6. ADC 把模拟电压量化，量化误差只是总误差的一部分。

## 3. 公式推导

差分与共模定义：

```text
Vdiff = Vhigh - Vlow
Vcm   = (Vhigh + Vlow)/2
```

理想差分放大器：

```text
Vout = Vref + k*Vdiff,  k = R2/R1 = R4/R3
```

实际输出的一阶误差模型：

```text
Vout = Vref + Ad*Vdiff + Acm*Vcm + Vos + Vnoise
```

ADC 量化：

```text
LSB = Vref_adc/2^N
```

## 4. 变量及单位

| 量 | 含义 | 单位 |
| --- | --- | --- |
| `Vhigh/Vlow` | 电芯正/负端对地电压 | V |
| `Vdiff` | 单体电压 | V |
| `Vcm` | 电池节点共模 | V |
| `Ad` | 差模增益 | V/V |
| `Acm` | 共模增益 | V/V |
| `Vos` | 输入失调 | V |
| `LSB` | ADC 量化步距 | V |
| `N` | ADC 位数 | bit |

## 5. 实际器件参数来源

- 运放：教学理想模型与教学非理想模型，**不是商业运放**。
- 电流放大器：INA240A2 官方规格行为模型（SBOS662C），不是芯片内部晶体管电路。
- ADC：教学 12 位行为模型，不是 BQ76922 内部 ADC。
- 电阻/电容：教学假设值，0.1% 与 1% 容差用于容差实验。

## 6. 实际核心源码

- `sensing/voltage_decoder.py`
- `sensing/current_decoder.py`
- `sensing/temperature_decoder.py`
- `sensing/measurement_chain.py`
- `circuits/differential_amplifier.py`
- `circuits/current_sensing.py`
- `circuits/ntc_sensing.py`

## 7. 函数名称及行号

| 名称 | 位置 | 作用 |
| --- | --- | --- |
| `four_resistor_output` | `sensing/voltage_decoder.py:18` | 四电阻差分解析输出 |
| `amplifier_pin_common_mode` | `sensing/voltage_decoder.py:64` | 运放引脚共模 |
| `amplifier_output` | `sensing/current_decoder.py:37` | 电流→电压 |
| `temperature_from_voltage` | `sensing/temperature_decoder.py:105` | NTC 反演 |
| `measure_voltage` | `sensing/measurement_chain.py:36` | 电压全链路 |
| `measure_current` | `sensing/measurement_chain.py:89` | 电流全链路 |
| `measure_temperature` | `sensing/measurement_chain.py:148` | 温度全链路 |

## 8. 核心代码逐行解释

```python
vp = (vhigh * r4 + vref * r3) / (r3 + r4)          # 同相端分压
vn = (vlow * r2 + out * r1) / (r1 + r2)            # 反相端分压
return {"v_inp_v": vp, "v_inm_v": vn, "v_out_v": out}
```

- 第 1 行把电池高压节点按 R3/R4 分压到运放同相端；
- 第 2 行把电池低压节点与输出按 R1/R2 分压到反相端；
- 虚短成立时 `vp≈vn`，两式联立即得四电阻差分公式；
- 饱和或超共模时虚短不再成立，因此代码只把它作为**理想解析参考**，真实输出由 SPICE 给出。

## 9. 实际运行命令

```powershell
conda run -n kaifa_battery python -m scripts.cell_voltage_sensing_demo
conda run -n kaifa_battery python -m scripts.differential_amplifier_demo
conda run -n kaifa_battery python -m scripts.current_sensing_demo
conda run -n kaifa_battery python -m scripts.ntc_sensing_demo
```

## 10. 实际图表及原始结果路径

- `results/sensing/run_sensing_20261126_135112_b44fef/plots/01_3s_node_voltages.png`
- `results/sensing/run_sensing_20261126_135218_cb8cf7/plots/04_diff_amp_transfer.png`
- `results/sensing/run_sensing_20261126_135555_720959/plots/09_bidirectional_current_transfer.png`
- `results/sensing/run_sensing_20261126_135306_def360/plots/18_ntc_divider_temperature.png`

## 11. 常见错误

1. 把节点对地电压当单体电压：错误接地时 cell2 偏差 **3.6 V**（真实运行结果）。
2. 把电池节点共模 9.4 V 当作运放引脚共模；实际顶部通道引脚共模约 3.93 V。
3. 认为理想运放可以无限共模；实际受供电与输入范围限制。
4. 把 ADC 位数当作精度；12 位 LSB 只是 0.806 mV。
5. 忽略 RC 滤波的负载效应：47 Ω 造成约 0.85–0.94 mV 系统误差。

## 12. 独立学习练习

1. 用 `four_resistor_output` 计算 R1 偏 1% 时 cell3 的输出变化。
2. 把 `common_mode_v` 从 0 扫到 13 V，观察引脚共模何时超过 5 V。
3. 计算 100 kHz 干扰经过 7696 Hz 一阶滤波后的理论衰减。

## 13. 面试问题

1. 为什么串联电芯需要差分采样？
2. 共模电压与差分电压有什么区别？
3. 虚短、虚断分别在什么条件下成立？
4. 为什么 ADC 分辨率不等于采集精度？
5. 如果共模超限，输出会怎样变化？
