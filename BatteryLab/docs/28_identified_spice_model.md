# 28 辨识参数导入真实 SPICE 与 3S 电池组

## 1. 专业原理

把辨识得到的 `R0/R1/C1/R2/C2` 写入真实 ngspice 网表，在同一 OCV、同一电流脉冲、同一初始状态下
比较 Python 与 ngspice 的非阶跃区间端电压，验证“参数 → 电路 → 数值求解”链路一致。

## 2. 公式推导

一阶 RC 网表：`OCV — R0 —(R1 ∥ C1)— 负载`。解析解：

```text
V(t) = OCV − I·R0 − I·R1·(1 − exp(−t/τ1))
```

二阶叠加 `R2 ∥ C2`。3S1P：

```text
V_pack = Σ_{k=1..3} V_cell,k
```

一致性误差：

```text
e_max = max_t |V_Python(t) − V_ngspice(t)|，排除电流阶跃后 0.15 s
```

## 3. 参数物理意义与单位

| 量 | 含义 | 单位 |
| --- | --- | --- |
| `OCV` | 固定工作点开路电压（SOC 0.55 → 3.7215） | V |
| `R0/R1/R2` | 欧姆/快/慢极化电阻 | Ω |
| `C1/C2` | 极化电容 | F |
| `V_pack` | 3S 组端电压 | V |
| `e_max` | 实现一致性误差 | V/mV |

## 4. 实际文件路径

- `circuits/battery_ecm_circuit.py`
- `circuits/battery_pack_circuit.py`
- `simulations/spice_battery_runner.py`
- `battery_models/battery_pack.py`
- `results/identified_spice/run_identified_spice_20261126_131837_230b2b/`
  （`spice_pack_bms_summary.json`、`bms_design_reference.csv`、`pack_waveform.csv`、`pack_cell_waveform.csv`）

## 5. 实际类与函数

| 名称 | 作用 |
| --- | --- |
| `run_spice_single_cell(...)` | 生成网表并真实调用 ngspice |
| `run_spice_pack(...)` | 3S 网表求解 |
| `build_uniform_pack(...)` | 3 节一致电池组 |
| `simulate_series_pack(...)` | 串并联求和与限压逻辑 |
| `simulate_constant_power(...)` | 恒功率工况 |
| `analytic_pulse_response(...)` | 独立解析校核 |

## 6. 关键源码逐行解释

```python
definition = parameters.as_definition()          # 辨识参数 → 电路定义
spice = run_spice_single_cell(..., ocv_v=ocv_value, profile=profile, step_s=0.05)
python_result = simulate_ecm(definition.parameters, definition.branches, ...)
compare_frames(spice["frame"], python_result.frame, exclude_times_s=(10.0, 70.0), exclude_window_s=0.15)
```

- 第 1 行把 C1/C2 由 `τ/R` 派生，保证单位一致；
- 第 2 行真实启动 ngspice（`ngspice` 34）；
- 第 3 行同一输入跑 Python 求解器；
- 第 4 行排除电流阶跃后的过渡区，只比较模型实现一致性。

## 7. 运行命令

```powershell
conda run -n kaifa_battery python -m scripts.identified_spice_demo
```

## 8. 实际结果

固定 OCV = 3.7215 V（SOC 0.55），2 A / 60 s 脉冲，0.05 s 步长：

| 模型 | Python vs ngspice 最大差 | 解析 vs Python 最大差 |
| --- | --- | --- |
| Rint | 0.0000 mV | 0.0000 mV |
| 一阶 RC | 0.001247 mV | 4.44×10⁻¹³ mV |
| 二阶 RC | 0.001600 mV | 8.88×10⁻¹³ mV |

3S1P（三节一致，初始 SOC 0.55）：

| 指标 | 数值 |
| --- | --- |
| 组端电压 | 11.1645 V → 11.1195 V |
| 最大单体压差 | 0.000 mV |
| 终止 | completed（未触发限压） |
| 20 W 恒功率 | 600 s 正常完成 |

BMS 参考表（20 项，分五节）：AFE 电压采集 4 项、电流采集 3 项、MOSFET 保护 4 项、电池均衡 3 项、
CC-CV 控制 6 项。典型值：单体电压 2.4034–4.2001 V；实验电流 −2.142–+4.002 A；R0 75.86 mΩ；
4 A 压降 303.4 mV；中段 OCV 斜率约 690 mV/SOC；0.3 与 0.7 SOC 的 OCV 差 262 mV；
慢时间常数 100 s；充电方向内阻压升 `NOT_VERIFIED`（缺少大电流充电阶跃）。

## 9. 已知局限

1. 1 mV 是实现一致性，不是对真实电池的预测精度；
2. 3S 使用三节相同参数，压差 0 不能证明均衡算法；
3. 固定 OCV 局部脉冲不覆盖 SOC 耦合；
4. 充电方向内阻压升缺真实数据，保留 `NOT_VERIFIED`；
5. 实验峰值电流不能直接作为保护阈值。

## 10. 独立学习练习

1. 把 R0 改大 10%，观察 Python 与 SPICE 是否仍一致；
2. 构造三节不一致参数，观察最大压差与终止单体；
3. 解释为什么排除阶跃后 0.15 s 再比较。

## 11. 相关面试题

1. 为什么模型实现一致性验证不能替代真实电池精度验证？
2. 3S 电池组串联仿真需要注意哪些边界条件？
3. 如何把辨识参数用于 AFE 量程、保护阈值与均衡策略设计？
