# 18 SQLite 测试历史数据库

`storage/sqlite_store.py` 使用标准库 `sqlite3` 保存结构化历史，
默认数据库为 `results/testlab.db`，与 `results/automation/` 的 JSONL
运行目录互补。

## 1. 表结构

```sql
CREATE TABLE runs (
  run_id TEXT PRIMARY KEY,
  suite_id TEXT,
  suite_name TEXT,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  planned_count INTEGER NOT NULL,
  summary_json TEXT
);

CREATE TABLE test_results (
  result_id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  case_id TEXT NOT NULL,
  execution_index INTEGER NOT NULL,
  case_name TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  duration_ms REAL,
  status TEXT NOT NULL CHECK (status IN ('PASS','FAIL','ERROR','SKIP')),
  expected_state TEXT,
  actual_state TEXT,
  raw_data_json TEXT,
  metrics_json TEXT,
  error_message TEXT,
  data_source TEXT,
  FOREIGN KEY (run_id) REFERENCES runs(run_id),
  UNIQUE (run_id, execution_index)
);

CREATE TABLE check_results (
  check_id INTEGER PRIMARY KEY AUTOINCREMENT,
  result_id INTEGER NOT NULL,
  check_name TEXT NOT NULL,
  actual_json TEXT,
  expected_json TEXT,
  status TEXT NOT NULL CHECK (status IN ('PASS','FAIL','ERROR','SKIP')),
  message TEXT,
  FOREIGN KEY (result_id) REFERENCES test_results(result_id)
);
```

索引：`test_results(run_id)`、`test_results(status)`。

## 2. 事务与一致性

- 连接开启 `PRAGMA foreign_keys = ON`；
- 单条结果与其全部检查项在**同一事务**中写入：任一失败整体回滚，
  不会出现“有结果、缺检查项”的半条记录；
- 结果写入前自动确保 `runs` 记录存在，避免外键失败；
- `ON CONFLICT(run_id, execution_index) DO NOTHING` 处理重复写入：
  重复保存返回既有 `result_id`，不覆盖、不删除历史；
- 所有 SQL 使用参数绑定，用例名称中的引号等字符只作为数据处理。

## 3. 查询接口

| 方法 | 用途 |
| --- | --- |
| `list_runs()` | 按开始时间倒序列出运行 |
| `get_run(run_id)` | 读取单次运行元数据 |
| `get_results_by_run(run_id)` | 按执行顺序返回用例结果 |
| `get_failed_results(run_id=None)` | 返回 FAIL/ERROR 记录 |
| `get_checks(result_id)` | 返回某项结果的检查明细 |
| `get_run_summary(run_id)` | 按状态统计真实记录数 |
| `count_results(run_id)` | 与 JSONL 行数对账 |

命令行入口见 [19_ci_usage.md](19_ci_usage.md) 中的
`scripts/query_test_history.py`。

## 4. 设计取舍

- **JSON 列**：`raw_data_json` / `metrics_json` 保留完整结构，避免为每个
  指标改表；查询常用字段（状态、用例、时间）单独建列；
- **不做自动归档**：当前不删除历史；数据量增大后应新增归档策略，
  而不是让写入覆盖旧记录；
- **本地单文件**：适合单机测试台；多机并发不是当前目标。

## 5. 局限

- SQLite 中的结果与 JSONL 属于两份独立写入，极端情况下可能不一致；
  出现存储失败时方案状态会置为 `ERROR`，应通过
  `count_results` 与 JSONL 行数对账；
- 数据库中的数值来源仍是行为模型仿真结果，不是真实硬件测量。
