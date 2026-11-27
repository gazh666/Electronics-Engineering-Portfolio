# TestLab 源码学习指南（真实路径 + 行号）

> 对应版本：`VERSION` = 1.0.0；HEAD `6156c2b`；Windows + conda `kaifa`（Python 3.11.18）。
> 本文所有行号均来自当前工作区源码，改动源码后行号可能偏移。
> 学习目标：能独立讲清“一条用例从界面到数据库”的完整链路，并能定位每类异常的处理点。

---

## 0. 分层与推荐阅读顺序

```text
app.py / ui/views/*           界面（只调用 service）
        ↓
ui/service.py                 Web 服务层（唯一入口，任务锁）
        ↓
engine/                       用例加载 → 执行 → 判定 → 方案编排
   ↑            ↑
instruments/   reliability/   仪器通信 / 故障注入、重试、事件
        ↓
models/virtual_dut.py         行为模型（电压/保护状态/效率）
        ↓
analysis/                     指标、数据质量、性能分析
        ↓
storage/                      JSONL/CSV 运行目录 + SQLite
        ↓
reports/generator.py          离线 HTML 综合报告
```

建议顺序：`core/paths.py` → `instruments/base.py` → `models/virtual_dut.py` →
`engine/case_loader.py` → `engine/test_runner.py` → `engine/result_judge.py` →
`storage/*` → `engine/suite_runner.py` → `reliability/*` → `analysis/*` →
`reports/generator.py` → `ui/service.py`。

---

## 1. 核心文件索引

| 文件 | 关键类/函数（行号） | 对应测试 |
| --- | --- | --- |
| `core/paths.py` | `PROJECT_ROOT` L23、`results_dir()` L35、`database_path()` L43、`ensure_runtime_directories()` L56 | `tests/test_project_paths.py` |
| `instruments/base.py` | `BaseInstrument` L73、`write` L191、`query` L209、`query_float` L248、`query_int` L259、`identify` L279 | `tests/test_instruments.py` |
| `instruments/manager.py` | `InstrumentManager` L24、`discover` L150、`create` L178、`open_device` L220、`close_device` L258 | `test_instrument_manager.py`、`test_discovery.py` |
| `instruments/power_supply.py` | 6 个业务方法 L83-112 | `test_power_supply.py` |
| `instruments/multimeter.py` | 8 个业务方法 L47-87 | `test_multimeter.py` |
| `instruments/electronic_load.py` | 7 个业务方法 L21-66 | `test_electronic_load.py` |
| `models/virtual_dut.py` | `DUTState` L39、`DUTConfig` L58、`DUTResult` L127、`VirtualDUT` L153、`from_yaml` L171、`calculate` L249 | `test_virtual_dut.py` |
| `bench/virtual_test_bench.py` | `VirtualTestBench` L56、`read_snapshot` L70、`get_model_measurements` L81、`get_static_mock_measurements` L91 | `test_virtual_test_bench.py` |
| `engine/case_loader.py` | `validate_number` L92、`load_test_cases` L171、`load_test_suites` L258 | `test_case_loader.py` |
| `engine/models.py` | `TestStatus` L24、`TestCase` L73、`TestResult` L158、`summarize_results` L275 | 间接覆盖（多处） |
| `engine/result_judge.py` | `judge` L52、`judge_state` L81、`judge_range` L102、`aggregate_status` L165 | `test_result_judge.py` |
| `engine/test_runner.py` | `ScenarioTestRunner` L102、`TestRunner` L611、`run_case` L669、`_cleanup` L995 | `test_runner.py`、`test_end_to_end.py` |
| `engine/suite_runner.py` | `SuiteRunner` L41、`run_suite` L62、`exit_code_for_results` L409 | `test_suite_runner.py`、`test_automation_integration.py` |
| `engine/fault_injector.py` | `FaultInjector` L126、`apply` L146、`finalize` L231 | `test_fault_injector.py` |
| `storage/result_store.py` | `ResultStore` L92、`start_run` L115、`save_result` L172、`finish_run` L225 | `test_result_store.py` |
| `storage/sqlite_store.py` | `SQLiteStore` L168、`start_run` L211、`save_result` L241、`save_check_results` L291、`finish_run` L299、`get_run_summary` L484 | `test_sqlite_store.py` |
| `analysis/metrics.py` | 指标函数 L54-241、`calculate_metrics` L257、`pass_rate_percent` L283 | `test_metrics.py` |
| `analysis/data_quality.py` | `inspect_power_data` L134、`validate_record` L267、`validate_dataset` L415 | `test_data_quality.py` |
| `analysis/performance_analyzer.py` | `PerformanceLimits` L60、`load_performance_limits` L78、`PerformanceAnalyzer` L200、`analyze` L221 | `test_performance_analyzer.py` |
| `analysis/statistics.py` | `summarize` L33、`summarize_by_group` L79 | `test_statistics.py` |
| `reliability/fault_models.py` | `FaultScenario` L136、`FaultScenarioLibrary` L343、`load_fault_scenarios` L450 | `test_fault_models`（含于可靠性测试） |
| `reliability/fault_injector.py` | `FaultInjector` L47、`before_query` L149、`before_write` L188、`before_cleanup` L212、`transform_measurement` L244 | `test_fault_injector.py` |
| `reliability/error_classifier.py` | `ErrorCategory` L33、`classify_error` L63、`is_retryable_category` L113 | `test_error_classifier.py` |
| `reliability/retry_policy.py` | `RetryPolicy` L93、`RetryExecutor` L232、`execute` L297 | `test_retry_policy.py` |
| `reliability/fault_logger.py` | `EventType` L32、`FaultLogger` L134、`emit` L163 | `test_fault_logger.py` |
| `reliability/reliability_analyzer.py` | `load_experiments` L112、`ReliabilityAnalyzer` L184、`summarize` L190、`evaluate_suite_experiment` L363 | `test_reliability_analyzer.py` |
| `reports/generator.py` | `validate_run_id` L171、`load_run_bundle` L308、`build_conclusion` L425、`build_test_report` L706、`render_report_html` L748、`write_html_report` L803、`generate_test_report` L822 | `test_report_generator.py`、`test_web_report_export.py` |
| `ui/service.py` | `TaskBusyError` L83、`TestLabService` L206、`run_test_suite` L693、`run_performance_sweep` L757、`run_fault_scenario` L952、`run_reliability_validation` L963、`get_run_details` L1257、`export_run_csv` L1363、`generate_run_report` L1455 | `test_ui_service.py`、`test_streamlit_app.py` |
| `ui/state.py` | `begin_task` L32、`finish_task` L37、`set_error` L41、`remember_test_run` L45 | `test_ui_state.py` |

---

## 2. 三条关键调用链

### 2.1 单用例 / 方案执行链

`app.py` → `ui/views/automation.py` → `ui/service.py::run_test_suite` L693 →
`engine/suite_runner.py::run_suite` L62 → `engine/test_runner.py::run_case` L669 →
仪器（`instruments/*`）+ 模型（`models/virtual_dut.py::calculate` L249）→
`engine/result_judge.py::aggregate_status` L165 →
`storage/result_store.py::save_result` L172 + `storage/sqlite_store.py::save_result` L241 →
`engine/models.py::summarize_results` L275 → 返回 `SuiteRunResult`。

### 2.2 性能扫描链

`ui/views/performance.py` → `service.py::run_performance_sweep` L757 →
`bench/virtual_test_bench.py` 取数 → `analysis/performance_analyzer.py::analyze` L221 →
CSV/JSON 写入 `results/performance_<时间戳>_<随机>/`。

### 2.3 可靠性链

`ui/views/reliability.py` → `service.py::run_fault_scenario` L952 /
`run_reliability_validation` L963 → `engine/test_runner.py::configure_reliability` L651 →
`reliability/fault_injector.py` 注入 → `reliability/retry_policy.py::RetryExecutor.execute` L297 →
`reliability/fault_logger.py::emit` L163 → `reliability/reliability_analyzer.py::evaluate_suite_experiment` L363 →
`results/reliability/run_<id>/`。

---

## 3. 关键类的输入 / 输出 / 异常 / 调用关系

### 3.1 `instruments/base.py::BaseInstrument`（L73）

| 方法 | 输入 | 输出 | 异常 |
| --- | --- | --- | --- |
| `bind` L132 | `MessageBasedResource`、`owns_resource` | `None` | `InstrumentError` |
| `write` L191 | `command: str` | `None` | `InstrumentNotConnectedError`、`InstrumentTimeoutError`、`InstrumentResponseError` |
| `query` L209 | `command: str` | `str`（strip 后） | 同上 + 会话丢失 |
| `query_float` L248 | `command` | `float` | `InstrumentResponseError`（非数字） |
| `query_int` L259 | `command` | `int` | `InstrumentResponseError` |
| `identify` L279 | 无 | `*IDN?` 字符串 | 未连接异常 |

调用关系：由 `Instruments/manager.py::create` L178 实例化并 `bind`；上层 `PowerSupply`/`DMM`/`Load` 只调用这些基础方法。
异常定义：`instruments/exceptions.py` L11-36（`InstrumentError` 及 4 个子类）。

### 3.2 `models/virtual_dut.py::VirtualDUT`（L153）

- `from_yaml` L171：输入 `configs/dut_config.yaml` → `VirtualDUT`；YAML 缺字段/类型错误抛 `ValueError`。
- `calculate` L249：输入 `vin`、`iout`、`output_enabled` 等 → `DUTResult`（vout、iin、状态、保护标志）。
- 保护判定顺序在 L310-351：欠压 → 过压 → 过流 → 输入限流；`NORMAL` 之外的状态会阻断 PASS。
- 调用方：`bench/virtual_test_bench.py`、`engine/test_runner.py`。
- 测试：`tests/test_virtual_dut.py`（边界、保护、效率异常）。

### 3.3 `engine/test_runner.py::TestRunner`（L611）

- `run_case` L669：输入 `TestCase` → `TestResult`。
  流程：参数校验 → 设置工况 → `_verify_setpoints` L967（回读不一致抛 `SetpointMismatchError` L607）
  → 采集 → `_analyze` L889 → 判定 → `_cleanup` L995。
- `_cleanup` L995：先关负载输入再关电源输出，返回清理状态；失败时结果强制 `ERROR`。
- 异常处理：`InjectedFaultError` 子类 → ERROR/FAIL；`SetpointMismatchError` → ERROR；清理异常不会被吞掉。
- 测试：`test_runner.py`、`test_end_to_end.py`、`test_fault_injector.py`。

### 3.4 `engine/suite_runner.py::SuiteRunner`（L41）

- `run_suite` L62：输入 `TestSuite` + 运行参数 → `SuiteRunResult`。
- 规则：`stop_on_error` 默认 True；ERROR 后剩余用例记 SKIP；`stop_on_fail` 按方案配置。
- 存储：`_start_stores` L274、`_persist` L304、`_finish_stores` L322；存储失败调用 `_storage_failure` L337。
- 退出码：`exit_code_for_results` L409（0 全通过 / 1 有 FAIL / 2 有 ERROR / 3 未完成）。
- 测试：`test_suite_runner.py`、`test_automation_integration.py`。

### 3.5 `storage/sqlite_store.py::SQLiteStore`（L168）

- `start_run` L211：写 `runs` 行；`save_result` L241：写 `test_results` + 自动 `_ensure_run` L516；
  `save_check_results` L291：写 `check_results`；`finish_run` L299：更新状态与汇总。
- `get_run_summary` L484：读取运行汇总，报告模块使用。
- 异常：`sqlite3.Error` 由调用方转换为存储失败；不静默忽略。
- 测试：`test_sqlite_store.py`、`test_automation_integration.py`。

### 3.6 `reliability/retry_policy.py::RetryExecutor`（L232）

- `execute` L297：输入 `operation_name` + 可调用对象 → 返回值或抛 `RetryExhaustedError`。
- 限制：只重试白名单只读查询（`is_allowed_query` L177）且分类为瞬态（`is_retryable_category` L113）；
  写入与清理失败不重试。
- 记录：`retry_count` L287、`recovered` L292；事件由 `FaultLogger.emit` L163 落盘。
- 测试：`test_retry_policy.py`、`test_error_classifier.py`。

### 3.7 `reports/generator.py` 报告链路

- `load_run_bundle` L308：只读运行目录快照 + SQLite 汇总，**不重跑测试**。
- `build_conclusion` L425：确定性规则（清理未验证 / 运行未完成 / ERROR>0 / FAIL>0 / PASS=0 / SKIP>0 / 全通过）。
- `build_test_report` L706 → `render_report_html` L748（`string.Template` 替换 `$REPORT_TITLE`/`$BODY`）
  → `write_html_report` L803（`x` 模式，不覆盖）→ `generate_test_report` L822。
- 异常：`ReportError` L167（非法 run_id、报告越界写入）；`validate_run_id` L171 只允许安全字符。
- 测试：`test_report_generator.py`、`test_web_report_export.py`。

---

## 4. 十项独立代码练习（只给指导，不代为执行）

> 原则：练习只读代码、写临时脚本或测试，**不修改生产代码**；所有输出放到临时目录，避免污染 `results/`。

### 练习 1：路径优先级实验

- 目标：验证 `TESTLAB_RESULTS_DIR` > `TESTLAB_RESULTS_ROOT` > 默认 `results/`。
- 代码：`core/paths.py` L35-50。
- 步骤：在 PowerShell 会话中设置两个环境变量，分别导入 `core.paths` 并打印 `results_dir()`。
- 验收：能解释为什么 `RESULTS_DIR`（L52）是导入快照，而 `results_dir()` 是调用时求值。
- 参考测试：`tests/test_project_paths.py`。

### 练习 2：用例加载与校验失败

- 目标：理解 YAML → `TestCase` 的校验边界。
- 代码：`engine/case_loader.py` L171、`validate_limits` L117。
- 步骤：复制 `configs/test_cases.yaml` 到临时目录，删除某个 `limits` 字段后加载，观察异常类型与消息。
- 验收：能说出哪类错误是 `ValueError`，以及为什么不允许未知字段。

### 练习 3：手算指标并与代码对比

- 目标：掌握 10 个指标函数的口径。
- 代码：`analysis/metrics.py` L54-241。
- 步骤：取 TC001 的 `raw_data`，手算 Pin/Pout/Ploss/η/电压误差/负载调整率，再调用函数对比。
- 验收：误差为 0；能解释 `efficiency_percent` 在 Pin=0 时为何返回 `None`。

### 练习 4：判定优先级

- 目标：理解“数据质量 → DUT 状态 → 工程限值”。
- 代码：`engine/result_judge.py` L52-165；`engine/test_runner.py::_judge` L534。
- 步骤：构造三种输入：NaN 指标、保护状态、超限值，分别观察最终状态。
- 验收：能画出优先级流程图，并说明为何空检查项返回 ERROR。

### 练习 5：直接与虚拟仪器对话

- 目标：理解 PyVISA-sim 后端与 SCPI 回读。
- 代码：`instruments/base.py` L191-279；`configs/instruments.yaml`。
- 步骤：用 `pyvisa.ResourceManager("@sim")` 打开资源，手工发送 `*IDN?`、`VOLT 5`、`VOLT?`、`OUTP?`。
- 验收：能解释为什么设置后必须回读，以及无响应查询为何触发超时。

### 练习 6：双写一致性核对

- 目标：理解 JSONL/CSV 与 SQLite 的关系。
- 代码：`storage/result_store.py` L172、`storage/sqlite_store.py` L241。
- 步骤：跑一次 `SUITE-SMOKE`，比较 `results.jsonl` 行数与 `test_results` 行数、`check_results` 行数。
- 验收：数量一致；能说明哪个是“事实来源”、哪个是“查询索引”。

### 练习 7：单次超时与重试

- 目标：理解 F001 的恢复路径。
- 代码：`reliability/fault_injector.py::before_query` L149、`retry_policy.py::execute` L297。
- 步骤：用 F001 场景跑一次，阅读 `fault_events.jsonl` 的事件顺序。
- 验收：能指出 `attempt_count / retry_count / recovered` 三个字段各自的含义。

### 练习 8：数据质量拦截

- 目标：理解 NaN/Infinity 与功率不守恒的拦截点。
- 代码：`analysis/data_quality.py::validate_record` L267、`inspect_power_data` L134。
- 步骤：手工构造一条 `vout=NaN` 记录，跑 `validate_record`，观察 `QualityIssue`。
- 验收：能说明为什么数据质量问题必须是 ERROR，而不是 FAIL。

### 练习 9：离线报告生成

- 目标：理解报告只读快照、不重跑。
- 代码：`reports/generator.py` L308-822；模板 `reports/templates/test_report.html`。
- 步骤：对一个历史 run_id 调用 `generate_test_report`，检查输出路径必须在 results 内、同名不覆盖。
- 验收：能指出模板中的两个占位符及替换位置，并解释 `x` 模式的作用。

### 练习 10：覆盖率盲区分析

- 目标：学会用覆盖率定位未测试分支。
- 代码：`ui/views/instruments.py`、`ui/views/performance.py`（当前 40.6% / 42.2%）。
- 步骤：运行 `pytest tests --cov=ui --cov-report=term-missing`，挑一个 `Missing` 行段，
  说明它对应哪个 UI 分支，并设计一个 AppTest 场景（只设计，不要求实现）。
- 验收：能说出“覆盖率高不等于测试有效”，并给出一个具体缺失分支的例子。

---

## 5. 异常与状态约定速查

| 场景 | 结果 | 代码位置 |
| --- | --- | --- |
| 数据质量不通过 | ERROR | `engine/test_runner.py::_judge` L534 |
| DUT 保护状态非预期 | FAIL/ERROR（按用例预期） | `engine/result_judge.py::judge_state` L81 |
| 工程限值超限 | FAIL | `judge_range` L102 |
| 设置值回读不一致 | ERROR（`SetpointMismatchError`） | `engine/test_runner.py` L607、L967 |
| 清理失败 | ERROR + 停止后续 | `engine/test_runner.py::_cleanup` L995 |
| 存储失败 | ERROR | `engine/suite_runner.py::_storage_failure` L337 |
| 重试耗尽 | ERROR | `reliability/exceptions.py::RetryExhaustedError` L64 |

## 6. 已知口径差异（学习时注意）

- `engine.models.summarize_results` 的 `pass_rate` = PASS/(PASS+FAIL)；
- `analysis.metrics.pass_rate_percent` 的分母是 PASS+FAIL+ERROR；
- 两者都合法但含义不同，写文档或简历时必须写明是哪种口径。
