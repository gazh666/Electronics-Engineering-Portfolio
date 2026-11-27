# 16 真实 SPICE 电池电路

## 1. 电路拓扑

单体网表由 PySpice 构造，交给真实 ngspice 34 求解。二阶 RC 单体：

```text
VOCV n_ocv 0 3.8
R0   n_ocv n1 0.03
R1   n1 n2 0.02
C1   n1 n2 1000
R2   n2 out 0.015
C2   n2 out 4000
ILOAD out 0 PWL(...)
```

Rint 只有 `VOCV`、`R0`、`ILOAD`；一阶 RC 为 `R0 + R1/C1`。

三串电池组为三节首尾串联：

```text
V1(cell1_ocv, 0) → R0_1 → R1_1/C1_1 → R2_1/C2_1 → cell1
V2(cell2_ocv, cell1) → ... → cell2
V3(cell3_ocv, cell2) → ... → cell3
ILOAD cell3 0 PWL(...)
```

单体差分电压：`Vcell1=V(cell1)`、`Vcell2=V(cell2)-V(cell1)`、`Vcell3=V(cell3)-V(cell2)`。

## 2. 专业公式

PWL 电流源：

```text
I(t) = 分段线性插值{(t0,i0), (t1,i1), ...}
```

真实网表在每次电流阶跃处使用 1 ms 有限转换：

```text
(tb, Iold) → (tb+1ms, Inew)
```

SPICE 求解的是与 Python 相同的电路方程：

```text
Vterminal = OCV - I·R0 - V1 - V2
```

## 3. 变量与单位

| 量 | 含义 | 单位 |
| --- | --- | --- |
| PWL 时间点 | 电流转折时刻 | s |
| PWL 电流值 | 恒流段电流 | A |
| reltol/abstol/vntol | ngspice 收敛容差 | – / A / V |
| step/max_time | 输出步长与最大步长 | s |

## 4. 公式推导与数值设置

SPICE 瞬态分析对节点方程做数值积分，输出时刻由内部步长控制。为了与 Python 的 0.1 s 零阶保持对照，必须：

1. 采样步长取 0.05 s（小于 0.1 s，保证插值精度）；
2. 阶跃附近 0.15 s 内不参与误差统计（覆盖 1 ms PWL 转换与 0.1 s 网格插值区）；
3. 不使用过紧容差：`reltol=1e-6` 时三串电路会报 `timestep too small`，实际采用 `reltol=1e-5, abstol=1e-10, vntol=1e-7`。

## 5. 适用条件

- 网表只含线性 R/C 与理想电压源、电流源。
- 不含温度、老化、保护器件与寄生电感。
- 结果来自真实 ngspice，不再是 Python 预生成波形。

## 6. 实际代码与核心函数

| 功能 | 路径 | 函数/类 |
| --- | --- | --- |
| 单体的网表 | `circuits/battery_ecm_circuit.py` | `build_ecm_circuit` |
| PWL 生成 | `circuits/battery_ecm_circuit.py` | `build_pwl_points` |
| 瞬态求解 | `circuits/battery_ecm_circuit.py` | `run_transient` |
| 单体封装 | `circuits/battery_ecm_circuit.py` | `build_and_run_single_cell` |
| 三串网表 | `circuits/battery_pack_circuit.py` | `build_pack_circuit` |
| 三串封装 | `circuits/battery_pack_circuit.py` | `build_and_run_pack` |
| 结果落盘 | `simulations/spice_battery_runner.py` | `run_spice_single_cell`、`run_spice_pack` |

## 7. 关键代码逐行解释

```python
points = build_pwl_points(profile, transition_s)      # 阶跃处插入 1 ms 转换
circuit = Circuit(f"BatteryLab {model_name} benchmark")
circuit.V("OCV", "n_ocv", circuit.gnd, ocv_v)         # 理想 OCV 源
circuit.R("0", "n_ocv", "n1", r0)                     # 欧姆内阻
circuit.R("1", "n1", "n2", r1); circuit.C("1", "n1", "n2", c1)
circuit.PieceWiseLinearCurrentSource("LOAD", "out", circuit.gnd, values=points)
```

```python
simulator = circuit.simulator(temperature=25, nominal_temperature=25)
simulator.options(reltol=1e-5, abstol=1e-10, vntol=1e-7)
analysis = simulator.transient(step_time=0.05, end_time=190, start_time=0, max_time=0.05)
```

`str(circuit)` 直接保存为 `circuit.cir`，保证网表可复查；求解结果写入 `waveform.csv` 或 `pack_waveform.csv`。

## 8. 实际运行命令

```powershell
conda run -n kaifa_battery python -m scripts.spice_battery_demo
conda run -n kaifa_battery python -m scripts.battery_pack_demo
```

## 9. 真实结果

综合运行编号：`spice_ecm_20261126_122919_f8aaf5`。

单体 SPICE 运行：

| 模型 | SPICE Run ID | 有效点数 | MAE | RMSE | 最大误差 |
| --- | --- | --- | --- | --- | --- |
| Rint | `spice_ecm_20261126_122919_6a56f1` | 3796 | 4.44e-16 V | 4.44e-16 V | 4.44e-16 V |
| 一阶 RC | `spice_ecm_20261126_122919_bbcf7d` | 3796 | 1.78e-7 V | 2.85e-7 V | 9.79e-7 V |
| 二阶 RC | `spice_ecm_20261126_122919_ee3a13` | 3796 | 2.68e-7 V | 3.84e-7 V | 1.23e-6 V |

三串电池组：

| 指标 | 实际值 |
| --- | --- |
| SPICE Run ID | `spice_ecm_20261126_122919_ba990a` |
| 有效点数 | 3798 |
| MAE | 8.00e-7 V |
| 最大误差 | 3.64e-6 V |
| 节点电压求和误差 | 0.0 V |
| 69.95 s 组端电压 | 11.049131 V |

网表与波形：

- `results/spice_ecm/run_spice_ecm_20261126_122919_ee3a13/circuit.cir`
- `results/spice_ecm/run_spice_ecm_20261126_122919_ee3a13/waveform.csv`
- `results/spice_ecm/run_spice_ecm_20261126_122919_ba990a/circuit.cir`
- `results/spice_ecm/run_spice_ecm_20261126_122919_ba990a/pack_waveform.csv`

## 10. 常见错误

- 直接把 Python 生成的电压写入波形文件冒充 SPICE 结果（本阶段禁止）。
- 不排除阶跃转换区就计算最大误差，得到约 40 mV 的假误差。
- 用 1 ms 转换的 SPICE 波形与理想阶跃逐点比较。
- 过紧容差导致不收敛，却把失败解释为模型问题。

## 11. 独立练习

1. 把 PWL 转换时间从 1 ms 改为 10 ms，观察阶跃附近误差。
2. 把 `reltol` 改为 1e-6，复现三串求解失败。
3. 对比 0.05 s 与 0.01 s 输出步长的最大误差。

## 12. 面试题

1. 为什么 SPICE 结果与解析解仍会有微伏级差异？
2. 瞬态仿真中 `max_time` 的作用是什么？
3. 电流源与电压源在电池建模中的选择依据？
4. 如何验证一个 SPICE 网表写对了？
5. 为什么不能用 SPICE 的默认容差直接做微伏级比较？
