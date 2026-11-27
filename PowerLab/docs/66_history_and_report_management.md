# 66 历史记录与报告管理

## 1. Run ID 与 Job ID

| 标识 | 格式 | 含义 | 来源 |
| --- | --- | --- | --- |
| Job ID | `job_YYYYMMDD_HHMMSS_<8hex>` | 一次 Web 任务 | `results/web_jobs/<job_id>/job.json` |
| Run ID | `YYYYMMDD_HHMMSS_<8hex>` | 一次真实仿真/分析运行 | `results/**/run_<run_id>/metadata.json` |

关系：

- 单次仿真任务：1 个 Job → 1 个主 Run；
- 参数扫描/Monte Carlo：1 个 Job → 1 个汇总 Run + N 个真实 SPICE Run；
- 派生分析：1 个 Job → 1 个 `spice_derived` Run，并在元数据中记录 `parent_run_id`；
- Web Run 的 `web_run.json` 写入 `job_id`、`model`、`data_source`、`evidence_level`。

## 2. 原始仿真与派生分析

| 类型 | 判据 | 数据来源标注 |
| --- | --- | --- |
| 原始仿真 | 元数据含 `environment` 或 `backend` | `spice_simulation` |
| 派生分析 | 元数据 `run_kind=derived_analysis` | `spice_derived` |
| 无法判定 | 无环境/后端证据 | `unknown` |

派生分析不产生新 SPICE 波形，只重新计算指标；页面与报告都显示派生标记与父运行。

## 3. 结果索引

文件：`results/run_index.json`，由 `storage/run_index.py` 维护。

- `discover_run_dirs()` 扫描 `results/**/run_*/metadata.json`，忽略 `web_jobs`；
- `build_index()` 读取 `metadata.json`，并补充 `web_run.json` 的 `job_id` / `model`；
- 条目字段：`run_id`、`path`、`run_kind`、`analysis_type`、`circuit_name`、`model`、
  `data_source`、`status`、`created_at`、`job_id`、`parent_run_id`、`has_waveform`、
  `has_performance`、`has_summary`、`has_netlist`、`point_count`、`duration_ms`、
  `size_bytes`、`summary_path`；
- 索引**只存元数据**，不存波形数组；
- 原子写；版本 `INDEX_SCHEMA_VERSION = 1.0`，版本不符返回 `None` 后重建。

重建命令：

```powershell
conda run -n kaifa_power python -m scripts.rebuild_run_index
```

2026-11-25 实际结果：308 条记录，`run_id` 去重后仍为 308，无重复条目；
`verify_web` 的 `index:build` 检查同样报告 `runs=308`。

## 4. 配置快照

每个成功运行保存：

- `config_snapshot.yaml`：输入配置（来自 `save_config_snapshot()`）；
- `circuit.cir`：含分析命令的网表；
- `analysis_parameters.json`：分析参数与模型参数；
- `metadata.json`：运行编号、分析类型、环境、质量标记、文件清单。

历史页在“配置/网表”标签页只读展示，不提供编辑。

## 5. 报告生成

### 5.1 运行级文件

| 文件 | 生成方 | 内容 |
| --- | --- | --- |
| `summary.json` | `ResultStore.save_result()` | 运行摘要、指标子集、检查汇总 |
| `performance_metrics.json` | `jobs.handlers._save_spice_result()` | 指标、单位、状态、数据来源 |
| `checks.csv` | 同上 | 逐项工程检查 |
| `web_run.json` | 同上 | job_id、model、证据等级 |

### 5.2 HTML 报告

`ui/export_service.html_report(run_id)`：

- 读取 `load_run_bundle()`、`performance_metrics.json`、`summary.json`、`web_run.json`；
- 生成自包含 HTML（无外部资源）；
- 内容包含运行编号、任务编号、模型、数据来源、证据等级、指标表、检查表、摘要；
- 明确写明“不是硬件实测”；
- **不重新运行 SPICE**。

真实生成证据：

```powershell
conda run -n kaifa_power python -c "from ui.export_service import html_report; n,m,d=html_report('20261125_175823_618448b9'); open('results/stage9/'+n,'wb').write(d)"
```

结果：`results/stage9/run_20261125_175823_618448b9_report.html`，14,764 字节，`text/html`。

### 5.3 任务报告

`ui/export_service.job_report_markdown(record, summary)` 生成 Markdown 摘要，
包含任务类型、状态、工况计数、SPICE 调用、结果运行编号与错误信息。

## 6. 数据导出

| 函数 | 文件 | 说明 |
| --- | --- | --- |
| `waveform_csv()` | `run_<id>_waveform.csv` | 完整原始波形，不经抽样 |
| `metrics_csv()` | `run_<id>_metrics.csv` | 指标、单位、状态、数据来源 |
| `checks_csv()` | `run_<id>_checks.csv` | 工程检查项 |
| `summary_json()` | `run_<id>_summary.json` | 摘要 JSON，UTF-8 |
| `html_report()` | `run_<id>_report.html` | 自包含报告 |
| `table_csv()` | `<name>.csv` | 扫描表、样本表等 |

CSV 使用 `utf-8-sig`，便于 Excel 正确识别中文；JSON 使用 `ensure_ascii=False`。
下载采用“先生成、后下载”的两步式 `lazy_download()`，避免 Streamlit rerun 重复读取大文件。

## 7. 历史结果追溯

典型路径：

1. 历史页按关键字/来源/类型筛选索引；
2. 打开运行详情，查看元数据、配置快照、网表、文件清单；
3. 由 `web_run.json.job_id` 找到 `results/web_jobs/<job_id>/`，读取任务状态与日志；
4. 由 `parent_run_id` 追溯派生分析的源运行；
5. 导出完整波形/指标/检查项/HTML 报告进行离线复核。

索引损坏或过期时，历史页提供“重建索引”，重建过程只读运行目录，不删除、不覆盖任何历史结果。
