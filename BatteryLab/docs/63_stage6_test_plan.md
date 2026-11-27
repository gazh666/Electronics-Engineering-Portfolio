# 63 第六阶段测试计划与运行方式

## 1. 层次与预算

| 层 | 内容 | 预算 |
| --- | --- | --- |
| 分析/配置 | 纯 Python | 秒级 |
| 平均模型 | 显式欧拉 20 µs | 秒级 |
| ECM 长时 | 0.5 s 步长，最多 14400 s | 10–30 s/例 |
| 开关级 | 真实 ngspice，20 ns，8–12 ms | 12 次求解，每次约 10–20 s |
| 最终验收 | 20 工况 + 56 项检查 | 小于 45 min |

预登记值：最多 80 次开关级求解、单例 ≤ 180 s、总运行 ≤ 45 min。
最终验收实际使用 12 次开关级求解。

## 2. 单元/集成测试（50 项）

| 文件 | 数量 | 覆盖 |
| --- | --- | --- |
| `tests/test_stage6_config.py` | 7 | 配置、保护协调、20 工况、步长上限 |
| `tests/test_stage6_pi_antiwindup.py` | 7 | 冻结判据、反计算、离散稳定性 |
| `tests/test_stage6_charging_metrics.py` | 5 | PWM 周期平均、CC/CV 指标、建立时间 |
| `tests/test_stage6_charging_energy.py` | 5 | ZOH/梯形积分、反向电量、效率 |
| `tests/test_stage6_cc_cv_transition.py` | 4 | 切换识别、分阶段电量 |
| `tests/test_stage6_loop_analysis.py` | 4 | 被控对象、裕度、带宽分离、无穿越 |
| `tests/test_stage6_charging_validation.py` | 6 | 未登记指标拒绝、无穷裕度、限值收紧检测 |
| `tests/test_stage6_averaged_model.py` | 6 | CC/CV、BMS 禁止、步长与目标校验 |
| `tests/test_stage6_integration.py` | 6 | 网表行为源、步长守卫、PWL、真实 SPICE 冒烟 |

运行：

```bash
conda run -n kaifa_battery python -m pytest tests/test_stage6_*.py -q
conda run -n kaifa_battery python -m pytest tests -q
```

2026-11-26 实测：第六阶段 50 项通过；全仓 366 项通过（65.9 s）。

## 3. 实验脚本（11 个）

| 脚本 | 内容 | 是否开关级 |
| --- | --- | --- |
| `stage6_theory_demo.py` | 设计点、参数扫描、平均模型趋势 | 否 |
| `stage6_open_loop_demo.py` | 开环功率级 3 个占空比 | 是（3 次） |
| `stage6_current_loop_demo.py` | 电流内环 1 A/0.5 A/关断 | 是（3 次） |
| `stage6_cascade_cccv_demo.py` | C01–C03 | 是（3 次） |
| `stage6_input_transient_demo.py` | C04–C07 | 是（4 次） |
| `stage6_reference_transient_demo.py` | C08–C10、C19、C20 | 是（5 次） |
| `stage6_loop_analysis_demo.py` | 裕度与 12 点整定网格 | 否 |
| `stage6_efficiency_demo.py` | C01 损耗与效率 | 是（1 次） |
| `stage6_long_charge_demo.py` | C14、C16 | 否 |
| `stage6_protection_gating_demo.py` | C11–C13、C15、C17、C18 | 否 |
| `stage6_validation_demo.py` | 20 工况 + 56 项检查 | 是（12 次） |

每个脚本都写入 `results/stage6/run_stage6_<时间戳>_<哈希>/`，包含
`summary.json`；开关级工况另有 `circuit.cir`、`waveform.csv`、
`config_snapshot.json`。

## 4. 失败处理约定

- 预登记限值不达标：保留 FAIL，写进 docs/64，不放宽；
- 未测到：记 NOT_MEASURED，不计入通过；
- 求解器报错或步长过大：直接抛错，不降低步长"凑结果"；
- 保护许可为 False：拒绝运行，不伪造 `charge_allowed=True`。

## 5. 环境

| 项 | 版本/说明 |
| --- | --- |
| Conda 环境 | `kaifa_battery` |
| Python | 3.11.18 |
| PySpice | 1.5 |
| ngspice | 34（无独立 CLI，由 PySpice 调用） |
| 日期 | 2026-11-26 |
