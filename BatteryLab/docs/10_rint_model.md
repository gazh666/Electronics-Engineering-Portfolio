# 10 Rint 模型

## 1. 电路拓扑

```text
 n_ocv ── R0 ── out
   +             │
  OCV 3.8 V      Iload
   -             │
  gnd ───────────┘
```

只有 OCV 与欧姆内阻，没有极化动态。

## 2. 专业公式

```text
Vterminal = OCV - I·R0
Pohmic    = I²·R0
ΔVohmic   = I·R0
```

## 3. 变量与单位

| 符号 | 含义 | 单位 |
| --- | --- | --- |
| OCV | 开路电压 | V |
| I | 电流，放电为正 | A |
| R0 | 欧姆内阻 | Ω |
| Vterminal | 端电压 | V |
| Pohmic | 内阻损耗 | W |

## 4. 公式推导

R0 为线性电阻，端电压与电流满足代数关系：

```text
V = OCV - I·R0
```

功率损耗为 `P = I²R0`，与电流方向无关，充电时同样发热。该式由焦耳定律直接得到，不需要时间积分。

## 5. 适用条件

- 只适用于短时间尺度、忽略极化与扩散的粗略估算。
- 不能描述负载移除后的渐变恢复过程。
- 教学参数：`R0=30 mΩ`、`OCV=3.8 V`、容量 2 Ah。

## 6. 实际代码与核心函数

| 功能 | 路径 | 函数 |
| --- | --- | --- |
| 端电压 | `battery_models/rint.py` | `calculate_rint_voltage` |
| 欧姆损耗 | `battery_models/rint.py` | `calculate_ohmic_loss` |
| 压降 | `battery_models/rint.py` | `calculate_ohmic_drop` |
| 扫描表 | `battery_models/rint.py` | `rint_benchmark_rows` |
| 时间序列 | `battery_models/ecm_solver.py` | `simulate_ecm`（0 个 RC 支路） |

## 7. 关键代码逐行解释

```python
def calculate_rint_voltage(ocv_v, current_a, r0_ohm):
    ocv = _finite(ocv_v, "OCV")            # 拒绝布尔/NaN/Inf
    current = _finite(current_a, "电流")
    resistance = _finite(r0_ohm, "欧姆内阻")
    if resistance < 0.0:
        raise RintError("欧姆内阻必须为零或正数")
    return ocv - current * resistance      # 直接套用代数关系
```

## 8. 实际运行命令

```powershell
conda run -n kaifa_battery python -m scripts.rint_demo
```

## 9. 真实结果

运行编号：`ecm_20261126_122841_613386`（`results/ecm/run_ecm_20261126_122841_613386/`）。

| 电流 (A) | 压降 (V) | 端电压 (V) | 内阻损耗 (W) | 模式 |
| --- | --- | --- | --- | --- |
| 0.0 | 0.000 | 3.800 | 0.000 | rest |
| 0.5 | 0.015 | 3.785 | 0.0075 | discharge |
| 1.0 | 0.030 | 3.770 | 0.030 | discharge |
| 2.0 | 0.060 | 3.740 | 0.120 | discharge |
| 3.0 | 0.090 | 3.710 | 0.270 | discharge |
| -0.5 | -0.015 | 3.815 | 0.0075 | charge |
| -1.0 | -0.030 | 3.830 | 0.030 | charge |

2 A 脉冲：接入瞬间端电压从 3.800 V 跌至 3.740 V，跌落 60.000 mV；R0 反算值为 `0.030000 Ω`。移除负载后立即回到 3.800 V，恢复时间 0 s，这是 Rint 没有极化状态的必然结果，不是“恢复很快”的工程结论。

原始证据：

- `results/ecm/run_ecm_20261126_122841_613386/rint_sweep.csv`
- `results/ecm/run_ecm_20261126_122841_613386/summary.json`

## 10. 常见错误

- 用 Rint 解释“移除负载后电压缓慢回升”。
- 充电时把内阻损耗写成负值（功率损耗恒为非负）。
- 用 `OCV × I` 当作输出功率而忽略内阻压降。

## 11. 独立练习

1. 计算 R0=20 mΩ、3 A 时的端电压与损耗。
2. 说明为什么 Rint 的 `recovery_time_s` 为 0。
3. 用两点实验数据反推 R0，并分析采样误差的影响。

## 12. 面试题

1. 如何用一次负载阶跃测量电池直流内阻？
2. R0 是否会随 SOC 和温度变化？
3. Rint 模型在 BMS 中还有哪些用途？
4. 为什么脉冲法测得的内阻与交流阻抗法不同？
