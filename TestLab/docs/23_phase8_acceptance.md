# 23 阶段八验收记录

## 1. 环境

- 工作目录：`TestLab/`
- 解释器：`C:\\Users\\<user>\.conda\envs\kaifa\python.exe`
- 数据后端：`PyVISA-sim` + `VirtualDUT`（模拟）
- 上游源码：未修改 PyVISA / PyVISA-sim

## 2. 基线

| 项目 | 结果 |
| --- | --- |
| 阶段七 pytest | 382 passed |
| 阶段八 pytest | **465 passed**（新增 83 项） |
| `pip check` | No broken requirements found |
| 普通回归 `SUITE005` | 5/5 PASS，退出码 0 |
| 阶段七旧 demo | `scripts.demo` 12/12 PASS，退出码 0 |

## 3. 验收命令

```powershell
conda run -n kaifa python -m pytest -q
conda run -n kaifa python -m pip check
conda run -n kaifa python -m scripts.run_test_suite --list
conda run -n kaifa python -m scripts.run_test_suite --suite SUITE005
conda run -n kaifa python -m scripts.fault_injection_demo --list
conda run -n kaifa python -m scripts.fault_injection_demo --scenario F001
conda run -n kaifa python -m scripts.fault_injection_demo --scenario F002
conda run -n kaifa python -m scripts.fault_injection_demo --scenario F003
conda run -n kaifa python -m scripts.fault_injection_demo --scenario F004
conda run -n kaifa python -m scripts.fault_injection_demo --scenario F005
conda run -n kaifa python -m scripts.fault_injection_demo --scenario F007
conda run -n kaifa python -m scripts.fault_injection_demo --scenario F009
conda run -n kaifa python -m scripts.retry_demo --no-sleep
conda run -n kaifa python -m scripts.reliability_demo
```

## 4. 实际结果

### 4.1 单项故障演示

| 场景 | 业务状态 | 重试 | 恢复 | 清理 | 实验 |
| --- | --- | --- | --- | --- | --- |
| F001 | PASS | 1 | 是 | VERIFIED_OFF | PASS |
| F002 | ERROR | 2 | 否 | VERIFIED_OFF | PASS |
| F003 | ERROR | 0 | 否 | NOT_VERIFIED | PASS |
| F004 | ERROR | 0 | 否 | VERIFIED_OFF | PASS |
| F005 | ERROR | 0 | 否 | VERIFIED_OFF | PASS |
| F007 | FAIL | 0 | 否 | VERIFIED_OFF | PASS |
| F009 | ERROR | 0 | 否 | NOT_VERIFIED | PASS |

所有命令退出码均为 0；预期 ERROR/FAIL 的业务结果没有被改写。

### 4.2 综合可靠性实验

`results/reliability/run_20261124_084737_81c229fb/`：

| 指标 | 实际值 |
| --- | --- |
| 场景数 | 10（NONE + F001-F009） |
| 实验通过 / 失败 | 10 / 0 |
| 故障注入次数 | 11 |
| 重试次数 | 3 |
| 恢复率 | 50.0%（2 个可重试操作，1 个恢复） |
| 清理未确认 | 2（F003、F009） |
| 强制停止 | 1（F009 后续用例 SKIP） |
| JSONL 事件数 | 42 |
| SQLite 事件数 | 42 |
| 存储一致性 | PASS |

### 4.3 SQLite 抽查

- `fault_events` 表存在，`event_id` 主键、`run_id` 外键；
- 按 `run_id` 查询：每个场景的事件数与 JSONL 一致；
- `get_recovered_events`：F001 返回 1 条；
- `get_retry_exhausted_events`：F002 返回耗尽记录；
- `get_fault_events_by_type("TIMEOUT")` 返回注入事件；
- 旧数据库可直接打开，迁移可重复执行。

### 4.4 产物

- `scenario_results.csv`
- `fault_events.jsonl`
- `retry_statistics.json`
- `reliability_summary.json`
- `reliability_report.html`
- `execution.log`
- 5 张 SVG 图表

## 5. 逐项验收

| # | 检查项 | 结果 |
| --- | --- | --- |
| 1 | 普通测试零回归 | 465 passed |
| 2 | 故障注入默认关闭 | 通过 |
| 3 | 注入次数确定性 | 通过（trigger_at/occurrences） |
| 4 | 单次超时恢复 | F001 重试 1 次后 PASS |
| 5 | 持续超时耗尽 | F002 ERROR，重试 2 次 |
| 6 | 断开不重试且会话失效 | F003 通过 |
| 7 | 非法响应不重试 | F004 通过 |
| 8 | NaN/Infinity 数据质量 ERROR | F005/F006 通过 |
| 9 | 一致性偏移限值 FAIL | F007/F008 通过 |
| 10 | 不一致视图数据质量 ERROR | 通过 |
| 11 | 原始 DUTResult 不变 | 通过 |
| 12 | 故障数据来源标记 | `fault_injected_model` |
| 13 | 清理失败强制停止 | F009 通过 |
| 14 | SKIP 原因记录 | 通过 |
| 15 | 原始异常不被清理异常覆盖 | F003 通过 |
| 16 | JSONL 事件可解析 | 通过 |
| 17 | SQLite 迁移与查询 | 通过 |
| 18 | 按 run_id 关联事件与结果 | 通过 |
| 19 | 场景间无状态污染 | 通过 |
| 20 | 用户取消仍释放资源 | KeyboardInterrupt 测试通过 |
| 21 | 重试恢复不绕过限值 | 通过 |
| 22 | 业务 ERROR 与实验通过分离 | F002 通过 |
| 23 | 日志写入失败不阻断清理 | 通过 |

## 6. 未实现与限制

- 未开发阶段九 Streamlit 可靠性看板；
- 未开发阶段十部署；
- 未修改 PyVISA / PyVISA-sim 源码；
- 真实设备 MTBF/MTTR、通信抖动概率、自动重连均不在本阶段范围；
- 所有结论仅适用于模拟环境。
