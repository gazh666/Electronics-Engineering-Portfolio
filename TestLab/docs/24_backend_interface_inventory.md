# 24 后端接口盘点（第九阶段基线）

本文件记录第九阶段 Web 平台开发前，对现有代码的实际盘点结果。
所有结论来自源码阅读与实测命令，不依赖推测。

## 1. 环境与基线

| 项目 | 实测值 |
| --- | --- |
| 工作目录 | `TestLab` |
| 解释器 | `C:\\Users\\<user>\.conda\envs\kaifa\python.exe` |
| Python | 3.11.18 |
| streamlit / plotly / pandas | 1.67.0 / 7.1.0 / 3.1.1 |
| `pip check` | `No broken requirements found.` |
| 阶段八完成后 pytest | `465 passed`（`python -m pytest tests -q`） |

## 2. 分层与依赖方向

```text
ui/（第九阶段新增）
  └─> engine / bench / analysis / instruments / models / reliability / storage

engine/    编排、判定、故障注入；不拼接 SCPI
bench/     读仪器设置 -> DUT 模型 -> 带来源标签测量
analysis/  指标公式、数据质量、统计；不控制仪器
instruments/ SCPI 收发与参数校验；不含业务判定
models/    VirtualDUT 数学行为模型；不 import pyvisa
reliability/ 故障注入、重试、事件日志、可靠性统计
storage/   JSONL/CSV 运行目录与 SQLite 历史
```

UI 层只允许调用上述模块，不复制 DUT 公式、限值判定或 SCPI 字符串。

## 3. 仪器层

### 3.1 `InstrumentManager`

路径：`instruments/manager.py`

- 构造：`InstrumentManager(config_path)`；`open()/close()` 或 `with` 上下文。
- `ROLE_KEYWORDS`：`psu -> PS001`、`dmm -> DMM001`、`load -> LOAD001`。
- `discover() -> list[str]`：返回当前后端发现的资源名。
- `get_power_supply()` / `get_multimeter()` / `get_electronic_load()`：
  重复调用返回同一驱动对象。
- `open_device(serial)` / `close_device(serial)`。
- 同一 YAML 进程内只允许一个打开的 Manager；关闭幂等。
- `close()` 会先关闭负载输入、电源输出，再释放资源。

### 3.2 驱动 API

| 设备 | 方法 |
| --- | --- |
| `PowerSupply` | `identify()`、`set_voltage/get_voltage`、`set_current/get_current`、`set_output/get_output` |
| `VirtualMultimeter` | `identify()`、`measure_voltage/measure_current/measure_resistance`、`read_dc_voltage(true_value)` |
| `ElectronicLoad` | `identify()`、`set_mode/get_mode`、`set_current/get_current`、`set_input/get_input`、`safe_shutdown()` |
| `BaseInstrument` | `connected`、`session_invalid`、`write/query/query_float`、`close` |

数据来源约定：

- 仪器设定/回读：`pyvisa-sim SCPI`
- DMM 原始 SCPI 读数是固定模拟值：`static_mock`
- 模型测量：`behavioral_model`
- 故障注入视图：`fault_injected_model`

## 4. 数据桥接与测试台

路径：`bench/virtual_test_bench.py`、`engine/dut_bridge.py`

- `VirtualTestBench(manager, dut)`：
  - 构造时获取 `psu` 与 `load`；
  - `read_snapshot()` -> `BridgeReading`；
  - `read_state()` -> `DUTResult`，每次重新读取 SCPI，不缓存；
  - `get_model_measurements()` / `get_static_mock_measurements()`。
- `DutDataBridge.acquire()` 显式读取 PSU `VOLT?/CURR?/OUTP?` 与
  ELoad `CURR?/MODE?/INP?`，再调用 `VirtualDUT.calculate()`。
- PyVISA-sim 多台虚拟仪器不共享物理状态，UI 不能假设负载拉载会改变电源回读。

## 5. 用例、方案与执行引擎

### 5.1 加载器

路径：`engine/case_loader.py`

- `load_test_cases(path) -> list[TestCase]`：严格校验未知字段、类型、范围。
- `load_test_suites(path, case_ids) -> list[TestSuite]`：只引用用例编号。
- `configs/test_cases.yaml`：12 条普通用例（TC001–TC012）。
- `configs/test_suites.yaml`：SUITE-SMOKE / SUITE-PROTECTION /
  SUITE-REGRESSION / SUITE005。
- `configs/reliability_cases.yaml`：RC-RELIABILITY、RC-RELIABILITY-B。

### 5.2 `TestRunner`

路径：`engine/test_runner.py`

- 构造：`TestRunner(manager, bench, analyzer, *, fault_scenarios=None,
  retry_policy=None, fault_logger=None)`。
- `configure_reliability(scenarios, retry_policy=None, fault_logger=None)`：
  显式启用故障注入，默认关闭。
- `run_case(case, run_id, execution_index=0) -> TestResult`：
  设置工况 -> 回读校验 -> 模型读数 -> 数据质量 -> 判定 -> 清理。
- 清理失败会将结果标 ERROR 并置 `cleanup_failed=True`。
- `TestResult` 关键字段：`status`、`raw_data`、`metrics`、`checks`、
  `duration_ms`、`fault_injected`、`fault_events`、`retry_count`、
  `recovered`、`error_category`、`cleanup_status`、`original_model_data`、
  `observed_data`。

### 5.3 `SuiteRunner`

路径：`engine/suite_runner.py`

- 构造：`SuiteRunner(test_runner, result_store=None, sqlite_store=None)`。
- `run_suite(suite, cases, progress_callback=None, run_id=None, *,
  fault_scenarios=None, retry_policy=None, fault_logger=None)
  -> SuiteRunResult`。
- 进度回调签名：`callback(current: int, total: int, result: TestResult)`，
  在结果持久化之后调用。
- `stop_on_fail` / `stop_on_error`；清理失败强制停止；未执行用例补 SKIP。
- `SuiteRunResult.summary` 由 `summarize_results()` 计算，包含
  `pass_rate`、`completion_rate`、`planned_pass_rate` 三种口径。

## 6. 存储层

### 6.1 `ResultStore`（JSONL/CSV）

路径：`storage/result_store.py`

- 构造：`ResultStore(root, snapshot_files=..., environment=...)`。
- `start_run(run_id, suite_id, suite_name, planned_count, cases)`。
- `save_result(result)`、`finish_run(run_id, status, summary)`。
- 目录：`results/automation/run_<run_id>/`，含 `results.jsonl`、
  `results.csv`、`summary.json`、`fault_events.jsonl`、配置快照。
- 不覆盖历史运行。

### 6.2 `SQLiteStore`

路径：`storage/sqlite_store.py`

- 默认数据库：`results/testlab.db`。
- 表：`runs`、`test_results`、`check_results`、`fault_events`。
- 写入：`start_run`、`save_result`（结果与检查项同事务）、
  `finish_run`、`save_fault_events`。
- 查询：`list_runs`、`get_run`、`get_results_by_run`、`get_checks`、
  `get_run_summary`、`get_fault_events_by_run`、`get_failed_results`。
- 重复 `(run_id, execution_index)` 幂等，不删除历史。
- 所有 SQL 参数化。

## 7. 分析与性能

路径：`analysis/`

- `PerformanceAnalyzer(limits_path).analyze(result, expected_source=None)`：
  返回顶层原始字段 + `metrics` + `checks` + `quality_status` +
  `metric_status`。
- 限值只来自 `configs/performance_limits.yaml`。
- 保护状态指标 `NOT_APPLICABLE`；空载效率 `None`；数据质量 ERROR 优先。
- `metrics.py`：功率、效率、电压误差、负载/线性调整率。
- `statistics.py`：均值、极值、中位数、样本标准差；无样本返回 `None`。
- 扫描配置：`configs/sweep_config.yaml`，包含负载、线性、二维扫描。
- 现有扫描编排位于 `scripts/full_performance_demo.py` 的
  `run_load_sweep/run_line_sweep/run_matrix_sweep`，UI 服务层复用
  `VirtualTestBench` 与 `PerformanceAnalyzer`，不复制指标公式。

## 8. 可靠性

路径：`reliability/`

- `load_fault_scenarios(path) -> FaultScenarioLibrary`
  - `ids()`、`get(id)`、`select(ids)`、`select_one(id)`、`to_dicts()`。
- `RetryPolicy.from_yaml(path)`；`FaultLogger(path)`，`emit()` 立即落盘。
- `load_experiments(path) -> dict[str, ExperimentExpectation]`。
- `evaluate_suite_experiment(results, expectation, *, stopped_early=None)
  -> (passed, reasons, actual)`。
- `ReliabilityAnalyzer().summarize(events, scenario_results)`。
- 重要口径：业务 PASS/FAIL/ERROR 与“实验是否符合预期”分离；
  恢复率分母为可重试操作数；清理状态只能是
  `VERIFIED_OFF / NOT_VERIFIED / NOT_APPLICABLE`。

## 9. 可供 Web 复用的入口

| 能力 | 入口 |
| --- | --- |
| 仪器发现/控制 | `InstrumentManager` + 三个驱动 |
| 单次模型读数 | `VirtualTestBench.read_state()` |
| 用例/方案 | `load_test_cases` / `load_test_suites` |
| 普通测试 | `TestRunner` / `SuiteRunner` |
| 性能分析 | `PerformanceAnalyzer.analyze()` |
| 故障场景 | `load_fault_scenarios` / `FaultInjector` |
| 重试与事件 | `RetryPolicy` / `FaultLogger` |
| 可靠性判定 | `evaluate_suite_experiment` |
| 历史查询 | `SQLiteStore` |
| 原始运行目录 | `ResultStore.run_directory(run_id)` |

## 10. 第九阶段实现约束

1. UI 不复制 DUT 公式、限值判定或 SCPI 字符串。
2. 所有测试结果必须由真实后端执行产生，禁止硬编码 PASS。
3. 仪器对象、数据库连接不得放入 `st.session_state`，每次操作使用
   短生命周期上下文并 `finally` 清理。
4. 单进程内测试任务串行执行，使用模块级 `threading.Lock`；
   不声明分布式并发能力。
5. 普通测试默认关闭故障注入；只有可靠性页显式选择场景才启用。
6. 历史页只读，不重新执行测试；导出路径限制在 `results/` 下。
