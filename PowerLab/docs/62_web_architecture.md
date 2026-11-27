# 62 Web 平台架构

## 1. 目标

在既有七/八阶段后端之上增加 Streamlit 可视化工作台，使电路仿真、性能分析、
闭环实验、批量实验、数值验证与历史结果读取全部通过真实任务执行，并保持：

- 页面进程不被长时间 SPICE 求解阻塞；
- 任务状态可持久化、可恢复核对；
- 历史结果只读，索引可重建；
- 数据来源、证据等级与工程判定不被混淆。

## 2. 分层

```text
app.py
  └─ ui.navigation / ui.state / ui.theme
       └─ ui.views.<page>            页面渲染
            ├─ ui.form_validation    表单与跨字段校验（工程单位）
            ├─ ui.service            提交、查询、取消、索引、环境状态
            ├─ ui.result_reader      波形读取缓存与抽样
            ├─ ui.waveform_viewer    波形交互
            └─ ui.export_service     原始文件导出

ui.service
  └─ jobs.manager.JobManager        提交、并发、预算、核对、取消
       ├─ jobs.registry             白名单 + 参数校验 + SI 转换
       ├─ jobs.resource_budget      预算与磁盘检查
       ├─ jobs.cancellation         取消标志与进程终止
       └─ subprocess: python -m jobs.worker
            └─ jobs.worker          状态机、日志、进度同步
                 └─ jobs.handlers   真实调用既有模块
                      ├─ simulations / circuits / control
                      ├─ analysis / validation
                      └─ storage.result_store
```

页面层与仿真层之间不存在直接依赖；`jobs` 与 `storage` 可在无 Streamlit 环境下单独测试。

## 3. 任务目录与状态文件

```text
results/web_jobs/job_YYYYMMDD_HHMMSS_xxxxxxxx/
  job.json          # 唯一状态事实来源（原子写）
  request.json      # 已校验并转换为 SI 的请求
  progress.json     # 真实工况计数（原子写）
  cancel.flag       # 取消请求（存在即取消）
  log.txt           # 工作进程 stdout/stderr 与处理日志
```

结果目录：

```text
results/web_runs/run_<run_id>/     # Web 任务新结果，不覆盖历史
results/run_index.json             # 元数据索引，可随时重建
```

## 4. 执行模型

1. `JobManager.submit()` 校验请求、计算指纹、检查重复与并发、检查预算与磁盘；
2. 创建任务目录，写入 `request.json` 与 `job.json`（QUEUED）；
3. 以 `sys.executable -m jobs.worker` 启动独立进程，stdout/stderr 写入 `log.txt`；
4. 工作进程将状态置为 RUNNING，按白名单调用处理函数；
5. 处理函数在每个工况边界检查取消标志，写入真实进度；
6. 工作进程结束时写入 COMPLETED / FAILED / CANCELLED，并同步计数；
7. 管理器在读取任务时做惰性核对：超时、死进程、启动失败分别落到 TIMED_OUT / INTERRUPTED。

同一请求（任务类型 + 已校验 SI 参数）只允许一个活跃实例；并发上限默认 1。

## 5. 关键设计决策

| 决策 | 原因 |
| --- | --- |
| `job.json` 作为状态事实源 | 页面刷新、进程重启后仍可核对；避免内存状态丢失 |
| 独立子进程执行 | ngspice DLL 在进程内求解，终止进程即可终止求解；不阻塞 Web |
| 提交时统一 SI | 表单工程单位与内部计算解耦，避免单位混淆 |
| 静态 handler 映射 | 禁止用户输入触发动态导入 |
| 索引只存元数据 | 历史页快速加载；波形按需读取 |
| 结果写入 `results/web_runs` | 不触碰前八阶段历史目录 |
| 派生分析单独标记 | `performance_analysis` 的结果为 `spice_derived`，并记录父运行 |
| 判定状态独立 | 任务 COMPLETED ≠ 性能 PASS |

## 6. 异常与恢复

- 处理函数异常：写入 `log.txt` 完整堆栈，任务 FAILED，Web 进程不受影响。
- 工作进程意外退出：管理器在下一次读取时标记 INTERRUPTED，不伪造结果。
- 单任务超时：终止进程树并标记 TIMED_OUT。
- 取消：写 `cancel.flag` 后在安全点退出；管理器同时终止进程并确认退出。
- 索引损坏或版本不符：重新扫描磁盘重建，不修改运行目录。

## 7. 资源边界

并发、单任务时长、单工况时长、SPICE 调用上限、Monte Carlo 样本数、绘图点数、
磁盘余量与日志大小全部来自 `configs/job_limits.yaml` 与 `configs/web_config.yaml`，
详见 [63_job_execution_and_lifecycle.md](63_job_execution_and_lifecycle.md)。
