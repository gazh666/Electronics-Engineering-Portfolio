# 02 PyBaMM 上游项目分析

> 本文所有关于 PyBaMM 能力的描述均来自本机实际安装的 `pybamm 26.11.0.0` 与本地只读源码
> `PyBaMM-main`，不是对文档的推测。

## 1. PyBaMM 是什么

PyBaMM（Python Battery Mathematical Modelling）是一个开源电池模型求解框架：用户用接近数学方程的形式
描述电池的物理过程（锂离子扩散、电荷守恒、电化学反应动力学），框架负责离散化并调用数值求解器。

- 许可证：BSD 3-Clause（`PyBaMM-main\LICENSE.txt`，Copyright (c) 2018, the PyBaMM team）。
- 本地源码：`PyBaMM-main`（monorepo 结构：`packages/pybamm`、`packages/pybammsolvers` 等）。
- 安装包路径：`C:\\Users\\<user>\.conda\envs\kaifa_battery\Lib\site-packages\pybamm`。
- Python 要求：本地 `pyproject.toml` 标注 `requires-python = ">=3.11, <3.16"`。

## 2. PyBaMM 与 ngspice 的区别

| 维度 | PyBaMM | ngspice |
| --- | --- | --- |
| 建模对象 | 电化学/等效电路电池模型（连续介质方程） | 电路拓扑（节点方程） |
| 状态变量 | 固相/液相锂浓度、电位、SOC、温度 | 节点电压、支路电流 |
| 典型分析 | 恒流/恒压充放电、动态工况、老化 | 直流工作点、瞬态、交流小信号 |
| 本项目用途 | 电池本体行为（第三至第七阶段基础） | 采样、保护、充电控制电路（后续阶段） |
| 上游许可证 | BSD-3 | ngspice：按上游发行版许可（本项目只使用 PySpice 安装脚本提供的 64 位 DLL） |

两者在 BatteryLab 中属于不同层次：PyBaMM 描述“电芯”，ngspice 描述“围绕电芯的模拟电路”。
本阶段没有把两者耦合为同一个联合仿真。

## 3. PyBaMM 如何建立电池模型

实际调用链（已验证可运行）：

```python
import pybamm

model = pybamm.lithium_ion.SPM()                 # 选择模型
values = model.default_parameter_values          # 参数集
simulation = pybamm.Simulation(model, parameter_values=values)
solution = simulation.solve([0, 3600])           # 真实数值求解
```

`Solution` 通过变量名字符串取值，例如 `solution["Voltage [V]"].entries`。
本项目在 `battery_models/pybamm_backend.py` 中做统一封装，但模型与求解器仍由 PyBaMM 提供。

## 4. 什么是电化学模型

电化学模型从物质守恒与电荷守恒出发，描述锂离子在正负极颗粒内部的扩散、电解液中的输运以及界面反应。
本阶段实际使用：

- SPM（Single Particle Model）：每个电极用单个球形颗粒代表，忽略电解液浓度梯度，计算量小。
- 默认 SPM 参数集经实际比对为 `Marquis2019`（额定容量 0.680616 Ah，上限 4.1 V，下限 3.105 V）。

SPMe、DFN 属于同一框架内更复杂的模型，本阶段只阅读未运行。

## 5. 什么是等效电路模型

等效电路模型用电压源（OCV）+ 欧姆内阻 + RC 极化网络描述端电压：

V_terminal = OCV(SOC) − I·R0 − Σ V_RC,i

本阶段实际使用 PyBaMM 官方 `pybamm.equivalent_circuit.Thevenin()`：

- 默认参数集匹配 `ECM_Example`（100 Ah 教学示例）；
- `number of rc elements = 1`（一阶 RC）；
- R0、R1、C1 均为随 SOC 变化的函数，实际仿真在 t=0 时求得
  R0 = 4.0459e-4 Ω、R1 = 6.0688e-4 Ω、C1 = 50344.26 F、τ1 = 30.55 s。

该参数集是教学示例，**不是 CALCE INR18650-20R 的辨识结果**。

## 6. 什么是参数集

参数集（ParameterValues）是一组带单位的物理参数，如容量、扩散系数、反应速率常数、截止电压。
PyBaMM 26.11 本地可用参数集共 19 个：`Ai2020、Bonkile2024、Chayambuka2022、Chen2020、Chen2020_composite、
ECM_Example、Ecker2015、Ecker2015_graphite_halfcell、MSMR_Example、Marquis2019、Mohtat2020、NCA_Kim2011、
OKane2022、OKane2022_graphite_SiOx_halfcell、ORegan2022、Prada2013、Ramadass2004、Sulzer2019、Xu2019`。

## 7. 什么是电池状态变量

状态变量是求解器实际积分的量，例如 SPM 中的负/正极颗粒表面与体相锂浓度、电解液电位、温度。
此外还有派生变量（端电压、SOC、C-rate）。本项目输出的波形列：

`time_s, voltage_v, current_a, soc, temperature_c`

其中 SOC 在 Thevenin 模型中是真实状态变量；SPM 默认等温模型不输出电压以外的热状态。

## 8. 什么是数值求解

PyBaMM 把偏微分方程离散为常微分代数方程组，再交给求解器：

- 本机默认求解器：`IDAKLUSolver`（实际输出）；
- 可选求解器包括 `CasadiSolver、ScipySolver、CompositeSolver` 等（`dir(pybamm)` 实测）；
- 事件（如电压截止）由求解器检测，`solution.termination` 记录真实终止原因：
  本阶段实测出现过 `final time` 与 `event: Minimum voltage [V]` 两种。

## 9. 上游提供了哪些能力（本阶段实际用到/验证）

| 能力 | 实际接口 | 本项目用法 |
| --- | --- | --- |
| 模型库 | `pybamm.lithium_ion.SPM` | 恒流放电、CC-CV 实验 |
| 等效电路 | `pybamm.equivalent_circuit.Thevenin` | 一阶 RC 端电压仿真 |
| 参数集 | `pybamm.ParameterValues(name)` | 参数集名称核对 |
| 实验协议 | `pybamm.Experiment([...])` | 放电-静置-充电-恒压-静置五步流程 |
| 求解 | `pybamm.Simulation(...).solve(...)` | 所有仿真 |
| 结果访问 | `solution["Voltage [V]"].entries` | 波形导出与指标计算 |

## 10. BatteryLab 自行实现的应用层功能

1. `battery_models/pybamm_backend.py`：模型创建、参数集校验、初始 SOC、波形提取、元数据记录。
2. `analysis/battery_metrics.py`：容量/能量积分、符号穿越分段积分、SOC 派生、阶段划分。
3. `storage/result_store.py`：运行 ID、配置快照、波形 CSV、JSON（禁止 NaN/Infinity）。
4. `datasets/*`：CALCE 数据下载、解析、质量检查（上游不提供）。
5. `visualization/plots.py`：工程图表。
6. `scripts/*`：可复现实验入口与验收脚本。

## 11. 边界声明

- 电化学求解器、等效电路方程、实验协议解析均为 PyBaMM 上游成果，**不是本人自主开发**。
- 上游源码未被修改，`PyBaMM-main` 仅作只读参考。
- 本阶段没有做参数辨识，因此不能声称“已建立 CALCE 电芯的 PyBaMM 模型”。
