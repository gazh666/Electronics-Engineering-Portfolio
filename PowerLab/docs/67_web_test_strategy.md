# 67 Web 测试策略

## 1. 测试分层

| 层级 | 对象 | 是否真实 SPICE | 主要文件 |
| --- | --- | --- | --- |
| Python 单元测试 | 状态模型、注册表、进度、预算、取消、索引、结果读取 | 否 | `tests/test_job_*.py`、`tests/test_result_*.py` |
| 服务/导出测试 | CSV/JSON/HTML/Markdown 生成 | 否（使用真实结构的数据对象） | `tests/test_ui_export.py` |
| 工作进程测试 | `jobs.worker.run_job()` 状态机与日志 | 否（替换 handler） | `tests/test_job_worker.py` |
| 管理器测试 | 提交、重复、并发、超时核对、取消 | 否（替换进程启动） | `tests/test_job_manager.py` |
| AppTest | 8 个页面渲染与导航 | 否（读取磁盘历史结果） | `tests/test_app_smoke.py` |
| 真实 SPICE 集成 | 6 类任务真实提交并完成 | 是 | `scripts/web_smoke_demo.py` + 手工任务 |
| HTTP/浏览器验证 | Streamlit 健康检查与页面加载 | 否 | `results/stage9/web_health.json`、截图 |

## 2. 新增测试文件与实际数量

2026-11-25 实际收集结果（`pytest --collect-only`）：

| 文件 | 测试数 |
| --- | --- |
| `tests/test_web_config.py` | 11 |
| `tests/test_job_models.py` | 21 |
| `tests/test_job_registry.py` | 43 |
| `tests/test_job_manager.py` | 14 |
| `tests/test_job_worker.py` | 7 |
| `tests/test_job_progress.py` | 9 |
| `tests/test_cancellation.py` | 11 |
| `tests/test_resource_budget.py` | 11 |
| `tests/test_result_index.py` | 11 |
| `tests/test_result_repository.py` | 10 |
| `tests/test_ui_form_validation.py` | 17 |
| `tests/test_ui_export.py` | 13 |
| `tests/test_ui_navigation.py` | 6 |
| `tests/test_app_smoke.py` | 11 |
| **合计** | **195** |

全量回归：`854 passed in 47.96s`（第九阶段开始前基线为 659 passed）。

## 3. 各层能证明什么

### 3.1 单元测试

- Job ID 格式、状态集合、`job.json` 原子读写；
- 6 个任务类型与 6 个模型的参数校验；
- 工程单位 → SI 的转换正确性（ms/ns/µH/µF/kHz）；
- 扫描值数量、占空比范围、时间步顺序等跨字段约束；
- 进度只在真实工况计数存在时给出比例；
- 取消标志、进程存活判断、非法 PID 拒绝；
- 预算、profile 上限与磁盘检查；
- 索引构建、去重、分页、版本不符重建；
- 波形按列读取、降采样保留极值、数据来源判定。

### 3.2 工作进程与管理器

- worker 在成功、异常、取消三种路径上写入正确终态；
- 异常堆栈落盘，任务不会停留在 RUNNING；
- 管理器拒绝重复指纹与并发超限；
- 超时、死进程、启动失败在惰性核对中落到 TIMED_OUT / INTERRUPTED；
- 日志超过上限后停止追加。

这些测试**使用假 handler / 假进程**，证明的是编排逻辑，不是 SPICE 求解。

### 3.3 AppTest

`streamlit.testing.v1.AppTest` 以真实脚本运行 `app.py`，逐页设置
`session_state["page"]`。11 个测试覆盖 8 个页面、默认首页、footer 的
simulation-only 声明、未知页面回退。AppTest 不产生真实浏览器渲染，
也不能发现 CSS/截图层面的问题。

### 3.4 真实 SPICE 集成

2026-11-25 通过 `JobManager.submit()` 真实提交并等待完成：

| 任务类型 | Job ID | 结果 |
| --- | --- | --- |
| `circuit_simulation`（分压） | `job_20261125_175754_7c9cfecb` | COMPLETED |
| `circuit_simulation`（非理想 Buck） | `job_20261125_175819_acecc749` | COMPLETED |
| `parameter_sweep` | `job_20261125_180902_3c0c292e` | COMPLETED |
| `numerical_validation` | `job_20261125_180908_b377b668` | COMPLETED |
| `monte_carlo`（5 样本） | `job_20261125_180922_7ac3b245` | COMPLETED |
| `closed_loop_experiment` | `job_20261125_180946_fcad3ab2` | COMPLETED |
| `performance_analysis`（派生） | `job_20261125_181000_21ea3429` | COMPLETED |

`scripts/verify_web.py` 另外检查依赖版本、关键文件、白名单、预算、索引构建、
结果目录可写与首页 AppTest，实际输出 `PASS (18/18)`。

### 3.5 HTTP 与浏览器

- `GET http://127.0.0.1:8502/_stcore/health` → `200 ok`；
- `GET /` → `200`，7,863 字节；
- 浏览器实测首次发现 `pyarrow 26.0.1` 与 NumPy 1.26.4 不兼容导致表格渲染异常；
  将 `pyarrow` 固定为 `17.0.0` 后复验，仪表盘与运行列表正常，无异常文本；
- 截图：`results/stage9/screenshots/powerlab_dashboard_refreshed.jpg`、
  `results/stage9/screenshots/powerlab_final.jpg`。

## 4. 尚未验证

| 项目 | 状态 | 原因 |
| --- | --- | --- |
| 真实求解中的取消 | NOT_VERIFIED | 单元级验证通过，未在长时间 SPICE 求解中实测 |
| 3600 s 单任务超时 | NOT_VERIFIED | 未运行超长任务 |
| Web 重启时任务仍在运行 | NOT_VERIFIED | 代码路径存在，未做进程级演练 |
| extended profile | NOT_VERIFIED | 配置默认禁用 |
| 硬件实测对照 | NOT_VERIFIED | 项目无硬件测量数据 |
| 多浏览器/响应式视觉验收 | NOT_VERIFIED | 仅一次桌面浏览器验证 |
| Monte Carlo >30 样本 | 不适用 | 预算拒绝 |

## 5. 运行命令

```powershell
conda run -n kaifa_power python -m pytest tests -q
conda run -n kaifa_power python -m scripts.verify_web
conda run -n kaifa_power python -m scripts.web_smoke_demo --model nonideal_buck --end-ms 1
conda run -n kaifa_power python -m streamlit run app.py --server.port 8502
```
