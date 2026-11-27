# 11 一阶 RC 模型

## 1. 电路拓扑

```text
 n_ocv ── R0 ── n1 ──┬── R1 ── out
   +               === C1        │
  OCV              │            Iload
   -               │             │
  gnd ─────────────┴─────────────┘
```

R0 描述瞬时欧姆压降，R1/C1 描述单一极化过程。

## 2. 专业公式

```text
Vterminal = OCV - I·R0 - V1
dV1/dt    = -V1/(R1·C1) + I/C1
τ1        = R1·C1
```

恒流建立阶段：

```text
V1(t) = I·R1·(1 - exp(-t/τ1))
```

静置恢复阶段（初始值为 V1(0)）：

```text
V1(t) = V1(0)·exp(-t/τ1)
```

## 3. 变量与单位

| 符号 | 含义 | 单位 |
| --- | --- | --- |
| R1 | 极化电阻 | Ω |
| C1 | 极化等效电容 | F |
| τ1 | 极化时间常数 | s |
| V1 | 极化电压 | V |

## 4. 公式推导

对 `C1·dV1/dt + V1/R1 = I` 两边除以 C1，得到标准一阶线性方程。恒定电流下通解为：

```text
V1(t) = I·R1 + [V1(0) - I·R1]·exp(-t/τ1)
```

当 `V1(0)=0` 时即建立公式；当 `I=0` 时退化为纯指数衰减。离散形式：

```text
V1[k+1] = V1[k]·exp(-dt/τ1) + I·R1·(1 - exp(-dt/τ1))
```

## 5. 适用条件

- 单一主导极化过程，例如较短时间尺度的电荷转移。
- 不能同时刻画快、慢两个明显分离的极化过程。
- 教学参数：R1=20 mΩ、C1=1000 F，τ1=20 s。

## 6. 实际代码与核心函数

| 功能 | 路径 | 函数 |
| --- | --- | --- |
| 时间常数 | `battery_models/first_order_rc.py` | `calculate_time_constant` |
| 状态更新 | `battery_models/first_order_rc.py` | `update_first_order_polarization` |
| 端电压 | `battery_models/first_order_rc.py` | `first_order_terminal_voltage` |
| 极化损耗 | `battery_models/first_order_rc.py` | `calculate_polarization_loss` |
| 储能 | `battery_models/first_order_rc.py` | `calculate_stored_energy` |
| 时间常数检查 | `analysis/polarization_analysis.py` | `time_constant_checkpoints` |

## 7. 关键代码逐行解释

`update_first_order_polarization` 委托统一更新函数：

```python
return update_polarization_voltage(previous_voltage_v, current_a, r1_ohm, c1_f, dt_s)
```

`update_polarization_voltage` 内部：

```python
tau = resistance * capacitance
decay = math.exp(-dt / tau)
return previous * decay + current * resistance * (-math.expm1(-dt / tau))
```

第一项保留历史极化，第二项是本步电流建立的极化增量；两者系数之和为 1 减去同一衰减量，保证稳态收敛到 `I·R1`。

## 8. 实际运行命令

```powershell
conda run -n kaifa_battery python -m scripts.first_order_rc_demo
```

## 9. 真实结果

运行编号：`ecm_20261126_122846_d4bb75`（`results/ecm/run_ecm_20261126_122846_d4bb75/`）。

| 指标 | 实际值 |
| --- | --- |
| 时间常数 τ1 | 20.000 s |
| 2 A 瞬时压降（R0） | 60.000 mV |
| 脉冲结束（69.9 s 采样）端电压 | 3.702001 V |
| 60.0 s 解析端电压 | 3.701991 V |
| 断开瞬间回升（R0） | 59.990 mV |
| 最大压降 | 97.999 mV |
| 恢复至 ±1 mV 的时间 | 72.8 s（观察窗 120 s） |
| 程序与解析最大误差 | 4.44e-16 V（MAE 6.00e-17 V） |

时间常数检查点（建立阶段）：

| t/τ | 理论比例 | 实测比例 | 误差 |
| --- | --- | --- | --- |
| 0.5 | 0.393469 | 0.393469 | 1.1e-16 |
| 1.0 | 0.632121 | 0.632121 | -3.4e-15 |
| 2.0 | 0.864665 | 0.864665 | -4.1e-15 |
| 3.0 | 0.950213 | 0.950213 | 5.6e-16 |

恢复阶段在 0.5 τ 处相对误差 1.59e-4，原因是 0.1 s 采样并非恰好落在 0.5τ 时刻，属于采样误差而不是模型误差；建立阶段在整 τ 点采样，误差在浮点精度量级。

原始证据：

- `results/ecm/run_ecm_20261126_122846_d4bb75/waveform.csv`
- `results/ecm/run_ecm_20261126_122846_d4bb75/energy_balance.json`
- `results/ecm/run_ecm_20261126_122846_d4bb75/plots/04_polarization_checkpoints.png`

## 10. 常见错误

- 把 `I²R1` 当作极化损耗；正确是 `V1²/R1`。
- 用 60 s 末的 69.9 s 采样值直接对比 60.0 s 解析值，产生 10 µV 级“误差”。
- 认为 1τ 时电压“完全建立”（实际 63.21%）。
- 忽略库仑效率对 SOC 的影响（本阶段效率取 1.0）。

## 11. 独立练习

1. 计算 2τ、4τ 时的极化比例。
2. 将 C1 减半，观察 τ 与恢复时间如何变化。
3. 用 1 A 充电脉冲验证 V1 为负值。

## 12. 面试题

1. 如何从脉冲响应的指数段拟合 R1 与 C1？
2. 为什么 τ 相同的 R1、C1 组合在恒流响应中不可区分？
3. 一阶 RC 在什么工况下误差最大？
4. 极化损耗为什么不是 `I²R1`？
