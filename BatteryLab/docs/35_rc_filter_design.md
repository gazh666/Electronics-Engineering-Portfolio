# 35 输入 RC 滤波设计

## 1. 电路拓扑

```text
Vhigh ──47Ω──┬── 到差分放大器
             │
          0.22µF
             │
Vlow  ──47Ω──┴── 到差分放大器
```

两根输入线各串 47 Ω，差分电容跨接在放大器输入端之间。

## 2. 专业原理

- 差模一阶低通：`Rdiff = 2*47 Ω`，`Cdiff = 0.22 µF`。
- 抑制高频共模/差模干扰，降低 ADC 混叠风险。
- 代价：截止频率约 7.7 kHz，阶跃建立约 45 µs（10–90%）/95 µs（1%）。
- 与 100 kΩ 分压臂串联会产生负载效应（见 docs/32）。

## 3. 公式推导

```text
tau = 2*R*C = 94*0.22e-6 = 20.68 µs
fc = 1/(2π*tau) = 7696.08 Hz
|H(f)| = 1/sqrt(1+(f/fc)²)
A_db(f) = −10*log10(1+(f/fc)²)
tr = 2.197*tau = 45.43 µs
ts(1%) = 4.605*tau = 95.23 µs
```

100 kHz：

```text
A_db = −10*log10(1+(100000/7696.08)²) = −22.300 dB
```

## 4. 变量及单位

| 量 | 数值 | 单位 |
| --- | --- | --- |
| R（单边） | 47 | Ω |
| Rdiff | 94 | Ω |
| Cdiff | 0.22 | µF |
| tau | 20.68 | µs |
| fc | 7696.08 | Hz |
| tr | 45.43 | µs |
| ts(1%) | 95.23 | µs |

## 5. 实际器件参数来源

- 47 Ω / 0.22 µF：`configs/afe_config.yaml`，教学假设。
- BQ76922 数据手册 p.7 推荐外部单体输入 20–100 Ω、0.1–0.22–1 µF，本设计落在推荐区间。
- 电容温度特性未建模，标记为理想 C。

## 6. 实际核心源码

- `circuits/rc_filter.py`
- `analysis/filter_response.py`
- `scripts/rc_filter_demo.py`

## 7. 函数名称及行号

| 名称 | 位置 | 作用 |
| --- | --- | --- |
| `RCFilterConfig` | `circuits/rc_filter.py:35` | R/C 配置与 tau/fc |
| `theoretical_cutoff_hz` | `circuits/rc_filter.py:58` | 理论截止 |
| `run_ac_response` | `circuits/rc_filter.py:81` | 真实 ngspice AC |
| `extract_cutoff` | `circuits/rc_filter.py:107` | 插值提取 −3 dB |
| `run_step_response` | `circuits/rc_filter.py:137` | 真实瞬态阶跃 |
| `run_interference` | `circuits/rc_filter.py:228` | 100 kHz 干扰 |
| `scan_parameters` | `circuits/rc_filter.py:272` | 12 组参数扫描 |
| `extract_ac_metrics` | `analysis/filter_response.py:40` | AC 指标 |

## 8. 核心代码逐行解释

```python
denominator = data["hi"] - data["lo"]      # 输入差模
numerator = data["sh"] - data["sl"]        # 滤波后差模
transfer = numerator / denominator         # 复数传递函数
```

- 直接从 ngspice AC 节点电压取复数比，不经过 Python 重算；
- `extract_cutoff` 在 |H| 下降到低频增益的 1/√2 处做对数插值；
- `run_interference` 同时保存滤波前后 RMS，衰减按 20log10(Vrms_after/Vrms_before)。

## 9. 实际运行命令

```powershell
conda run -n kaifa_battery python -m scripts.rc_filter_demo
```

## 10. 实际图表及原始结果路径

Run ID：`sensing_20261126_135324_f7f014`

- `results/sensing/run_sensing_20261126_135324_f7f014/plots/07_rc_filter_bode.png`
- `results/sensing/run_sensing_20261126_135324_f7f014/plots/08_rc_step_response.png`
- `results/sensing/run_sensing_20261126_135324_f7f014/plots/08b_rc_interference_100khz.png`
- `results/sensing/run_sensing_20261126_135324_f7f014/plots/08c_rc_parameter_tradeoff.png`

实际结果：

| 指标 | 数值 |
| --- | --- |
| 理论截止 | 7696.08 Hz |
| SPICE 截止 | 7695.23 Hz |
| 相对误差 | **−0.011%** |
| 100 kHz 衰减 | **−22.3003 dB** |
| 理论 100 kHz 衰减 | −22.3003 dB |
| 实测上升时间 | 45.427 µs |
| 理论上升时间 | 45.434 µs |
| 相对误差 | 0.0145% |
| 超调 | 0.0005% |
| 稳态误差 | −0.583 µV |
| 100 kHz 干扰 RMS | 0.1414 V → 0.01085 V（−22.301 dB） |
| 真实 SPICE 求解 | 27 次 |

## 11. 常见错误

1. 只算单边 47 Ω，忘记差模是 94 Ω。
2. 用理想电容忽略 X7R 的电压/温度系数。
3. 把 100 kHz 衰减 −22 dB 当成对任意高频都足够。
4. 忽略滤波延迟对保护响应的影响。
5. 把 27 次 SPICE 求解与 12 组参数扫描混淆。

## 12. 独立学习练习

1. 把 C 改为 0.1 µF，重算 fc/tr 并解释参数取舍。
2. 计算 1 kHz 处的理论衰减并与 SPICE 对比。
3. 设计一个 50 Hz 强干扰下的两级 RC 方案并讨论延迟代价。

## 13. 面试问题

1. 为什么差分 RC 的时间常数是 2RC？
2. RC 滤波会带来什么延迟？
3. 100 kHz 干扰如何影响 1 kHz 采样 ADC？
4. 怎样在滤波带宽与保护响应之间取舍？
