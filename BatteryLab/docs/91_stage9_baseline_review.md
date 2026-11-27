# 91 第九阶段三项目工程基线审查

日期：2026-11-26
阶段：TestLab、PowerLab、BatteryLab 系统级联合仿真与自动化工程验证
定位：**Engineering Prototype Verification — Not Hardware Validated**

本文件只记录**本机实测**的基线事实。凡是本机不存在的工具、接口或数据，均
明确标注，不用推测填充。

## 1. 三项目真实状态

来源：`results/stage9/project_interfaces/verify_interfaces_20261126_172007_79b9ed/cross_project_manifest.json`

| 项目 | 路径 | 存在 | 版本 | 版本控制 | 核心文件缺失 |
| --- | --- | --- | --- | --- | --- |
| TestLab | `TestLab` | 是 | 1.0.0 | Git 仓库（有未提交改动统计） | 无 |
| PowerLab | `PowerLab` | 是 | 无 VERSION 文件 | 非 Git 仓库 | 无 |
| BatteryLab | `BatteryLab` | 是 | 无 VERSION 文件 | 非 Git 仓库 | 无 |

模块规模（`.py` 文件数，本阶段实测）：

| 项目 | 包与模块数 |
| --- | --- |
| TestLab | analysis 5、engine 8、instruments 7；Python 源文件 110 |
| PowerLab | analysis 31、circuits 26、control 11、simulations 14、validation 16 |
| BatteryLab | analysis 33、circuits 22、simulations 13、validation 11、protection 6、battery_models 10、estimation 9、health 6、integration 11、system_models 8 |

## 2. 三项目真实接口

### 2.1 TestLab

- 存在 `engine/result_judge.py`，可用函数：`judge`、`judge_voltage`、`judge_range`、`aggregate_status`；
- **没有**面向外部系统的测量导入接口（`has_external_measurement_import = false`）；
- 因此第九阶段采用"只读导入真实判定函数 + 在 BatteryLab 侧完成数据格式转换"的方式，
  不另写一个判定函数冒充 TestLab；
- 判定调用在 `kaifa` 环境通过子进程执行，并记录 `result_judge.py` 的 SHA-256。

### 2.2 PowerLab

| 项 | 实测值 | 来源 |
| --- | --- | --- |
| 输入电压 | 12.0 V | `configs/nonideal_buck_config.yaml` |
| 输出 | 5.0 V / 2.0 A | 同上 |
| 开关频率 | 100 kHz | 同上 |
| 电感 / DCR | 47 µH / 0.05 Ω | 同上 |
| 电容 / ESR | 100 µF / 0.03 Ω | 同上 |
| 负载 | 2.5 Ω | 同上 |
| 模型变体 | E（Level 1 教学 MOSFET + 非理想二极管） | `configs/closed_loop_config.yaml` |
| 控制器 | kp=0.0585、ki=117.66、抗饱和=back_calculation、含前馈 | `configs/controller_config.yaml` |
| 设计相位裕量 | 62.0° | 同上 |
| 设计带宽 | 57.3 Hz | 同上 |
| 控制周期参数 | end=12 ms、step=25 ns | `configs/closed_loop_config.yaml` |

PowerLab 关键事实：

- 闭环构建器 `build_closed_loop_buck(config)` 把输入源硬编码为理想电压源 `VIN`；
- 闭环求解函数 `run_closed_loop` 只返回内存结果，不写文件；
- 第六阶段参数扫描真实运行记录位于 `results/hardening/stage6_optimization/sweep.json`，
  基准为 47 µH/100 µF，选定候选为 68 µH/330 µF（combo_C）。

### 2.3 BatteryLab

| 项 | 实测值 | 来源 |
| --- | --- | --- |
| 电池模型 | 3S1P 一阶 RC ECM（第三阶段辨识） | `results/identification/run_identification_20261126_125603_622eba/identified_parameters.csv` |
| OCV 曲线 | 0–1 SOC 覆盖 | `results/ocv/run_ocv_20261126_124813_24e8d1/ocv_soc.csv` |
| 辨识 SOC 有效区间 | 0.0106–0.5068 | 辨识结果记录 |
| 保护阈值 | 第五阶段工程配置 | `configs/protection_config.yaml` |
| 第八阶段基线 | 10 PASS / 1 FAIL / 9 BLOCKED | `docs/90_stage8_final_validation.md` |
| 第八阶段后测试 | 480 passed | 同上 |

R0 = 77.07 mΩ、Rp = 22.84 mΩ、Cp = 788.6 F、容量 2.0281 Ah（单节，25 ℃）。

## 3. 接口风险与对策

| 风险 | 事实 | 对策 |
| --- | --- | --- |
| TestLab 无外部测量导入 | 已核实 | 只读导入 `engine.result_judge`，保留源码哈希与调用日志 |
| PowerLab 输入源硬编码 | 已核实 | 在 `kaifa_power` 环境中调用其真实构建器，移除 `VIN` 元件后串入电池 ECM；仅置 0 V 会造成低阻短路，已实测复现并放弃 |
| PowerLab 非 Git 仓库 | 已核实 | 用源码哈希树证明未被修改 |
| BatteryLab 非 Git 仓库 | 已核实 | 同上 |
| KiCad 仍未安装 | 第八阶段结论延续 | 第九阶段不涉及原理图/PCB，不将第八阶段 BLOCKED 改写为通过 |

## 4. 本阶段不宣称的内容

1. 不宣称任何硬件已制板、焊接、上电或实测；
2. 不宣称 TestLab 拥有系统级导入接口；
3. 不宣称 PowerLab 教学 MOSFET/二极管是商业器件模型；
4. 不宣称 1 s 步长的长期模型能证明微秒级保护响应；
5. 不宣称第八阶段 9 项 BLOCKED 已解除。
