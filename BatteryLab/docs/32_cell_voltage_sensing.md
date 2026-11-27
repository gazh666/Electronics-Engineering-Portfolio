# 32 3S 单体电压采集

## 1. 电路拓扑

```text
N3 (11.4 V) ──47Ω──┬── R3 100k ──┐
                    │ 0.22µF      ├── 运放 ── out3
N2 (7.4 V) ──47Ω────┴── R4 50k ───┘
                    │
                    └── R1 100k / R2 50k 反馈网络

N2 (7.4 V) ──47Ω──┬── ... ── out2
N1 (3.6 V) ──47Ω──┘
N1 (3.6 V) ──47Ω──┬── ... ── out1
N0 (0 V)  ──47Ω───┘
```

三路完全相同的四电阻差分通道，共用 0.2 V 参考。

## 2. 专业原理

- 每节电芯使用独立差分通道，输出以 0.2 V 为基准，增益 0.5。
- 单体电压范围 2.5–4.25 V → 输出 1.45–2.325 V，位于 3.3 V ADC 范围中部。
- 输入 47 Ω + 0.22 µF 构成差模低通，同时给 AFE 提供开线检测节点。
- 47 Ω 与 100 kΩ 分压臂串联，形成不可忽略的负载效应。

## 3. 公式推导

```text
Vout_k = 0.2 + 0.5*(N_k - N_{k-1})
Vcell_k = (Vout_k - 0.2)/0.5
```

含滤波负载的修正：

```text
Vout_k = (1+R2/R1')*(Vhigh*R4+Vref*R3')/(R3'+R4) - (R2/R1')*Vlow
R1' = R1 + 47 Ω,  R3' = R3 + 47 Ω
```

## 4. 变量及单位

| 量 | 数值 | 单位 |
| --- | --- | --- |
| R1/R3 | 100 kΩ | Ω |
| R2/R4 | 50 kΩ | Ω |
| 增益 k | 0.5 | V/V |
| Vref | 0.2 | V |
| 滤波 R | 47 | Ω |
| 滤波 C | 0.22 | µF |
| 单体范围 | 2.5–4.25 | V |

## 5. 实际器件参数来源

- 电阻/电容/参考：`configs/afe_config.yaml`，教学假设值。
- 运放：理想 VCVS 模型，开环增益 1e6，输出 0–5 V。
- 不是商业运放，也不是 BQ76922 内部采样网络。

## 6. 实际核心源码

- `circuits/cell_voltage_sensing.py`
- `sensing/voltage_decoder.py`
- `scripts/cell_voltage_sensing_demo.py`

## 7. 函数名称及行号

| 名称 | 位置 | 作用 |
| --- | --- | --- |
| `node_voltages` | `circuits/cell_voltage_sensing.py:25` | 3S 节点电压 |
| `build_3s_stack` | `circuits/cell_voltage_sensing.py:37` | 纯电压源串联 |
| `solve_3s_sensing` | `circuits/cell_voltage_sensing.py:128` | 三通道真实 SPICE |
| `wrong_ground_mapping` | `circuits/cell_voltage_sensing.py:179` | 错误接地对照 |
| `four_resistor_output` | `sensing/voltage_decoder.py:18` | 解析输出 |

## 8. 核心代码逐行解释

```python
rows = solve_3s_sensing([3.6, 3.8, 4.0], config)   # 一次工作点求解三路
for row in rows:
    error = row["vout_v"] - row["theory_v"]         # SPICE 与含滤波理论之差
```

- `solve_3s_sensing` 内部先建 3 个串联电压源，再为每路复制 RC + 四电阻 + 运放；
- `theory_v` 已把 47 Ω 并入 R1/R3，因此 `error_v` 只剩数值求解误差；
- `theory_no_filter_v` 与 `theory_v` 的差就是滤波负载效应，单独保存为 `filter_loading_error_v`。

## 9. 实际运行命令

```powershell
conda run -n kaifa_battery python -m scripts.cell_voltage_sensing_demo
```

## 10. 实际图表及原始结果路径

Run ID：`sensing_20261126_135112_b44fef`

- `results/sensing/run_sensing_20261126_135112_b44fef/plots/01_3s_node_voltages.png`
- `results/sensing/run_sensing_20261126_135112_b44fef/plots/02_3s_cell_differential_voltages.png`
- `results/sensing/run_sensing_20261126_135112_b44fef/plots/03_diff_amp_channel_outputs.png`

实际结果：

| 指标 | 数值 |
| --- | --- |
| 节点 | 0 / 3.6 / 7.4 / 11.4 V |
| 单体 | 3.6 / 3.8 / 4.0 V |
| KVL 误差 | 0 V |
| 错误接地 cell2 偏差 | **3.6 V** |
| SPICE vs 含滤波理论最大误差 | **3.298 µV** |
| 滤波负载效应 | **0.846 / 0.893 / 0.940 mV** |
| 真实 SPICE 求解 | 2 次 |

## 11. 常见错误

1. 把 N2=7.4 V 直接当 cell2；正确值是 7.4−3.6=3.8 V。
2. 用单端 ADC 直接采 N1/N2/N3，忽略共模与耐压。
3. 忘记 47 Ω 的负载效应，把 0.9 mV 误差误判为 SPICE 误差。
4. 把 3 路通道的输出直接相加当组端电压而不做校准。
5. 认为 KVL 误差为 0 就证明采集精度为 0；KVL 只验证节点关系。

## 12. 独立学习练习

1. 把 cell2 改为 3.5 V，重算 N1/N2/N3 与三路输出。
2. 把 47 Ω 改为 100 Ω，观察滤波负载效应是否翻倍。
3. 构造“把 N2 直接接地”的错误拓扑，解释为什么输出饱和。

## 13. 面试问题

1. 3S 电池组中 N2 对地 7.4 V，为什么不能直接送 ADC？
2. 差分放大器的输入共模如何计算？
3. 47 Ω 滤波电阻为什么会带来增益误差？
4. 如何用一次工作点求解验证三路差分通道？
