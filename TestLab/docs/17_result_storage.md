# 17 运行目录与结果存储

`storage/result_store.py` 为每次运行创建独立目录，保证历史结果不被覆盖。

## 1. 目录结构

```
results/automation/run_<run_id>/
├── metadata.json              # 运行元数据、环境、配置快照清单
├── test_cases_snapshot.yaml   # 用例配置快照（运行时实际使用的文件）
├── dut_config_snapshot.yaml   # DUT 模型参数快照
├── limits_snapshot.yaml       # 工程限值快照
├── results.jsonl              # 逐条追加的完整结果
├── results.csv                # 宽表，便于 Excel / pandas
├── summary.json               # 汇总统计与结束状态
└── execution.log              # 执行日志（含停止原因、存储错误）
```

`run_id` 为 UUID，目录已存在时 `start_run` 会抛错，禁止复用同一目录。

## 2. results.jsonl

每行一条 `TestResult.to_dict()`，包含：

- 标识：`run_id`、`execution_index`、`case_id`、`case_name`；
- 时间：`started_at`、`finished_at`、`duration_ms`；
- 判定：`status`、`expected_state`、`actual_state`、`checks`；
- 数据：`raw_data`（模型原始输出）、`metrics`（派生指标）；
- 质量：`quality_issues`、`error_message`、`cleanup_failed`；
- 来源：`data_source`（`behavioral_model`）。

原始字段与派生指标分开保存，指标不得覆盖原始数据。

## 3. results.csv

CSV 是宽表视图，字段固定（`storage/result_store.py::CSV_FIELDS`）：
用例、状态、设定值、`vin/iin/vout/iout/pin/pout`、效率、电压误差、
来源与错误说明。检查项细节只保留在 JSONL 与 SQLite 中。

缺失值写空字符串，不填 0；文件使用 `utf-8-sig`，便于 Excel 打开中文。

## 4. 非有限数值

NaN / Infinity 不能写成 JSON 数字，本平台统一写成明确字符串：

| 值 | JSON 表示 |
| --- | --- |
| NaN | `"NaN"` |
| +Infinity | `"Infinity"` |
| -Infinity | `"-Infinity"` |

同时在 `quality_issues` 中记录数据质量问题，**不会**静默转换为正常数字。

## 5. summary.json

```json
{
  "run_id": "...",
  "suite_id": "SUITE-REGRESSION",
  "status": "COMPLETED",
  "started_at": "...",
  "finished_at": "...",
  "summary": {
    "total_cases": 12,
    "executed_cases": 12,
    "pass_count": 12,
    "fail_count": 0,
    "error_count": 0,
    "skip_count": 0,
    "pass_rate": 100.0,
    "completion_rate": 100.0,
    "planned_pass_rate": 100.0
  }
}
```

三个比率口径不同，禁止只报通过率：

- `pass_rate = PASS / (PASS + FAIL)`（有效判定通过率）；
- `completion_rate = (PASS + FAIL + ERROR) / 计划数`；
- `planned_pass_rate = PASS / 计划数`。

## 6. 一致性

- 结果逐条写入，进程中断时已完成记录仍然保留；
- JSONL 行数应与 SQLite 中同 `run_id` 的记录数一致；
- 存储失败由 `SuiteRunner` 记录到 `storage_errors` 与
  `execution.log`，并把方案状态置为 `ERROR`，不会隐瞒。
