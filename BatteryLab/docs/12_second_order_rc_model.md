# 12 二阶 RC 模型

## 1. 电路拓扑

```text
 n_ocv ── R0 ── n1 ──┬── R1 ── n2 ──┬── R2 ── out
   +               === C1         === C2        │
  OCV              │              │            Iload
   -               └──────────────┴─────────────┘
```

两个 RC 支路在等效电路中依次串联，端电压同时减去两个极化电压。

## 2. 专业公式

```text
Vterminal = OCV - I·R0 - V1 - V2
dV1/dt    = -V1/(R1·C1) + I/C1
dV2/dt    = -V2/(R2·C2) + I/C2
```

恒流建立：

```text
V1(t) = I·R1·(1 - exp(-t/τ1))
V2(t) = I·R2·(1 - exp(-t/τ2))
```

## 3. 变量与单位

| 符号 | 含义 | 单位 |
| --- | --- | --- |
| R1, C1 | 快极化电阻/电容 | Ω / F |
| R2, C2 | 慢极化电阻/电容 | Ω / F |
| τ1, τ2 | 两个时间常数 | s |
| V1, V2 | 两个极化电压 | V |

教学参数：R1=20 mΩ、C1=1000 F（τ1=20 s）；R2=15 mΩ、C2=4000 F（τ2=60 s）。

## 4. 公式推导

两个 RC 支路互相独立（共用同一总电流，但状态方程解耦），因此可以分别套用一阶结论再叠加：

```text
Vterminal(t) = OCV - I·R0 - I·R1(1-e^{-t/τ1}) - I·R2(1-e^{-t/τ2})
```

静置时两个状态分别按各自时间常数衰减：

```text
Vj(t) = Vj(0)·exp(-t/τj)
```

## 5. 适用条件

- 存在两个明显分离的时间尺度时才需要二阶模型。
- 参数必须来自真实脉冲或阻抗数据辨识；教学参数只能验证数值方法。
- 更多支路并不自动等于更高精度，还可能引入参数可辨识性问题。

## 6. 实际代码与核心函数

| 功能 | 路径 | 函数 |
| --- | --- | --- |
| 时间常数 | `battery_models/second_order_rc.py` | `calculate_time_constants` |
| 状态更新 | `battery_models/second_order_rc.py` | `update_second_order_polarization` |
| 端电压 | `battery_models/second_order_rc.py` | `second_order_terminal_voltage` |
| 极化损耗 | `battery_models/second_order_rc.py` | `calculate_polarization_losses` |
| 储能 | `battery_models/second_order_rc.py` | `calculate_stored_energies` |
| 统一求解 | `battery_models/ecm_solver.py` | `simulate_ecm`（2 个 RC 支路） |

## 7. 关键代码逐行解释

```python
v1_next = update_polarization_voltage(v1_prev, current, r1, c1, dt)
v2_next = update_polarization_voltage(v2_prev, current, r2, c2, dt)
```

每个支路独立更新，互不耦合。求解器记录时：

```python
terminal = ocv - current * r0 - sum(polarization_voltages)
```

两个支路电压在端电压上直接相加；损耗则分别按 `Vj²/Rj` 计算，再求和。

## 8. 实际运行命令

```powershell
conda run -n kaifa_battery python -m scripts.second_order_rc_demo
```

## 9. 真实结果

运行编号：`ecm_20261126_122851_934617`（`results/ecm/run_ecm_20261126_122851_934617/`）。

| 指标 | 实际值 |
| --- | --- |
| τ1 / τ2 | 20.000 s / 60.000 s |
| 2 A 瞬时压降 | 60.000 mV |
| 脉冲结束（69.9 s）端电压 | 3.683056 V |
| 60.0 s 解析端电压 | 3.683028 V |
| 60 s 时 V1 / V2 | 38.009 mV / 18.964 mV |
| 最大压降 | 116.944 mV |
| 断开瞬间回升 | 59.972 mV |
| 恢复至 ±1 mV | 120 s 观察窗内未达到（NOT_RECOVERED） |
| 程序与解析最大误差 | 4.44e-16 V |

恢复未达标不是程序错误：120 s 静置只相当于 2 个 τ2，慢支路仍残留约 2.6 mV，大于 1 mV 判据。报告必须如实写 `NOT_RECOVERED`，不能把观察窗延长到刚好通过。

原始证据：

- `results/ecm/run_ecm_20261126_122851_934617/waveform.csv`
- `results/ecm/run_ecm_20261126_122851_934617/energy_balance.json`
- `results/ecm/run_ecm_20261126_122851_934617/plots/04_two_polarization_branches.png`

## 10. 为什么二阶 RC 不一定比一阶更准确

1. 如果真实电池只有一个主导极化过程，第二个支路只会拟合噪声。
2. 两个时间常数接近时，参数强相关，辨识结果不稳定。
3. 增加支路会增加过拟合风险，在未参与拟合的工况上可能更差。
4. 本阶段二阶模型与解析解的误差极小，只证明数值实现正确，不证明它对真实电芯更准确。真实精度必须用独立实验数据验证（本阶段 CALCE 重放仍为未辨识基线）。

## 11. 常见错误

- 用同一组数据既辨识参数又宣称预测精度。
- 看到二阶模型曲线更“贴合”就认定更准确，而没有独立验证集。
- 把两个 τ 相近的支路强行解释为两个物理过程。

## 12. 独立练习

1. 把 R2 改为 0.02 Ω，观察 120 s 静置是否恢复。
2. 令 τ2=τ1，说明参数不可辨识的表现。
3. 比较一阶与二阶在 10 s 脉冲下的端电压差异。

## 13. 面试题

1. 二阶 RC 的两个时间常数分别对应什么物理过程？
2. 如何判断是否需要增加 RC 支路？
3. 参数辨识中如何避免过拟合？
4. 为什么“理论误差小”不能证明模型对真实电池准确？
