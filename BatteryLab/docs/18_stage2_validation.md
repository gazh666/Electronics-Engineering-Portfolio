# 18 第二阶段综合验收与面试题

## 1. 阶段范围

本阶段完成：Rint、一阶 RC、二阶 RC、统一 ECM 求解器、3S1P 电池组、真实 ngspice 电池电路、PyBaMM 交叉验证、CALCE 电流重放、模型误差与能量守恒分析。

本阶段不包含：真实电芯参数辨识、EKF/UKF、SOC 估计、BMS 保护、均衡、硬件测量、Web 页面。这些属于后续阶段。

## 2. 验收环境

```text
Python 3.11.18
numpy 2.4.6
pandas 3.1.1
pybamm 26.11.0.0
PySpice 1.5 + ngspice 34
conda 环境：kaifa_battery
```

## 3. Task 31 实际执行记录

| 命令 | 退出码 |
| --- | --- |
| `python -m scripts.rint_demo` | 0 |
| `python -m scripts.first_order_rc_demo` | 0 |
| `python -m scripts.second_order_rc_demo` | 0 |
| `python -m scripts.battery_pulse_demo` | 0 |
| `python -m scripts.battery_pack_demo` | 0 |
| `python -m scripts.pack_inconsistency_demo` | 0 |
| `python -m scripts.spice_battery_demo` | 0 |
| `python -m scripts.model_comparison_demo` | 0 |
| `python -m scripts.battery_stage2_demo` | 0 |
| `python -m pytest tests -v` | 0 |
| `python -m pip check` | 0 |

- pytest：**118 passed in 24.42 s**（阶段一 37 项 + 阶段二 81 项）。
- `pip check`：`No broken requirements found.`
- 命令日志：`results/stage2/acceptance_commands.log`。

## 4. 验收检查结果

综合运行：`results/stage2/run_stage2_20261126_123052_b15f65/validation_summary.json`，总体 **PASS**。

| 检查项 | 实际值 | 阈值 | 结论 |
| --- | --- | --- | --- |
| RC 解析最大端电压误差 | 4.44e-16 V | ≤1e-6 V | PASS |
| Rint 解析最大端电压误差 | 0.0 V | ≤1e-6 V | PASS |
| 60 s 脉冲 SOC 误差 | 3.33e-13 | ≤1e-8 | PASS |
| 3S 电压求和误差 | 0.0 V | ≤1e-6 V | PASS |
| 3S 一致电芯最大压差 | 0.0 V | ≤1e-9 V | PASS |
| Python 与 ngspice 最大误差 | 3.64e-6 V | ≤1e-3 V | PASS |
| PyBaMM 与自研 ECM 最大差 | 1.14e-5 V | ≤2e-3 V | PASS |
| 一阶/二阶脉冲能量平衡 | 8.0e-6 / 1.25e-5 | ≤1e-3 | PASS |
| 6 工况 × 3 模型能量平衡 | 全部 PASS_RELATIVE | 全部通过 | PASS |

## 5. 关键真实数值

| 项目 | 数值 |
| --- | --- |
| 2A 接入瞬时压降 | 60.000 mV |
| R0 反算 | 0.030000 Ω |
| 一阶脉冲结束电压（69.9 s） | 3.702001 V |
| 二阶脉冲结束电压（69.9 s） | 3.683056 V |
| 60 s 解析值（一阶/二阶） | 3.701991 V / 3.683028 V |
| 一阶恢复时间（±1 mV） | 72.8 s |
| 二阶 120 s 内恢复 | 未达到（NOT_RECOVERED） |
| 3S 开路/接入/60 s 末 | 11.400000 / 11.220000 / 11.049169 V |
| 3S 一致电芯最大压差 | 0.0 V |
| 3S 不一致实验最大压差（SOC 不一致） | 0.407143 V |
| 恒阻 5.7 Ω 初始电流 | 1.968912 A |
| 恒功率 11.111 W 初始电流 | 0.982276 A |
| CALCE 重放 Rint RMSE | 0.299492 V（未辨识基线） |
| CALCE 重放二阶 RC RMSE | 0.333280 V（未辨识基线） |

## 6. 数据来源分类

| 数据 | 来源 |
| --- | --- |
| ECM 波形与指标 | SPICE_DERIVED / custom_ecm_simulation |
| ngspice 波形 | SPICE_SIMULATION |
| PyBaMM 波形 | BEHAVIORAL_MODEL（官方库） |
| CALCE 电流与电压 | 公开实验数据，重放为 UNCALIBRATED_BASELINE |
| 解析参考值 | ANALYTICAL_THEORY |
| pytest / pip check | SOFTWARE_TEST |
| 参数 | PROJECT_SPECIFICATION / educational_assumption |

本项目没有真实硬件实验条件，因此不存在 REAL_HARDWARE_MEASUREMENT 成果。

## 7. 工程局限

1. 所有电芯参数为教学假设，未做参数辨识。
2. OCV-SOC 为教学曲线，不是 CALCE 实测曲线。
3. 二阶模型对真实数据的精度未验证，CALCE 重放仍是未辨识基线。
4. 电池组不含均衡、保护、采样线束与接触电阻。
5. 模型停止事件不代表真实 BMS 保护动作。
6. ngspice 电路为线性 R/C 网络，不含温度、老化、寄生电感与开关器件。
7. 未做 EKF/UKF、SOC 估计、SOH 估计。
8. 未开展任何危险实验或真实充放电测试。

## 8. 第三阶段可复用模块

- `battery_models/ecm_solver.py`：统一求解器与终止事件定位。
- `battery_models/parameters.py`、`ocv_model.py`：参数与查表校验。
- `simulations/load_profiles.py`：真实数据重放与 ZOH 采样。
- `analysis/energy_balance.py`、`battery_losses.py`：能量与损耗核查。
- `storage/result_store.py`：运行编号与证据落盘。
- `circuits/*`：真实 SPICE 网表构造与求解。
- 81 项阶段二测试可作为回归基线。

## 9. 25 道面试题

1. 等效电路模型与电化学模型各自的适用场景是什么？
2. 为什么端电压不等于 OCV？
3. R0 与 RC 极化在时域响应上如何区分？
4. 为什么等效电容可以达到数千法拉？
5. 如何从一次脉冲实验估计 R0、R1、C1？
6. 一阶 RC 与二阶 RC 的选择依据是什么？
7. 为什么二阶模型不一定比一阶更准确？
8. 参数辨识与模型验证为什么要使用不同数据？
9. 库仑计数的误差来源有哪些？
10. OCV-SOC 曲线为什么存在滞回？
11. 如何用静置电压修正 SOC？
12. 为什么串联电池组 Ah 容量不增加？
13. 串联电池组为什么必须监测单体电压？
14. 电芯不一致性有哪些来源？
15. 被动均衡与主动均衡的区别？
16. 如何定义脉冲响应的恢复时间？
17. 采样率不足会如何影响内阻估计？
18. 为什么极化损耗是 V²/R 而不是 I²R？
19. 能量守恒如何在数值仿真中验证？
20. 零阶保持离散与数值积分相比有什么优势？
21. ngspice 的结果为什么与解析解存在微伏级差异？
22. 如何验证一个 SPICE 网表写对了？
23. PyBaMM 交叉验证能证明什么、不能证明什么？
24. 面对公开实验数据误差较大时如何定位原因？
25. 如果要把本阶段模型用于真实 BMS，还缺哪些工作？

## 10. 文档索引

- [09 等效电路总览](09_battery_equivalent_circuit.md)
- [10 Rint](10_rint_model.md)
- [11 一阶 RC](11_first_order_rc_model.md)
- [12 二阶 RC](12_second_order_rc_model.md)
- [13 SOC 与 OCV](13_soc_and_ocv_model.md)
- [14 脉冲响应](14_pulse_response_analysis.md)
- [15 3S1P 电池组](15_3s1p_battery_pack.md)
- [16 真实 SPICE 电路](16_spice_battery_circuit.md)
- [17 模型对比](17_model_comparison.md)
