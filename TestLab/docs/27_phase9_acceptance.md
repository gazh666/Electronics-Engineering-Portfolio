# 27 第九阶段验收记录

验收环境：Windows，conda 环境 `kaifa`，Python 3.11.18。
全部数据来自 PyVISA-sim 与 VirtualDUT 行为模型，属 SIMULATION。

## 1. 依赖与基线

| 项目 | 结果 |
| --- | --- |
| `python --version` | 3.11.18 |
| streamlit | 1.67.0 |
| plotly | 7.1.0 |
| pandas | 3.1.1 |
| pytest | 9.2.0 |
| `pip check` | `No broken requirements found.` |
| 阶段八基线 | 465 passed |
| 第九阶段后 | **518 passed** |

新增 53 项测试：

- `tests/test_ui_service.py`：27 项；
- `tests/test_ui_formatters.py`：9 项；
- `tests/test_ui_state.py`：7 项；
- `tests/test_streamlit_app.py`：10 项。

## 2. 应用启动

```powershell
& "C:\\Users\\<user>\.conda\envs\kaifa\python.exe" -m streamlit run app.py `
  --server.address 127.0.0.1 --server.port 8501 --server.headless true
```

实测：

- `http://127.0.0.1:8501/_stcore/health` 返回 `ok`；
- 首页 HTTP 200；
- 浏览器打开后左侧显示 6 个导航项，无 Streamlit 异常。

截图：

- `assets/screenshots/dashboard.jpg`
- `assets/screenshots/automation_suite005.jpg`

## 3. 页面验收

| 页面 | 验收方式 | 结果 |
| --- | --- | --- |
| 运行概览 | 浏览器 + AppTest | 真实历史、状态图、类别统计正常 |
| 仪器控制 | AppTest 六页渲染 + 服务层仪器测试 | 无异常；发现/设置/回读/关闭通过 |
| 自动化测试 | 浏览器执行 SUITE005 + AppTest | 5/5 PASS，导出按钮出现 |
| 性能扫描 | AppTest 渲染 + 超限阻止 + 服务层扫描 | 5 点负载扫描正常，300 点上限生效 |
| 可靠性验证 | AppTest 渲染 + 服务层 F001/F002/F007 | 业务状态与实验结论分离显示 |
| 历史记录 | AppTest + 服务层筛选/导出 | 筛选、详情、导出通过 |

> 说明：浏览器视觉验证覆盖运行概览与自动化测试两页；其余页面通过
> Streamlit AppTest 与真实服务调用验证，未声称已完成人工视觉走查。

## 4. 八个端到端场景

| # | 场景 | 实际结果 |
| --- | --- | --- |
| 1 | 正常 12 V / 1 A 与 2 A | TC001 + TC004 全部 PASS |
| 2 | SUITE005 | 5/5 PASS，状态 COMPLETED |
| 3 | 负载扫描 0–2 A（5 点） | 5 点全部 NORMAL，清理 `VERIFIED_OFF` |
| 4 | F001 单次查询超时 | 业务 PASS，重试 1 次，恢复 True，实验 PASS |
| 5 | F002 持续查询超时 | 业务 ERROR，重试 2 次，耗尽 True，实验 PASS |
| 6 | F007 电压偏移 | 业务 FAIL，观测 Vout 4.68 V，实验 PASS |
| 7 | 历史与导出 | 5 条结果；CSV 6 行（含表头）；JSON/HTML 正常 |
| 8 | 页面切换/刷新 | 6 页无异常；运行数 33 → 33，未重复执行 |

输出：`E2E_RESULT PASS`。

## 5. 关键行为验证

### 5.1 进度与持久化

`test_progress_callback_is_after_persistence` 在回调内查询 SQLite：

- 第 1 次回调时数据库已有 1 条；
- 第 2 次回调时数据库已有 2 条；
- 回调顺序为 `(1,2,1) → (2,2,2)`。

### 5.2 状态与重复执行

- 页面加载不创建数据库、不执行测试；
- 页面切换与刷新后运行数不变；
- 点击下载按钮不新增运行；
- `task_running=True` 时显示警告，复位后可正常执行；
- 自定义用例为空时在建立仪器连接前失败。

### 5.3 仪器清理

- 电源会话结束回读 `OUTP? = 0`；
- 负载会话结束回读 `INP? = 0`；
- 万用表无输出控制，清理状态为 `NOT_APPLICABLE`；
- 非法负载操作（CV 模式设置电流）返回错误，但仍完成清理。

### 5.4 历史与导出

- SQLite 查询全部参数化；
- 历史页只读，无重新执行按钮；
- CSV/JSON/HTML 在内存生成，导出内容来自当前运行；
- 未知运行编号导出直接报错。

## 6. 最终回归（阶段九完成后）

| 命令 | 结果 |
| --- | --- |
| `python -m pytest tests -q` | 518 passed |
| `python -m pip check` | `No broken requirements found.` |
| `python -m scripts.run_test_suite --suite SUITE005` | 5/5 PASS，退出码 0 |
| `python -m scripts.reliability_demo` | 10/10 实验通过，退出码 0 |

可靠性回归摘要：

```text
场景 10 · 实验通过 10 · 失败 0
故障注入 11 次 · 重试 3 次 · 恢复率 50.0%
清理未确认 2 · 强制停止 1
JSONL=42 · SQLite=42（一致）
F002/F003/F005/F009 = ERROR；F007/F008 = FAIL
```

## 7. 与阶段八对比

| 项目 | 阶段八 | 阶段九 |
| --- | --- | --- |
| 测试入口 | CLI 脚本 | Streamlit 六页平台 + CLI 保留 |
| 测试总数 | 465 | 518 |
| 仪器操作 | 脚本内部 | 仪器页单次会话，安全关闭 |
| 进度 | 命令行日志 | 持久化后真实回调 |
| 性能扫描 | CLI/HTML | 交互式扫描 + Plotly 图表 |
| 可靠性 | 演示脚本 | 单场景/全部场景 + 事件时间线 |
| 历史 | SQLite CLI 查询 | 筛选、详情、配置快照、导出 |
| 并发 | 单进程串行 | 单进程串行 + UI 任务标志 |

阶段八的 `SUITE005`、F001/F002/F007 行为与结论保持不变。

## 8. 已知限制

1. 任务锁只覆盖单进程；多进程/多副本部署没有分布式协调。
2. `session_state` 仅属于当前浏览器会话，刷新会丢失“最近结果”缓存；
   数据库历史不受影响。
3. DMM 的 SCPI 读数是固定模拟值（`static_mock`），不代表真实测量。
4. 未接入真实硬件；全部结论不能用于真实产品认证。
5. 浏览器视觉验收只覆盖运行概览与自动化测试页；其余页面通过
   AppTest 与服务层测试验证。
6. 本阶段不包含 Docker、Linux 部署、综合报告系统与 PowerLab。

## 9. 手工确认项

- 手动打开 `http://127.0.0.1:8501`，确认布局在目标分辨率下无错位；
- 检查历史记录中既有阶段七/八运行仍然可读；
- 确认导出的 HTML 在浏览器中可打开；
- 确认目标机器允许 8501 端口（如被占用可改用 8502）。
