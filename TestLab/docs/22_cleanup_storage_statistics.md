# 22 清理验证、存储与可靠性统计

## 1. 清理状态

`engine/models.py::CleanupStatus`：

| 状态 | 含义 |
| --- | --- |
| `VERIFIED_OFF` | 已执行关闭并回读确认关闭 |
| `NOT_VERIFIED` | 无法确认（写入失败、会话失效、回读不通过） |
| `NOT_APPLICABLE` | 没有适用的清理对象（例如用例未执行） |

关键规则：

- 负载输入与电源输出**分别尝试**关闭，一个失败不阻止另一个；
- 只承诺“是否得到确认”，不推断硬件实际状态；
- 任一步失败，该用例强制变成 ERROR；
- 清理失败必须强制停止后续用例，即使 `stop_on_error=false`；
- 未执行用例记录 SKIP 与具体停止原因；
- 后续资源释放可以在禁用注入后独立执行，但**不得**把之前的
  `NOT_VERIFIED` 改写为成功。

F009 的 `SHUTDOWN_FAILURE` 只作用于 `cleanup:OUTP 0`，因此测试本体可以
正常完成，最后由清理阶段产生 ERROR 并强制停止。

## 2. 存储

### 2.1 JSONL

运行目录新增 `fault_events.jsonl`，每行一个事件，字段包括：

```
event_id, run_id, case_id, scenario_id, timestamp, event_type,
fault_type, target, device_id, operation, operation_id,
attempt_number, retry_number, error_category, exception_type,
message, original_value, injected_value, cleanup_status, details
```

- `event_id` 全局唯一；
- 时间带时区；
- NaN / ±Infinity 写成 `"NaN"` / `"Infinity"` / `"-Infinity"` 字符串，
  保证是合法 JSON；
- 写入失败只记录错误，不阻断测试或清理。

`TestResult` 同时保存 `fault_injected / fault_scenario_ids /
fault_events / retry_count / retry_exhausted / recovered /
error_category / cleanup_status / cleanup_errors /
original_model_data / observed_data / original_data_source /
observed_data_source`，旧字段全部保留。

### 2.2 SQLite

新增 `fault_events` 表：

```sql
CREATE TABLE IF NOT EXISTS fault_events (
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    case_id TEXT,
    scenario_id TEXT,
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,
    fault_type TEXT,
    device_id TEXT,
    operation TEXT,
    attempt_number INTEGER,
    retry_number INTEGER,
    error_category TEXT,
    exception_type TEXT,
    message TEXT,
    original_value TEXT,
    injected_value TEXT,
    cleanup_status TEXT,
    details_json TEXT,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);
```

- `initialize_database()` 使用 `CREATE TABLE IF NOT EXISTS`，并对旧表做
  `PRAGMA table_info` + `ALTER TABLE ADD COLUMN` 的可重复迁移；
- 不删除、不重建既有历史；
- 事件按 `event_id` 幂等写入；
- 查询接口：`get_fault_events_by_run`、`get_fault_events_by_type`、
  `get_retry_exhausted_events`、`get_recovered_events`、
  `count_fault_events`。

## 3. 统计口径

`reliability/reliability_analyzer.py`：

| 指标 | 定义 |
| --- | --- |
| 故障场景数量 | 执行的场景数（含 NONE 基线） |
| 故障注入次数 | `FAULT_INJECTED` 事件数 |
| 重试次数 | `RETRY_SCHEDULED` 事件数 |
| 可重试操作数 | 失败分类为 `TRANSIENT_COMMUNICATION`、`retry_safe=true` 且带 `operation_id` 的操作去重数 |
| 恢复操作数 | 同一 `operation_id` 出现 `RECOVERED` 的去重数 |
| 恢复率 | 恢复操作数 / 可重试操作数 |
| 重试耗尽 | `RETRY_EXHAUSTED` 或耗尽操作去重数 |
| 强制停止 | 清理失败导致后续 SKIP 的场景数 / `TEST_ABORTED` |
| 清理失败 | 业务结果中 `NOT_VERIFIED` 的数量 |
| 重试额外耗时 | 所有 `RETRY_SCHEDULED.details.delay_seconds` 之和 |
| 实验通过/失败 | 预设预期与实际行为的比较结果 |

注意：

- 恢复率分母不是注入次数；同一操作多次超时只算一个操作；
- 可靠性实验通过率不是产品良率；
- 业务 PASS/FAIL/ERROR 与实验通过/失败分开存储和展示。

## 4. 报告产物

`scripts.reliability_demo` 生成：

```
results/reliability/run_<run_id>/
├── scenario_results.csv
├── fault_events.jsonl
├── retry_statistics.json
├── reliability_summary.json
├── reliability_report.html
├── execution.log
└── charts/
    ├── fault_types.svg
    ├── retries_by_scenario.svg
    ├── recovery_outcome.svg
    ├── experiment_outcome.svg
    └── duration_by_scenario.svg
```

图表完全来自真实运行事件，不手写数字；SVG 由标准库生成，不依赖图表库。
报告同时展示 JSONL 与 SQLite 事件数是否一致。

## 5. 限制

- 所有数据来自模拟环境，不能用于真实设备可靠性认证；
- `NOT_VERIFIED` 只表示“无法确认”，不等于“已确认开启”；
- 统计不包含真实环境中的温漂、EMI、线缆接触不良等随机因素。
