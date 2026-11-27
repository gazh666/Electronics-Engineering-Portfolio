# 21 通信异常分类与有限重试

## 1. 异常分类

分类依据是**异常类型与 PyVISA 状态码**，不是异常字符串匹配。

| 分类 | 典型异常 | 是否安全重试 |
| --- | --- | --- |
| `TRANSIENT_COMMUNICATION` | `InstrumentTimeoutError`、`CommunicationTimeoutError`、VISA `error_timeout` | 是（仍需满足白名单与只读条件） |
| `DEVICE_DISCONNECTED` | `InstrumentSessionLostError`、`DeviceDisconnectedError`、`InstrumentNotConnectedError` | 否 |
| `INVALID_DATA` | `InstrumentResponseError`、`InvalidResponseError` | 否（本阶段不允许配置为可重试） |
| `CONFIGURATION_ERROR` | 驱动层 `ValueError` / `TypeError` | 否 |
| `SHUTDOWN_ERROR` | `UnsafeShutdownError` | 否 |
| `UNKNOWN_ERROR` | 其他异常 | 否 |

数值解析失败在仪器基类中已被转换为 `InstrumentResponseError`，不会落入
`ValueError` 配置错误分支。

## 2. 会话失效

`BaseInstrument` 收到 `InstrumentSessionLostError` 后：

1. 标记 `session_invalid = True`；
2. 后续 `query` / `write` 直接抛出 `InstrumentNotConnectedError`；
3. 不自动重连、不复用旧会话；
4. 清理阶段无法关闭输出时记录 `NOT_VERIFIED`，不声称已关闭。

断开故障（F003）因此会得到业务 ERROR、清理 `NOT_VERIFIED`，并且
`InstrumentManager.close()` 的安全关断也会留下失败记录。

## 3. 重试策略

`configs/retry_policy.yaml`：

```yaml
retry:
  enabled: true
  max_attempts: 3
  initial_delay_seconds: 0.1
  backoff_multiplier: 2.0
  max_delay_seconds: 1.0
  retryable_categories: [TRANSIENT_COMMUNICATION]
  allowed_query_commands: ["*IDN?", "VOLT?", "CURR?", "OUTP?", "INP?", "MODE?"]
  retry_writes: false
  retry_invalid_data: false
  retry_failed_test: false
  retry_shutdown_failure: false
```

约束：

- `max_attempts` 是总尝试次数（含第一次），最大 10；
- 退避时间 `min(initial * multiplier^(n-1), max_delay)`，不会无限增长；
- 只有 `retry_safe=True` 且命令在白名单内才允许重试；
- 写入默认不重试，即使异常分类是超时；
- 断开、非法数据、配置错误、未知异常、清理失败均不重试；
- `KeyboardInterrupt` 不参与重试，直接向上传播，但 `finally` 仍执行清理。

## 4. 事件

| 事件 | 含义 |
| --- | --- |
| `FAULT_INJECTED` | 人为故障已注入 |
| `ATTEMPT_FAILED` | 一次尝试失败（含分类） |
| `RETRY_SCHEDULED` | 已安排下一次重试（含延迟） |
| `RECOVERED` | 重试后成功 |
| `RETRY_EXHAUSTED` | 达到总尝试上限 |
| `TEST_ABORTED` | 清理失败导致强制停止 |
| `CLEANUP_STARTED` / `CLEANUP_FAILED` / `CLEANUP_COMPLETED` | 清理生命周期 |

事件在发生瞬间写入 JSONL，而不是任务结束后补造。

## 5. 场景预期

| 场景 | 预期业务结果 | 重试 | 恢复 | 清理 |
| --- | --- | --- | --- | --- |
| NONE | PASS | 0 | 否 | VERIFIED_OFF |
| F001 单次超时 | PASS | 1 | 是 | VERIFIED_OFF |
| F002 持续超时 | ERROR | 2 | 否，耗尽 | VERIFIED_OFF |
| F003 断开 | ERROR | 0 | 否 | NOT_VERIFIED |
| F004 非法响应 | ERROR | 0 | 否 | VERIFIED_OFF |
| F005 NaN | ERROR | 0 | 否 | VERIFIED_OFF |
| F006 Infinity | ERROR | 0 | 否 | VERIFIED_OFF |
| F007 电压偏低 | FAIL | 0 | 否 | VERIFIED_OFF |
| F008 电流偏移 | FAIL | 0 | 否 | VERIFIED_OFF |
| F009 关闭失败 | ERROR | 0 | 否 | NOT_VERIFIED，强制停止 |

业务结果与实验结论分开：F002 的业务结果是 ERROR，但“系统正确识别持续
超时并停止”属于可靠性实验通过，不能把业务 ERROR 改写为 PASS。

## 6. 限制

- 真实仪器超时后是否可安全重试取决于设备协议与缓冲区状态，本策略只
  证明模拟后端行为；
- 不实现自动重连、错误队列清空、SCPI 状态寄存器恢复；
- 不实现“失败测试自动重跑”，业务 FAIL 不会因重试变成 PASS。
