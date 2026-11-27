# 37 NTC 温度采集

## 1. 电路拓扑

```text
Vexc 3.3 V ── Rpull 10 kΩ ──┬── TS / ADC
                            │
                          NTC 10 kΩ
                            │
                           GND
```

NTC 接地、固定电阻上拉，比率式分压。

## 2. 专业原理

- NTC 电阻随温度升高而下降，B 值模型描述其指数特性。
- 分压电压随温度单调下降，适合 ADC 直接采集。
- 比率式测量让激励源误差在 `R=V/(Vexc−V)` 中部分抵消。
- 自热会改变 NTC 自身温度，需要耗散系数才能定量，本阶段缺少该参数。

## 3. 公式推导

```text
Rntc(T) = R25*exp(B*(1/(T+273.15) − 1/298.15))
Vntc = Vexc*Rntc/(Rpull+Rntc)
Rntc = Rpull*Vntc/(Vexc−Vntc)
T = 1/(1/298.15 + ln(Rntc/R25)/B) − 273.15
P = Vntc²/Rntc
```

## 4. 变量及单位

| 量 | 数值 | 单位 |
| --- | --- | --- |
| R25 | 10 | kΩ |
| B | 3950 | K |
| Rpull | 10 | kΩ |
| Vexc | 3.3 | V |
| 温度范围 | 0–60 | ℃ |
| 25 ℃ 灵敏度 | −36.7 | mV/℃ |
| ADC 量化折算 | 0.022 | ℃ |

## 5. 实际器件参数来源

- `configs/ntc_config.yaml`：教学假设 10 kΩ / B3950 / 10 kΩ 上拉。
- 没有指定真实商业 NTC 料号；BOM 中为 TBD。
- 耗散系数未提供，自热温升 `NOT_VERIFIED`。

## 6. 实际核心源码

- `sensing/temperature_decoder.py`
- `circuits/ntc_sensing.py`
- `scripts/ntc_sensing_demo.py`

## 7. 函数名称及行号

| 名称 | 位置 | 作用 |
| --- | --- | --- |
| `ntc_resistance` | `sensing/temperature_decoder.py:29` | 温度→电阻 |
| `ntc_temperature` | `sensing/temperature_decoder.py:51` | 电阻→温度 |
| `divider_voltage` | `sensing/temperature_decoder.py:72` | 分压 |
| `resistance_from_voltage` | `sensing/temperature_decoder.py:86` | 电压→电阻 |
| `temperature_from_voltage` | `sensing/temperature_decoder.py:105` | 电压→温度 |
| `voltage_sensitivity_v_per_c` | `sensing/temperature_decoder.py:117` | 灵敏度 |
| `sweep_temperatures_fast` | `circuits/ntc_sensing.py:172` | 真实 SPICE 扫描 |
| `run_open_short` | `circuits/ntc_sensing.py:129` | 开路/短路 |

## 8. 核心代码逐行解释

```python
circuit.B("ntc", "vntc", circuit.gnd,
          i="V(temp)/(R25*exp(B*(1/(V(tctl)*1000+273.15)-1/298.15)))")
```

- 用行为电流源表示 NTC：电流 = 端电压 / R(T)；
- 温度由 `V(tctl)` 控制，`V(tctl)*1000+273.15` 转为开尔文；
- 这是一条连续行为方程，不是把 Python 结果写进网表。

## 9. 实际运行命令

```powershell
conda run -n kaifa_battery python -m scripts.ntc_sensing_demo
```

## 10. 实际图表及原始结果路径

Run ID：`sensing_20261126_135306_def360`

- `results/sensing/run_sensing_20261126_135306_def360/plots/17_ntc_resistance_temperature.png`
- `results/sensing/run_sensing_20261126_135306_def360/plots/18_ntc_divider_temperature.png`
- `results/sensing/run_sensing_20261126_135306_def360/plots/19_ntc_temperature_recovery_error.png`

实际结果：

| 指标 | 数值 |
| --- | --- |
| SPICE vs 理论最大电压误差 | **18.115 µV** |
| 理想反演最大温度误差 | **0.000853 ℃** |
| ADC 后最大温度误差 | **0.012896 ℃** |
| 0 ℃ 分压 | 2.54348 V |
| 25 ℃ 分压 | 1.65000 V |
| 60 ℃ 分压 | 0.65707 V |
| 25 ℃ 自热功率 | 272 µW |
| 自热温升 | **NOT_VERIFIED** |
| 真实 SPICE 求解 | 3 次 |

AFE 异常状态（`results/sensing/run_sensing_20261126_135542_6eec7a`）：

| 场景 | 电压 | 状态 |
| --- | --- | --- |
| NTC 开路 | 3.267 V | `SENSOR_OPEN` |
| NTC 短路 | 0.033 V | `SENSOR_SHORT` |

## 11. 常见错误

1. 用线性公式近似 NTC，忽略 B 值指数。
2. 把 0.013 ℃ 的 ADC 量化误差当成完整温度精度。
3. 忽略自热，缺少耗散系数却宣称温升可忽略。
4. 上拉电阻容差与 R25 容差不做区分。
5. 开路/短路只报数值，不报明确状态。

## 12. 独立学习练习

1. 计算 B=3380 的 NTC 在 0/25/60 ℃ 的电阻与分压。
2. 把上拉改为 4.7 kΩ，观察 60 ℃ 附近灵敏度变化。
3. 给定耗散系数 2 mW/℃，估算 272 µW 自热温升。

## 13. 面试问题

1. NTC 的温度特性是什么？
2. 为什么采用比率式分压？
3. 如何识别 NTC 开路与短路？
4. 自热误差如何评估？
5. 12 位 ADC 对 NTC 温度分辨率意味着什么？
