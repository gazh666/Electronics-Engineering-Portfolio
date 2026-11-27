# 04 电池仿真基线

## 1. 模型层次

| 模型 | 本阶段状态 | 说明 |
| --- | --- | --- |
| SPM | 已实际求解 | 单颗粒模型，忽略电解液浓度梯度，计算快 |
| SPMe | 只阅读 | 增加电解液动力学修正，本阶段未运行 |
| DFN | 只阅读 | 全阶多孔电极模型，计算量大，本阶段未运行 |
| Thevenin | 已实际求解 | 一阶 RC 等效电路，官方教学参数集 |

## 2. 模型参数集

- SPM：实际使用模型默认参数集，经三键比对（容量、上下限电压）匹配 `Marquis2019`；
  额定容量 0.680616 Ah，上限 4.1 V，下限 3.105 V。
- Thevenin：实际匹配 `ECM_Example`，100 Ah 教学电芯，上限 4.2 V，下限 3.2 V，初始 SOC 0.5，默认电流 100 A。

**两者都不是 CALCE INR18650-20R 的辨识参数。**

## 3. 仿真时间与终止事件

| 运行 | 请求时长 | 实际结束 | 终止原因 |
| --- | --- | --- | --- |
| SPM | 3600 s | 3600.000 s | `final time` |
| Thevenin | 1800 s | 1746.100 s | `event: Minimum voltage [V]` |
| Experiment | — | 4515.075 s | `final time` |

Thevenin 未达到 1800 s，是因为 100 A 放电在 1746.1 s 触发 3.2 V 下限，按真实事件终止，未强行补齐。

## 4. SPM 真实结果

运行：`results/pybamm/run_pybamm_20261126_114048_a6a49e`

| 指标 | 数值 |
| --- | --- |
| 求解器 | IDAKLUSolver |
| 参数集 | Marquis2019 (matched_by_nominal_values) |
| 初始电压 | 3.780081 V |
| 结束电压 | 3.191567 V |
| 放电容量 | 0.680616 Ah |
| 放电能量 | 2.468340 Wh |
| 波形点数 | 51 |
| 求解耗时 | 0.1527 s |

文件：`waveform.csv`、`voltage.png`、`current.png`、`summary.json`、`metadata.json`。

## 5. Thevenin 真实结果

运行：`results/pybamm/run_pybamm_20261126_114155_574951`

| 指标 | 数值 |
| --- | --- |
| RC 支路 | 1 |
| R0（t=0） | 4.0459e-4 Ω |
| R1（t=0） | 6.0688e-4 Ω |
| C1（t=0） | 50344.26 F |
| τ1（t=0） | 30.55 s |
| 初始/结束电压 | 3.656055 V / 3.200000 V |
| SOC | 0.500000 → 0.014972 |
| 放电容量 | 48.502780 Ah |
| 放电能量 | 168.669172 Wh |

参数集为教学示例，**不代表任何真实 18650 电芯**，本阶段不做参数辨识。

## 6. 充放电 Experiment 真实结果

运行：`results/pybamm/run_pybamm_20261126_114304_73854e`

实验协议（官方语法，5 步）：

```text
Discharge at C/2 for 20 minutes
Rest for 5 minutes
Charge at C/2 until 4.1 V
Hold at 4.1 V until C/20
Rest for 5 minutes
```

| 指标 | 数值 |
| --- | --- |
| 初始 SOC | 0.9（显式设置） |
| 阶段数 / cycles | 5 / 5 |
| 总时长 | 4515.075 s |
| 电压范围 | 3.786515 – 4.100002 V |
| 电流范围 | −0.340308 – +0.340308 A |
| 放电容量 / 能量 | 0.113436 Ah / 0.433458 Wh |
| 充电容量 / 能量 | 0.194947 Ah / 0.774887 Wh |
| SOC | 0.9 → 1.0 |

阶段划分（按电流方向，左端点归类）：

| 阶段 | 起止 | 时长 |
| --- | --- | --- |
| 放电 | 0 – 1200 s | 1200 s |
| 静置 | 1200 – 1500 s | 300 s |
| 充电（含恒压） | 1500 – 4215.07 s | 2715.07 s |
| 静置 | 4215.07 – 4515.07 s | 300 s |

**注意**：起止 SOC 不同（0.9→1.0），因此充放电容量比（58.19%）不是循环库仑效率，只能作为参考。

## 7. 恒流与恒压

- 恒流放电：`Current [A]` 恒定（SPM 1C = 0.680616 A）。
- 恒压充电：`Hold at 4.1 V until C/20` 阶段电流由 0.34 A 衰减到 C/20 判定值。
- 恒压阶段在波形中与恒流充电连续，按电流符号统一归入“充电”段。

## 8. 代码与命令

```powershell
conda run -n kaifa_battery python -m scripts.pybamm_spm_demo
conda run -n kaifa_battery python -m scripts.pybamm_thevenin_demo
conda run -n kaifa_battery python -m scripts.battery_charge_discharge_demo
```

核心实现：`battery_models/pybamm_backend.py`（`PyBaMMBackend.run / extract_waveform`）、
`analysis/battery_metrics.py`（`summarize_measurement / segment_statistics`）。

## 9. 已知局限

- 只有 SPM 与 Thevenin 两个模型实际运行；SPMe/DFN 未验证。
- 参数集为官方默认/教学值，未与 CALCE 数据做参数辨识。
- 无温度耦合实验（默认等温），`temperature_c` 列在 SPM 中为 null。
- 能量积分使用输出时间点梯形积分；SPM 默认输出点较稀疏（51 点），后续阶段可加密输出。

---

## 面试题（附参考答案要点）

**Q1：SPM 与 DFN 的核心差别？**
A：SPM 用单颗粒代表电极、忽略电解液浓度梯度；DFN 求解电解液浓度与电位分布，精度高但计算量大。

**Q2：为什么等效电路模型更适合 BMS 在线估算？**
A：状态少、计算快、参数可在线辨识；电化学模型精度高但计算量不适合嵌入式实时运行。

**Q3：仿真为什么会在设定时间之前结束？**
A：触发事件（如电压截止）。必须记录真实终止原因，不能强行补齐时间轴。

**Q4：一阶 RC 的 τ=R1C1 物理含义？**
A：极化恢复的时间常数，反映电流突变后电压缓慢回到稳态的快慢。

**Q5：为什么不能把充放电容量比直接叫循环效率？**
A：若起止 SOC 不同，充入与放出的电荷量本身不对等，比值失去效率含义。

**Q6：如何判断参数集是否适用于目标电芯？**
A：核对容量、上下限电压、化学体系与温度范围；最终需用实测数据做参数辨识与验证。
