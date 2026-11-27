# 63 任务执行与生命周期

## 1. 任务标识

格式：`job_YYYYMMDD_HHMMSS_<8 位十六进制>`，例如
`job_20261125_175819_acecc749`。管理器和 worker 都会校验格式，拒绝任意路径拼接。

## 2. 状态定义

| 状态 | 类别 | 含义 |
| --- | --- | --- |
| `QUEUED` | 活跃 | 已创建目录并启动工作进程，尚未进入 RUNNING |
| `RUNNING` | 活跃 | 工作进程正在执行 |
| `CANCEL_REQUESTED` | 活跃 | 已写取消标志，等待安全点或进程终止 |
| `COMPLETED` | 终止 | 处理函数正常返回 |
| `CANCELLED` | 终止 | 在安全点观察到取消，或取消后进程被终止 |
| `FAILED` | 终止 | 处理函数抛出异常，已写日志 |
| `TIMED_OUT` | 终止 | 超过单任务时限，进程被终止 |
| `PARTIAL` | 终止 | 部分工况成功（保留给批量任务结果层） |
| `INTERRUPTED` | 终止 | 工作进程未正常结束（启动失败/意外退出） |

任务状态只描述执行结果。工程性能判定（PASS/FAIL/NOT_RESOLVED/NOT_VERIFIED）
由 `analysis.performance_judge` 单独给出，`COMPLETED` 不等于 `PASS`。

## 3. 状态迁移

```text
submit
  └─ QUEUED ──worker 启动──▶ RUNNING ──成功──▶ COMPLETED
        │                       ├──异常──▶ FAILED
        │                       ├──安全点取消──▶ CANCELLED
        │                       └──超时──▶ TIMED_OUT
        ├──启动失败──▶ FAILED / INTERRUPTED
        └──取消请求──▶ CANCEL_REQUESTED ──进程终止确认──▶ CANCELLED
```

管理器采用**惰性核对**：在 `get_job()` 时检查

- QUEUED 超过 30 s 仍无 pid → INTERRUPTED；
- QUEUED 超过 5 s 且 pid 已退出 → INTERRUPTED；
- RUNNING 超过单任务时限 → 终止进程 → TIMED_OUT；
- RUNNING 但 pid 已退出 → 重新读取 `job.json`，仍为活跃则 INTERRUPTED。

## 4. 任务目录文件

| 文件 | 写入方 | 内容 |
| --- | --- | --- |
| `job.json` | 管理器 / worker | 状态、计数、pid、结果 run_id、错误、预算、日志路径 |
| `request.json` | 管理器 | 已校验并转换为 SI 的请求 |
| `progress.json` | worker | 计划/完成/失败工况、SPICE 调用、缓存命中、阶段、消息 |
| `cancel.flag` | 管理器 | 取消原因与时间 |
| `log.txt` | worker | 启动信息、处理日志、异常堆栈 |

`job.json` 与 `progress.json` 均先写临时文件再原子替换，避免半写状态。

## 5. 请求指纹与重复提交

指纹为 `SHA-256(job_type + 规范化 SI 请求)`。提交时：

1. 若活跃任务中存在相同指纹 → `DuplicateJobError`，提示已有任务编号；
2. 若活跃任务数达到并发上限 → `ConcurrencyLimitError`；
3. 参数不合法 → `InvalidJobRequest`，不创建任务目录。

## 6. 取消语义

- 第一级：worker 在每个工况开始前检查 `cancel.flag`，命中则抛出 `JobCancelled`；
- 第二级：管理器在写标志后终止工作进程树（Windows `taskkill /PID <pid> /T /F`），
  并轮询确认进程退出后才报告 `CANCELLED`；
- 已终止任务再次取消不产生副作用。

ngspice 以共享 DLL 在 worker 进程内运行，没有独立求解子进程；终止 worker 即终止求解。

## 7. 超时与预算

| 约束 | 默认值 | 来源 |
| --- | --- | --- |
| 并发任务 | 1 | `job_limits.yaml` |
| 单任务时长 | 3600 s | `job_limits.yaml` |
| 单工况时长 | 300 s | `job_limits.yaml` |
| 单任务 SPICE 调用 | 120 | `job_limits.yaml` / profile |
| Monte Carlo 样本 | 30 | `job_limits.yaml` |

提交前按任务类型估算工况数（扫描值个数、样本数、时间步个数），超过 profile 上限即拒绝。

## 8. 结果关联

- `job.json.result_run_ids` 记录任务产生的主运行编号；
- 派生分析在结果元数据中写入 `parent_run_id`，索引可据此追溯；
- 批量任务的主运行目录包含 `sweep_table.csv` / `samples.csv` / `convergence_points.csv`，
  每个真实 SPICE 点另有自己的工作目录（含 `web_run.json` 的 `job_id`）。

## 9. Web 重启后的任务状态

Web 进程不保存唯一状态副本。重启后：

1. 页面读取 `results/web_jobs/*/job.json` 重新发现任务；
2. 对活跃任务执行惰性核对（见第 3 节）；
3. 工作进程仍在运行的，继续显示真实进度；
4. 工作进程已退出的，标记 INTERRUPTED，不补写波形或指标；
5. 历史结果仍通过 `results/run_index.json` 或重新扫描读取。

因此刷新页面或重启 Streamlit 不会丢失任务记录，也不会把未完成任务伪装成完成。

## 10. 日志大小限制

工作进程通过 `JobContext.log()` 写日志，累计字节数受
`configs/job_limits.yaml` 的 `limits.maximum_log_bytes`（默认 2,000,000）约束。
超过上限后写入一行 `log truncated` 并停止追加，避免异常循环或大量工况日志撑满磁盘。
异常堆栈在截断前已写入，页面日志预览只读取末尾若干行。

