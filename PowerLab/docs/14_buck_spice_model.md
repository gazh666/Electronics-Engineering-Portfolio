# 14 Buck 的 SPICE 模型与网表

本文逐行解释第三阶段真实生成的 Buck 网表，并给出对应的 Python 代码位置。

## 1. 实际网表

来自默认运行 `results/buck/run_20261125_115042_d4dd77aa/circuit.cir`：

```text
.title Basic Asynchronous Buck
VIN vin 0 12.0
VPWM gate 0 DC 0V PULSE(0.0V 5.0V 1e-05s 2e-08s 2e-08s 4.146666666666667e-06s 1e-05s)
S1 vin sw gate 0 SWMOD
DFREE 0 sw DFREE
VSENSE sw lx 0.0
L1 lx out 4.7e-05
C1 out 0 0.0001
RLOAD out 0 2.5
.model SWMOD SW (ROFF=1000000.0 RON=0.001 VH=0.1 VT=2.5)
.model DFREE D (IS=1e-06 N=1.0 RS=0.001)
.options TEMP = 25.0C
.options TNOM = 25.0C
.tran 1e-07s 0.005s 0.0s 5e-08s
.end
```

这不是手工写死的字符串，而是由 PySpice 根据参数对象生成，再写入运行目录。

## 2. 逐行解释

| 行 | 含义 |
| --- | --- |
| `.title` | 电路标题，来自 `BuckParameters.circuit_name` |
| `VIN vin 0 12.0` | 12 V 输入直流源，`vin` 对地 |
| `VPWM gate 0 DC 0V PULSE(...)` | 0/5 V PWM 驱动 `gate`，参数见 `docs/13` |
| `S1 vin sw gate 0 SWMOD` | 电压控制开关：vin→sw，栅极 gate，模型 SWMOD |
| `DFREE 0 sw DFREE` | 续流二极管：阳极 0（GND），阴极 sw |
| `VSENSE sw lx 0.0` | 0 V 串联电压源，用于测量电感支路电流 |
| `L1 lx out 4.7e-05` | 47 µH 电感，lx→out |
| `C1 out 0 0.0001` | 100 µF 输出电容，out 对地 |
| `RLOAD out 0 2.5` | 2.5 Ω 恒阻负载 |
| `.model SWMOD SW (...)` | 开关模型参数 |
| `.model DFREE D (...)` | 二极管模型参数 |
| `.options TEMP/TNOM` | 仿真温度 25 °C |
| `.tran 1e-07s 0.005s 0.0s 5e-08s` | 瞬态分析命令 |
| `.end` | 网表结束 |

### 2.1 瞬态命令

```
.tran <输出步长> <结束时间> <开始时间> <最大内部步长>
.tran 1e-07s     0.005s     0.0s       5e-08s
```

- 输出步长 100 ns：结果 CSV 的名义采样间隔；
- 结束时间 5 ms：包含启动与约 500 个开关周期；
- 开始时间 0：保存从 0 时刻开始的完整启动波形；
- 最大内部步长 50 ns：保证每个 10 µs 周期至少 200 个内部步长。

ngspice 实际会自适应调整内部步长，因此输出时间轴是**非均匀**的
（默认工况 118512 点，最小步长约 2.27e-10 s，最大步长 5e-8 s）。

## 3. 元件连接关系

```
VIN(vin→GND) ─ S1(vin→sw, gate) ─ VSENSE(sw→lx) ─ L1(lx→out) ─┬─ C1(out→GND)
                                                                ├─ RLOAD(out→GND)
DFREE(GND→sw) 与 S1 组成开关-续流对
```

节点命名常量在 [buck.py](file:///PowerLab/circuits/buck.py) 中：

- `NODE_VIN = "vin"`
- `NODE_GATE = "gate"`
- `NODE_SWITCH = "sw"`
- `NODE_INDUCTOR = "lx"`
- `NODE_OUTPUT = "out"`
- `BRANCH_INPUT = "vin"`
- `BRANCH_SENSE = "vsense"`

## 4. 代码位置

| 功能 | 文件与函数 |
| --- | --- |
| 参数数据类与 YAML 加载 | [buck_config.py](file:///PowerLab/circuits/buck_config.py) `BuckConfig`、`BuckParameters`、`load_buck_config()` |
| PWM 参数 | [pwm.py](file:///PowerLab/circuits/pwm.py) `PWMParameters` |
| 开关/二极管模型 | [switch_models.py](file:///PowerLab/circuits/switch_models.py) `add_switch_model()`、`add_diode_model()` |
| 拓扑构建 | [buck.py](file:///PowerLab/circuits/buck.py) `build_buck_circuit()`、`build_buck_from_parameters()` |
| 瞬态执行与步长统计 | [buck_runner.py](file:///PowerLab/simulations/buck_runner.py) `run_buck_transient()`、`time_step_statistics()` |
| 通用瞬态执行器 | [runner.py](file:///PowerLab/simulations/runner.py) `SimulationRunner.run_transient()` |
| 分析命令生成 | [backend.py](file:///PowerLab/simulations/backend.py) `analysis_command()` |

## 5. 结果文件

每次运行写入新的 `results/buck/run_<timestamp>_<uuid8>/`：

| 文件 | 内容 |
| --- | --- |
| `circuit.cir` | 实际网表 |
| `metadata.json` | 求解器版本、后端、温度、耗时、步长统计 |
| `waveform.csv` | 全部真实波形（约 15 MB，默认 5 ms 工况） |
| `steady_state_waveform.csv` | 稳态窗口内的波形子集 |
| `theoretical_results.json` | 理想理论（`analytical_theory`） |
| `spice_results.json` | SPICE 结果（`spice_simulation`） |
| `comparison.json` / `comparison.csv` | 理论与仿真对照（`comparison`） |
| `validation.json` | 逐项验证报告 |
| `config_snapshot.yaml` | 参数快照 |
| `plots/*.png` | 波形图 |

理论、SPICE、对比三类数据在 JSON 中通过 `data_source` 字段显式区分，不会互相覆盖。
