# 16 自动化测试执行引擎

本文件描述阶段七的 `TestRunner` 与 `SuiteRunner`：
如何设置工况、读取模型、判定状态、处理异常与清理资源。

## 1. 分层

```
scripts/run_single_test.py / run_test_suite.py
        │
engine/suite_runner.py  ── 方案编排、停止条件、SKIP 补全、汇总
        │
engine/test_runner.py   ── 单用例：设置 -> 校验 -> 测量 -> 判定 -> 清理
        │
bench/virtual_test_bench.py ── 读取 SCPI 设置并调用 VirtualDUT
        │
instrument_manager / instruments/*
```

引擎不拼接 SCPI 字符串，也不做数据质量算法；这些分别属于驱动层与
`analysis/` 层。

## 2. 单用例执行流程

1. `case.enabled == false` → 立即 SKIP，**不访问任何仪器**；
2. 先关负载输入、关电源输出，回到安全状态；
3. 下发 `vin / input_current_limit / CC 电流`，再打开输出与负载输入；
4. 核对回读值：电压、限流、负载电流、模式、输出/输入开关；
   任一不一致 → `SetpointMismatchError`，结果 ERROR，不继续测量；
5. `bench.read_state()` 读取 SCPI 设置并调用行为模型，得到 `DUTResult`；
6. `PerformanceAnalyzer.analyze()` 做数据质量检查；
   `quality_status != VALID` → ERROR，不进入限值判定；
7. 检查项：
   - `dut_state`：实际状态 vs 预期状态；
   - `case.limits` 中的每个指标：实际值 vs `[min, max]`；
8. 汇总 `ERROR > FAIL > PASS`；无检查项返回 ERROR；
9. `finally` 中关闭负载与电源输出并回读验证；失败则结果 ERROR，
   并置 `cleanup_failed=True`，由方案层强制停止。

## 3. 判定语义

| 场景 | 结果 |
| --- | --- |
| 状态符合预期 + 限值全部满足 | PASS |
| 状态不符 / 任一限值越界 | FAIL |
| 数据质量 ERROR、通信异常、设置不一致、限制值缺失、清理失败 | ERROR |
| `enabled: false` 或方案提前停止 | SKIP（写明原因） |

保护状态（如 `OVERCURRENT`）符合预期属于 PASS；保护时输出为 0，
因此保护用例应把 `vout` 限值设为 `0–0`。

## 4. 方案执行

- 用例按方案声明顺序执行，不按 YAML 中用例出现顺序；
- 每执行一条立即持久化（JSONL/CSV/SQLite），然后触发进度回调；
- 进度回调异常只记录，不影响仪器清理与后续执行；
- 停止条件：`stop_on_fail`、`stop_on_error`，以及清理失败（强制）；
- 未执行用例生成 SKIP 记录，原因形如
  `未执行: TC001 判定 FAIL，按方案停止`；
- 用户 `Ctrl+C` → 方案 `ABORTED`，已完成结果保留；
- 存储失败 → 方案 `ERROR`，但不会丢弃内存中的结果。

方案状态 `COMPLETED` 只表示流程正常结束，不代表全部 PASS；通过率必须
结合 `pass_rate / completion_rate / planned_pass_rate` 三个口径查看。

## 5. 串行约束

- 引擎只支持串行执行，不声明线程安全；
- 全流程只使用 `InstrumentManager` 打开一次仪器；
- `VirtualDUT` 是确定性模型，相同设置得到相同结果（不含随机数）。

## 6. 局限

- 设置校验使用容差 `1e-6`，仅用于吸收浮点误差，不代表测量不确定度；
- 当前不实现并行执行、重试策略与断点续跑；
- 所有结果来自虚拟仪器与行为模型，不能作为真实硬件认证依据。
