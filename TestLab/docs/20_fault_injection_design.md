# 20 故障注入设计（阶段八）

> 本阶段所有故障均为**模拟故障**，由 `PyVISA-sim` + `VirtualDUT` 受控产生，
> 不是真实硬件断线、真实仪器超时或真实保护动作。不得据此声明真实设备的
> MTBF/MTTR、抖动容限或安全认证结论。

## 1. 目标与边界

阶段八要回答的问题是：

1. 系统能否在**明确的时间点、明确的位置、明确的次数**注入故障？
2. 故障是否被记录、分类、有限重试或安全停止，而不是静默吞掉？
3. 发生 FAIL/ERROR 时，结果是否仍然真实、可复现、可追溯？
4. 关闭故障注入后，阶段七行为是否完全不变？

不在本阶段范围：

- 真实仪器通信抖动/断线的概率建模；
- 无限重试、自动重连风暴；
- 把注入故障当成真实故障写入“硬件可靠性”结论；
- 真实设备的保护动作验证。

## 2. 包结构

```
reliability/
├── exceptions.py            注入异常（同时继承仪器异常）
├── fault_models.py          FaultType / FaultTarget / FaultScenario / YAML 加载
├── fault_injector.py        确定性注入器 + 测量视图适配
├── error_classifier.py      异常分类（按类型/状态码，不按字符串）
├── retry_policy.py          RetryPolicy / RetryExecutor（有限重试）
├── fault_logger.py          JSONL 事件日志（NaN/Infinity 显式字符串）
└── reliability_analyzer.py  统计口径与实验判定
```

旧的 `engine/fault_injector.py`（`FaultSpec`）只服务于
`ScenarioTestRunner` / `scripts.demo` 的旧版回归，不是阶段八主实现。

## 3. 故障场景模型

`configs/fault_scenarios.yaml` 每个场景包含：

| 字段 | 含义 |
| --- | --- |
| `id` | 唯一编号，例如 `F001` |
| `name` | 名称 |
| `fault_type` | `TIMEOUT` / `DISCONNECT` / `INVALID_RESPONSE` / `NAN_VALUE` / `INFINITY_VALUE` / `VOLTAGE_OFFSET` / `CURRENT_OFFSET` / `SHUTDOWN_FAILURE` |
| `target` | `instrument_query` / `instrument_write` / `model_measurement` / `cleanup` |
| `operation` | SCPI 命令（`VOLT?`、`OUTP 0`）或测量字段（`vout`、`iin`） |
| `device` | 可选目标仪器编号（`PS001` 等） |
| `case_id` | 可选限定用例编号 |
| `trigger_at` | 第几次匹配开始注入（>=1） |
| `occurrences` | 最大注入次数（>=1，绝不无限） |
| `offset` | 仅偏移类故障使用，必须非零 |
| `enabled` | 场景是否启用 |

严格校验：

- 未知字段、未知枚举值、非有限数值、布尔伪装成整数一律拒绝；
- 测量故障只能作用于 `vin/iin/vout/iout`；
- `VOLTAGE_OFFSET` 只能作用于 `vin/vout`，`CURRENT_OFFSET` 只能作用于
  `iin/iout`；
- `SHUTDOWN_FAILURE` 只能作用于 `cleanup`；
- `INVALID_RESPONSE` 只能作用于仪器查询；
- 同一时刻会命中同一操作的两个启用场景视为**冲突**，注入器构造时直接
  拒绝。例如 `F001` 与 `F002` 都注入 `PS001:VOLT?`，因此一次运行只能
  选择其中一个。

## 4. 注入点与顺序

| 阶段 | 钩子 | 支持类型 |
| --- | --- | --- |
| 仪器查询 | `before_query(command, device)` | TIMEOUT / DISCONNECT / INVALID_RESPONSE |
| 仪器写入 | `before_write(command, device)` | TIMEOUT / DISCONNECT |
| 模型测量 | `transform_measurement(field, value)` | NAN / INFINITY / 偏移 |
| 清理 | `before_cleanup(operation, device)` | SHUTDOWN_FAILURE / TIMEOUT / DISCONNECT |

F009 只作用于 `cleanup:OUTP 0`，不会命中测试开始阶段的
`psu.set_output(False)`，因为两者使用不同的钩子。

注入计数规则：

- 只有 `target + operation + device + case_id` 都匹配才计数；
- `trigger_at` 是匹配次数，不是全局调用次数；
- `occurrences` 用尽后不再注入；
- 每个用例创建独立注入器，状态不跨运行共享。

## 5. 测量故障的两类视图

`apply_measurement_faults(result, injector, consistent=...)` **不修改原始
`DUTResult`**，而是用 `dataclasses.replace` 生成独立视图，并把
`source` 标记为 `fault_injected_model`。

### 5.1 一致性偏移（默认，`consistent=True`）

F007/F008 使用该模式：

- 先对 `vout` / `iout` 施加偏移；
- 按原始效率重算 `pout = vout * iout`、`pin = pout / efficiency`、
  `iin = pin / vin`、`power_loss = pin - pout`；
- 数据质量检查仍然全部执行，因此结果不是“非法数据”，而是“数据自洽但
  超出工程限值”，最终为业务 FAIL。

### 5.2 不一致视图（`consistent=False`）

只改测量字段，保留原始 `pin/pout/power_loss/efficiency`，用于验证数据
质量模块会识别功率关系错误并判 ERROR。NaN/Infinity 无法参与自洽重算，
始终走不一致视图，绝不会被替换成正常值。

## 6. 默认关闭与可复现

- `TestRunner` 默认不创建注入器；
- 只有显式调用 `configure_reliability(...)`（或构造时传入场景）才启用；
- 不使用随机数，所有触发次数与偏移量固定；
- 普通测试路径不附加故障注入，阶段七基线与回归测试保持不变。

## 7. 限制

- 真实仪器超时后通信缓冲区可能处于不确定状态，本项目的“安全重试”
  只对当前 PyVISA-sim 模拟后端成立；
- 断开故障只会让**当前会话**失效，不模拟重连成功；
- 无法确认关闭时只记录 `NOT_VERIFIED`，不推断硬件实际带电状态。
