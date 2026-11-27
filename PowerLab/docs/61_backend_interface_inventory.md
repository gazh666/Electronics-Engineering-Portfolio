# 61 后端接口盘点（第九阶段）

本文件记录 Web 平台调用到的既有后端接口。第九阶段只新增任务编排、结果索引与页面层，
**没有**重新实现 SPICE 求解、性能指标、统计分析或理论公式。

## 1. 调用原则

1. 页面只调用 `ui.service`、`ui.form_validation`、`ui.export_service`，不直接 import 仿真模块。
2. 任务管理器只接受白名单任务类型，经 `jobs.registry.resolve_handler` 静态映射到处理函数。
3. 处理函数在独立工作进程中运行，调用既有模块并写入新的运行目录。
4. 用户输入只作为数值参数；模块名、函数名、文件路径不会被动态导入或执行。
5. 所有 `data_source` 与证据等级由后端显式写入结果文件，页面不得自行改写。

## 2. 仿真与电路构建接口

| 模块 | 入口 | 用途 | 输入 | 输出 |
| --- | --- | --- | --- | --- |
| `simulations.runner` | `SimulationRunner.run_operating_point()` | 电阻分压工作点 | 电路对象 | `SimulationResult` |
| `simulations.runner` | `SimulationRunner.run_transient()` | RC/RL/RLC 瞬态 | 电路对象、`step_s`、`end_s` | `SimulationResult` |
| `simulations.buck_runner` | `run_buck_transient()` | 近理想开关 Buck | 参数、结束时间、步长 | `SimulationResult` |
| `simulations.nonideal_buck_runner` | `run_nonideal_buck_transient()` | 非理想 MOSFET Buck | 配置、变体 A–E | `SimulationResult` |
| `simulations.closed_loop_runner` | `run_closed_loop_with_fallback()` | 闭环开关级仿真 | `ClosedLoopConfig`、模式 | 闭环运行对象 |
| `simulations.closed_loop_runner` | `save_closed_loop_run()` | 保存闭环结果 | 运行对象、根目录 | 运行目录 `Path` |
| `circuits.divider` | `build_voltage_divider()` / `theoretical_output_voltage()` | 分压电路与理论值 | 电压、电阻 | 电路对象 / 理论电压 |
| `circuits.rc_circuit` | `build_rc_transient()` | RC 电路 | 输入、R、C | 电路对象 |
| `circuits.rl_circuit` | `build_rl_transient()` | RL 电路 | 输入、R、L | 电路对象 |
| `circuits.rlc_circuit` | `build_rlc_transient()` | RLC 电路 | 输入、R、L、C | 电路对象 |
| `circuits.buck_config` | `load_buck_config()` | 读取近理想 Buck 配置 | — | 参数对象 |
| `circuits.nonideal_config` | `load_nonideal_buck_config()` | 读取非理想 Buck 配置 | — | `NonidealBuckConfig` |
| `circuits.closed_loop_config` | `load_closed_loop_config()` | 读取闭环配置 | — | `ClosedLoopConfig` |

闭环配置通过 `with_named_load()` / `with_named_line()` 选择
`configs/disturbance_cases.yaml` 中已定义的负载与输入工况。

## 3. 分析与验证接口

| 模块 | 入口 | 用途 |
| --- | --- | --- |
| `analysis.performance_analyzer` | `PerformanceAnalyzer.analyze()` | 由真实波形计算输出均值、纹波、效率、电流纹波、开关能量等 |
| `analysis.performance_judge` | `summarize_checks()` | 汇总工程判定（PASS/FAIL/NOT_RESOLVED/NOT_VERIFIED） |
| `analysis.time_domain` | `time_weighted_mean` / `minimum_value` / `maximum_value` / `peak_to_peak` | 稳态窗口统计 |
| `validation.convergence_analysis` | `TimestepPoint` / `analyze_convergence()` | 时间步收敛判定 |
| `validation.monte_carlo` | `generate_samples()` / `sampling_provenance()` / `write_samples_csv()` | 假设分布抽样与来源记录 |
| `validation.tolerance_analysis` | `ParameterTolerance` / `apply_parameters()` / `load_component_tolerances()` | 容差应用 |
| `validation.statistical_analysis` | `summarize_samples()` | 样本统计汇总 |

工程判定与任务执行状态严格分离：任务 `COMPLETED` 只表示求解完成，性能是否 PASS
由 `PerformanceAnalyzer` 与判定配置决定。

## 4. 存储接口

| 模块 | 入口 | 用途 |
| --- | --- | --- |
| `storage.result_store` | `ResultStore.save_result()` | 保存波形、网表、配置快照、摘要、附加表 |
| `storage.result_store` | `new_run_id()` / `write_json()` / `write_dataframe()` / `save_config_snapshot()` | 运行编号与原子写工具 |
| `storage.result_repository` | `discover_run_dirs()` / `locate_run()` / `load_waveform()` / `load_run_bundle()` | 只读扫描与按需读取波形 |
| `storage.run_index` | `build_index()` / `save_index()` / `load_index()` / `get_index()` | 元数据索引（可重建） |

Web 任务的新结果写入 `results/web_runs/run_<run_id>/`，历史目录只读。

## 5. 任务类型与处理函数

| 任务类型 | 处理函数 | 真实计算 |
| --- | --- | --- |
| `circuit_simulation` | `handle_circuit_simulation` | 分压/RC/RL/RLC/近理想 Buck/非理想 Buck |
| `performance_analysis` | `handle_performance_analysis` | 读取既有波形，重新运行第五阶段性能分析（派生结果） |
| `parameter_sweep` | `handle_parameter_sweep` | 每个扫描点一次真实非理想 Buck 瞬态 |
| `closed_loop_experiment` | `handle_closed_loop_experiment` | 真实闭环开关级瞬态 |
| `numerical_validation` | `handle_numerical_validation` | 多时间步真实求解 + 收敛判定 |
| `monte_carlo` | `handle_monte_carlo` | 假设容差抽样，每个样本一次真实瞬态 |

## 6. 明确未使用的接口

- 不直接调用 PySpice/ngspice 的底层 API；全部经既有 runner。
- 不在 Web 进程内启动 `ngspice` 可执行程序；求解发生在工作进程内。
- 不读取/修改 `TestLab`、`PySpice-master` 或任何历史结果目录。
- 不提供任意脚本执行、任意模块导入或任意路径读取接口。
