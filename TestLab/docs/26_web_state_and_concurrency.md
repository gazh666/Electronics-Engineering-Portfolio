# 26 会话状态、重跑与串行任务控制

## 1. Streamlit 重跑模型

Streamlit 在每次交互时从头执行脚本。因此：

- 页面模块只定义函数与常量，不在 import 时执行测试或连接仪器；
- 所有“执行”动作只能发生在按钮/表单提交分支内；
- 页面切换、刷新、修改输入不会自动触发测试。

## 2. session_state 键

`ui/state.py` 统一管理：

| 键 | 含义 |
| --- | --- |
| `task_running` | 当前会话是否有任务 |
| `last_run_id` | 最近一次自动化运行编号 |
| `last_test_results` | 最近一次逐用例结果 |
| `last_test_summary` | 最近一次汇总 |
| `last_instrument_snapshot` | 最近一次仪器会话快照 |
| `last_performance_results` | 最近一次扫描结果 |
| `last_reliability_results` | 最近一次可靠性实验 |
| `last_error` | 最近错误文本 |
| `navigation` | 侧边导航当前页 |

约束：

- 不保存 `InstrumentManager`、驱动对象、SQLite 连接、文件句柄；
- 只保存可序列化的结果字典与标志；
- `reset_results()` 只清结果，不破坏导航。

## 3. 单进程任务锁

`ui/service.py`：

```python
_TASK_LOCK = threading.Lock()

@contextmanager
def exclusive_task():
    if not _TASK_LOCK.acquire(blocking=False):
        raise TaskBusyError(...)
    try:
        yield
    finally:
        _TASK_LOCK.release()
```

使用范围：

- 仪器发现与会话；
- 普通测试方案/自定义用例；
- 性能扫描；
- 单场景/批量可靠性实验。

特点：

- 非阻塞：已有任务时立即报错，不排队、不覆盖；
- 覆盖同一 Python 进程内的全部 Streamlit 会话；
- 不声明跨进程/多副本并发能力。

## 4. 页面执行流程

以自动化测试为例：

```text
按钮提交
  → 检查 session_state.task_running
  → begin_task()
  → service.run_test_suite(...)
      → exclusive_task()
      → InstrumentManager 上下文
      → SuiteRunner 逐条执行
      → 每条结果先持久化，再触发进度回调
      → finally 关闭输出/负载并释放资源
  → remember_test_run()
  → finally finish_task()
  → 展示结果与导出按钮
```

异常路径：

- `TaskBusyError`：提示已有任务，不启动仪器；
- 输入错误（空用例、未知方案、超 300 点）：在建立仪器连接前失败；
- 执行异常：写入 `last_error`，`finally` 仍复位 `task_running`；
- 清理失败：后端将结果标 ERROR 并强制停止，UI 显示停止原因。

## 5. 进度回调真实性

- `SuiteRunner` 在 `_persist(result)` 之后调用 `progress_callback`；
- 回调中不会预先写入 100%；
- 扫描回调在每个点完成读取与分析后触发；
- 回调异常由后端记录到 `callback_errors`，不影响清理。

测试 `test_progress_callback_is_after_persistence` 在回调内查询 SQLite，
验证 `current == 已持久化条数`。

## 6. 重复执行防护

三层防护：

1. `session_state.task_running`：同一会话提示并拒绝重复提交；
2. 进程级 `_TASK_LOCK`：跨会话仍只能有一个任务；
3. `InstrumentManager`：同一 YAML 同时只允许一个打开的实例。

AppTest 覆盖：

- 页面切换/刷新后数据库运行数不变；
- 下载按钮点击后不新增运行；
- 强制设置 `task_running=True` 时显示警告，复位后可正常执行；
- 空自定义用例提交后 `task_running` 为 False，且不创建数据库记录。

## 7. 资源清理

- 仪器使用 `with InstrumentManager(...)` 或显式 `try/finally`；
- 扫描、仪器会话结束调用 `_shutdown_bench` / `_safe_shutdown_manager`；
- 清理状态只使用 `VERIFIED_OFF / NOT_VERIFIED / NOT_APPLICABLE`；
- 关闭失败不会被改写为成功，UI 显示错误。

## 8. 局限

- 任务锁仅在单进程内有效；多进程部署需要外部协调（本阶段不实现）；
- session_state 属于单个浏览器会话，不同标签页/用户不共享“最近结果”；
- 刷新页面会丢失当前会话缓存，但数据库历史不受影响。
