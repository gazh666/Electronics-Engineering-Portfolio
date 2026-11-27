# 33 差分放大器设计

## 1. 电路拓扑

```text
Vhigh ──R3──┬── V+ ──┐
            │        │
           R4        │
            │      [OpAmp] ── Vout
           Vref      │
                     │
Vlow  ──R1──┬── V− ──┘
            │
           R2
            │
           Vout
```

四电阻差分放大器：R1/R2 在反相臂，R3/R4 在同相臂。

## 2. 专业原理

- 理想运放 + 负反馈 → 虚短 `V+=V−`、虚断 `I+=I−=0`。
- 当 `R2/R1 = R4/R3` 时，共模被完全抵消，只剩差模增益。
- 实际电阻失配会把共模转成差模误差，这是高共模电池采集的主要误差源。
- 运放本身还有输入失调、有限开环增益、有限 CMRR、输出摆幅与共模范围限制。

## 3. 公式推导

节点方程：

```text
V+ = (Vhigh*R4 + Vref*R3)/(R3+R4)
V− = (Vlow*R2 + Vout*R1)/(R1+R2)
V+ = V−
```

解得：

```text
Vout = (1+R2/R1)*(Vhigh*R4+Vref*R3)/(R3+R4) - (R2/R1)*Vlow
```

匹配时 `R2/R1=R4/R3=k`：

```text
Vout = Vref + k*(Vhigh−Vlow)
```

共模误差的一阶近似：

```text
ΔVout ≈ Vcm * (R4/R3 − R2/R1)/(1+R2/R1)
```

## 4. 变量及单位

| 量 | 数值 | 单位 |
| --- | --- | --- |
| R1/R3 | 100 kΩ | Ω |
| R2/R4 | 50 kΩ | Ω |
| k | 0.5 | V/V |
| Vref | 0.2 | V |
| 供电 | 5.0 | V |
| 共模范围（电池节点） | 1.8–9.7 | V |
| 共模范围（运放引脚） | 1.35–3.42 | V |

## 5. 实际器件参数来源

- 三层模型：
  - A 理想运放：VCVS，开环增益 1e6；
  - B 教学非理想：有限增益、tanh 饱和、失调、GBW；
  - C 规格参考模型：INA240A2 行为模型（仅电流通道），**不是商业运放内部电路**。
- 电阻容差：0.1% 与 1% 教学假设。
- 没有任何商业运放 SPICE 模型被声称为真实器件模型。

## 6. 实际核心源码

- `circuits/differential_amplifier.py`
- `circuits/opamp_models.py`
- `sensing/voltage_decoder.py`
- `circuits/spice_utils.py`

## 7. 函数名称及行号

| 名称 | 位置 | 作用 |
| --- | --- | --- |
| `DifferentialAmplifierConfig` | `circuits/differential_amplifier.py:26` | 电阻/参考/供电配置 |
| `ideal_opamp_spec` | `circuits/differential_amplifier.py:82` | 理想运放 |
| `teaching_opamp_spec` | `circuits/differential_amplifier.py:94` | 教学非理想运放 |
| `add_opamp` | `circuits/opamp_models.py:59` | 把运放加入网表 |
| `solve_differential` | `circuits/differential_amplifier.py:134` | 单点工作点 |
| `sweep_differential_fast` | `circuits/differential_amplifier.py:329` | 差模扫描 |
| `sweep_common_mode_fast` | `circuits/differential_amplifier.py:351` | 共模扫描 |
| `resistor_mismatch_values` | `circuits/differential_amplifier.py:239` | 失配组合 |
| `cmrr_db` | `circuits/differential_amplifier.py:225` | CMRR 计算 |

## 8. 核心代码逐行解释

```python
circuit.B("hi", "hi", circuit.gnd, v="V(cm)+0.5*V(dctrl)")   # 同相端共模+半差模
circuit.B("lo", "lo", circuit.gnd, v="V(cm)-0.5*V(dctrl)")   # 反相端共模-半差模
data = run_dc_sweep(circuit, source_name="Vdctrl", ...)        # 扫描差模
```

- 用两个行为电压源把“共模”和“差模”解耦，避免把电池节点共模误当运放共模；
- `Vdctrl` 从 −5 V 扫到 +5 V，得到差模传输曲线；
- 共模扫描固定差模，扫 `Vcm`，得到 `Acm` 与 CMRR。

## 9. 实际运行命令

```powershell
conda run -n kaifa_battery python -m scripts.differential_amplifier_demo
```

## 10. 实际图表及原始结果路径

Run ID：`sensing_20261126_135218_cb8cf7`

- `results/sensing/run_sensing_20261126_135218_cb8cf7/plots/04_diff_amp_transfer.png`
- `results/sensing/run_sensing_20261126_135218_cb8cf7/plots/05_diff_amp_common_mode_sweep.png`
- `results/sensing/run_sensing_20261126_135218_cb8cf7/plots/06_resistor_mismatch_cell_error.png`

实际结果：

| 指标 | 数值 |
| --- | --- |
| 差模增益 Ad（SPICE） | 0.49999925 |
| 理论 Ad | 0.50000000 |
| 共模增益 Acm | −5.82×10⁻¹¹ |
| CMRR（数值） | 198.68 dB |
| CMRR 可验证下界 | **133.98 dB** |
| 差模理论与 SPICE 最大误差 | **0.003488 mV** |
| 真实 SPICE 求解 | 8 次 |

共模扫描（电池节点 0–8 V，差模固定）：

| 电池共模 | 运放引脚共模 | 输出 |
| --- | --- | --- |
| 0 V | 0.750 V | 2.049997 V |
| 2 V | 1.417 V | 2.049997 V |
| 4 V | 2.083 V | 2.049997 V |
| 6 V | 2.750 V | 2.049997 V |
| 8 V | 3.417 V | 2.049997 V |

电阻失配（真实 SPICE 提取 Ad/Acm/失调后线性外推，不是逐点 SPICE）：

| 容差 | cell1 (3.6 V) | cell2 (3.8 V) | cell3 (4.0 V) |
| --- | --- | --- | --- |
| 1% | 8.126 mV | 16.079 mV | 25.071 mV |
| 0.1% | 1.639 mV | 2.825 mV | 4.163 mV |

## 11. 常见错误

1. 认为理想运放 CMRR 无限；实际只报告可验证下界 133.98 dB。
2. 把 198.68 dB 当真实芯片 CMRR；它是匹配模型的数值结果。
3. 忽略电阻失配随共模增大：cell3 误差约为 cell1 的 3 倍。
4. 把 1% 电阻直接用于 10 mV 目标而不做校准。
5. 认为虚短在所有工况成立；饱和/超共模时必须用 SPICE 或非线性模型。

## 12. 独立学习练习

1. 固定 R1/R2，改变 R3 的 ±1%，推导共模误差方向。
2. 把 0.1% 电阻结果与误差预算的 22.679 mV 对比，解释差异。
3. 将供电从 5 V 降到 3.3 V，观察顶部通道是否先饱和。

## 13. 面试问题

1. 推导四电阻差分放大器公式。
2. 电阻匹配如何影响 CMRR？
3. 为什么高共模下电阻失配误差更大？
4. 运放输入共模范围与输出摆幅有什么区别？
5. 理想运放模型能验证什么，不能验证什么？
