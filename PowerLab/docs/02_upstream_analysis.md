# 02 原始开源项目分析（PySpice 1.5 + ngspice）

> 依据：本机实际安装的 PySpice 1.5 包、参考源码 `PySpice-master`
> 与一次真实分压/RC 求解结果。未使用记忆中的接口冒充实际代码。

## 1. PySpice 是什么

PySpice 是一个 Python 电路仿真前端库：用 Python 描述电路、生成 SPICE 网表、调用
ngspice 求解，并把结果转成 Python/NumPy 可处理的对象。它本身不是求解器。

- 版本：`PySpice.__version__ = '1.5'`（`PySpice/__init__.py` L23）
- 许可证：GNU GPL v3（`LICENSE.txt`、`GPL-V3.0.txt`）
- 官方文档：<https://pyspice.fabrice-salvaire.fr/>
- 源码参考：本地 `PySpice-master`；该目录没有 `.git`，无法读取 commit（NOT_VERIFIED）

## 2. ngspice 是什么

ngspice 是开源的 SPICE 电路仿真器（C 实现），负责数值求解。PySpice 通过共享库或
子进程把网表交给它。本机实际使用的是 64 位共享库 `ngspice-34.dll`。

## 3. 两者的区别

| 维度 | PySpice | ngspice |
| --- | --- | --- |
| 角色 | Python 前端 / 网表构建 / 结果封装 | 数值求解引擎 |
| 语言 | Python | C |
| 是否懂电路方程 | 不懂，只负责表达与调用 | 懂，负责建立并求解方程 |
| 本项目是否修改源码 | 否 | 否 |
| 本机版本 | 1.5 | ngspice-34（DLL 文件名） |

## 4. Python 如何建立电路

```python
from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import u_V, u_Ohm

circuit = Circuit("Voltage Divider")
circuit.V("input", "vin", circuit.gnd, 12 @ u_V)
circuit.R(1, "vin", "out", 1_000 @ u_Ohm)
circuit.R(2, "out", circuit.gnd, 1_000 @ u_Ohm)
```

`Circuit` 继承自 `Netlist`（`PySpice/Spice/Netlist.py` L1129），提供 `V`、`R`、`C`、
`PulseVoltageSource` 等元件工厂方法；`circuit.gnd` 就是 SPICE 的节点 `0`。

## 5. Circuit 类的作用

- 保存标题、节点、元件与分析配置；
- 生成 SPICE 网表文本（`str(circuit)`）；
- 通过 `Circuit.simulator()`（L1291）创建绑定该网表的仿真器；
- 不负责数值求解，也不保存历史运行结果。

## 6. 节点与元件的定义方式

| 元件 | PySpice 调用 | 生成网表 | 含义 |
| --- | --- | --- | --- |
| 直流电压源 | `circuit.V("input", "vin", gnd, 12@u_V)` | `Vinput vin 0 12.0V` | vin 对地 12 V |
| 电阻 | `circuit.R(1, "vin", "out", 1@u_kOhm)` | `R1 vin out 1000.0Ohm` | vin–out 之间 1 kΩ |
| 电容 | `circuit.C(1, "out", gnd, 1e-6)` | `C1 out 0 1e-06` | out 对地 1 μF |
| 脉冲源 | `circuit.PulseVoltageSource(...)` | `PULSE(0V 5.0V 0s 1e-06s ...)` | RC 充电激励 |

单位后缀（`u_V`、`u_kOhm`）来自 `PySpice.Unit`，只影响网表数值表达，不改变物理量。

## 7. SPICE 网表是什么

网表是电路的纯文本描述：标题、元件行、分析命令、`.end`。本项目实际保存的分压网表：

```spice
.title Voltage Divider
Vinput vin 0 12.0V
R1 vin out 1000.0Ohm
R2 out 0 1000.0Ohm
```

RC 实际网表：

```spice
.title RC Charging
Vinput vin 0 DC 0V PULSE(0V 5.0V 0s 1e-06s 1e-06s 0.02s 0.04s)
R1 vin out 1000.0
C1 out 0 1e-06
```

说明：`str(circuit)` 只包含拓扑；`.op` / `.tran` 由 PySpice 在调用分析时追加并送入
ngspice，因此保存的 `netlist.cir` 里看不到分析指令。

## 8. 仿真器如何接收网表

`circuit.simulator(temperature=25, nominal_temperature=25)` 返回仿真器对象。PySpice
把 Circuit 序列化为 ngspice 能识别的网表，通过共享库 API 送入求解器。本机使用
`PySpice/Spice/NgSpice/Shared.py` 的 CFFI 接口（L92 导入 `cffi.FFI`，L539
`ffi.dlopen(self.library_path)`）。

## 9. 仿真结果如何返回 Python

- 工作点：`operating_point["out"][0]` 取节点电压，返回可转 `float` 的数值；
- 瞬态：`analysis.time`、`analysis["vin"]`、`analysis["out"]` 返回类数组对象，
  用 `numpy.asarray(..., dtype=float)` 转成 NumPy 数组；
- PySpice 不做工程判定，PASS/FAIL、误差、RMSE 都由应用层计算。

## 10. 直流工作点分析是什么

求电路在直流稳态下的节点电压与支路电流：电容视为开路、电感视为短路，解非线性
代数方程。本项目用于分压电路，`simulator.operating_point()`。

## 11. 瞬态分析是什么

在时间轴上逐步积分，求节点电压随时间的变化。本项目用于 RC 充电：
`simulator.transient(step_time=10e-6, end_time=6e-3)`。ngspice 会自适应调整内部
时间步，所以实际采样点（619）不等于 `end/step + 1`。

## 12. 本项目采用的实际仿真后端

| 项目 | 实际值 |
| --- | --- |
| 前端 | PySpice 1.5 |
| 接口 | `NgSpice.Shared`（CFFI 共享库） |
| 求解器 | ngspice-34 64 位 DLL |
| DLL 路径 | `...\site-packages\PySpice\Spice\NgSpice\Spice64_dll\dll-vs\ngspice-34.dll` |
| 子进程 | 未使用 |
| 数据标签 | `spice_simulation` |

## 13. 原始项目提供哪些能力

- 电路拓扑描述与网表生成；
- 单位系统与元件参数表达；
- 工作点、直流扫描、交流小信号、瞬态等分析；
- 结果封装为 NumPy 数组、原始文件读取、绘图辅助；
- 子电路、器件模型与多种 ngspice 后端接入方式；
- 示例与文档（`examples/`、`doc/`）。

## 14. PowerLab 计划自主扩展哪些能力

第一阶段已实现：

- YAML 配置驱动（`configs/simulation.yaml`）；
- 唯一运行目录、网表/结果/环境快照落盘；
- 工程指标：绝对/相对误差、检查点电压、最大误差、RMSE；
- 输入校验（有限性、正负、时间严格递增）；
- 22 项 Pytest，其中包含真实 ngspice 集成测试；
- 环境探针与可复现文档。

后续阶段计划（尚未开发）：Buck 电路建模、开关波形、器件参数扫描、输出纹波、
功率与效率、负载瞬态、电源工程数据分析、Web 界面与 TestLab 数据接入。

## 15. 实际软件版本与许可证

| 软件 | 版本 | 许可证 | 状态 |
| --- | --- | --- | --- |
| PySpice | 1.5 | GPL v3（`LICENSE.txt`） | 已核对 |
| ngspice | 34（`ngspice-34.dll`） | 以官方发行包为准 | 精确许可证版本 NOT_VERIFIED |
| Python | 3.11.18 | PSF | 已核对 |
| NumPy | 1.26.4 | BSD-3-Clause | 已安装 |
| SciPy | 1.17.1 | BSD-3-Clause | 已安装 |
| Matplotlib | 3.11.2 | PSF-based | 已安装 |
| pandas | 3.0.6 | BSD-3-Clause | 已安装 |

本机 ngspice DLL 发行包未附带独立 LICENSE 文件，因此不把“GPL 某版本”写成确定事实。
