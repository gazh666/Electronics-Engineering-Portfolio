# 64 第六阶段最终验收

日期：2026-11-26
运行：`results/stage6/run_stage6_20261126_155147_64c696`
环境：Conda `kaifa_battery` / Python 3.11.18 / PySpice 1.5 / ngspice 34
最终结果：**20/20 工况 PASS，13/13 预登记限值 PASS，56/56 检查 PASS，12 次真实 ngspice 求解**

## 1. 预登记限值

| 指标 | 实测 | 限值 | 单位 | 判定 |
| --- | --- | --- | --- | --- |
| cc_mean_error_a | 0.00109 | 0.020 | A | PASS |
| cc_period_average_error_a | 0.00575 | 0.020 | A | PASS |
| cc_startup_overshoot_fraction | 0.0834 | 0.10 | 1 | PASS |
| cv_mean_error_v | 0.01350 | 0.020 | V | PASS |
| cv_period_average_error_v | 0.00445 | 0.020 | V | PASS |
| cc_cv_voltage_overshoot_v | 0.00207 | 0.050 | V | PASS |
| power_stage_efficiency_min_percent | 98.01 | 85.0 | % | PASS |
| power_conservation_residual_fraction | 0.00533 | 0.010 | 1 | PASS |
| phase_margin_deg | 107.22 | 45.0 | deg | PASS |
| gain_margin_db | 无相位穿越（INF） | 6.0 | dB | PASS |
| bandwidth_separation_ratio | 9.134 | 5.0 | 1 | PASS |
| soc_consistency_tolerance_ah | 0.00088 | 0.005 | Ah | PASS |
| intrinsic_solver_consistency_ppm | 4.98 | 100 | ppm | PASS |

限值来自 `configs/stage6_validation.yaml`，在正式运行前登记，本阶段未修改。

## 2. 20 个工况

| 工况 | 层次 | 关键实测 | 判定 |
| --- | --- | --- | --- |
| C01 | SPICE | 周期平均 1.0011 A，稳态电压 11.631 V，启动峰值 1.0834 A | PASS |
| C02 | SPICE | 0.600 ms 进入 CV，稳态 0.1579 A / 12.136 V，CV 误差 −13.5 mV | PASS |
| C03 | SPICE | 6.790 ms 切换，稳态 0.8457 A / 12.146 V，过冲 2.07 mV | PASS |
| C04 | SPICE | 18→16 V，稳态 0.9993 A | PASS |
| C05 | SPICE | 16→18 V，稳态 1.0001 A | PASS |
| C06 | SPICE | 18→20 V，稳态 1.0008 A | PASS |
| C07 | SPICE | 输入掉电，最大反向 130.1 mA，窗口内无锁存 | PASS（风险记录） |
| C08 | SPICE | 0.5→1.0 A，稳态 1.0057 A | PASS |
| C09 | SPICE | 1.0→0.5 A，稳态 0.4972 A | PASS |
| C10 | SPICE | 使能拉低，末电流 −5.4 µA，栅压均值 1.8e-314 V（零） | PASS |
| C11 | ECM | 293.5 s 单体 4.2503 V，组压 11.9655 V，锁存 OV | PASS |
| C12 | 软件 | 50 ℃ → charge_allowed=False | PASS |
| C13 | 软件 | NaN 测量 → measurement_valid=False，拒绝充电 | PASS |
| C14 | 行为级 | 4568.5 s COMPLETE，终止电流 0.0816 A | PASS |
| C15 | 软件 | 30 s 低电流后恢复，未误判 COMPLETE | PASS |
| C16 | ECM | 14400 s TIMEOUT，0.2 A | PASS |
| C17 | 软件 | 过压锁存后不自动重启 | PASS |
| C18 | ECM | 3949.5 s COMPLETE，SOC 极差 0.165，最高单体 4.1844 V | PASS |
| C19 | SPICE | 稳态 0.1554 A，判为 DCM，CV 误差 +15.9 mV | PASS |
| C20 | SPICE | PWM 关闭，最大反向 4.7 mA，栅压均值 0.0 V | PASS |

开关级运行目录：

| 工况 | 目录 |
| --- | --- |
| C01 | `run_stage6_20261126_155156_d5f885` |
| C02 | `run_stage6_20261126_155211_054626` |
| C03 | `run_stage6_20261126_155227_97496e` |
| C04 | `run_stage6_20261126_155239_9b8dfc` |
| C05 | `run_stage6_20261126_155252_09fc5c` |
| C06 | `run_stage6_20261126_155305_fb14ae` |
| C07 | `run_stage6_20261126_155326_3cb91c` |
| C08 | `run_stage6_20261126_155338_0c812a` |
| C09 | `run_stage6_20261126_155351_fb3201` |
| C10 | `run_stage6_20261126_155411_53b0ab` |
| C19 | `run_stage6_20261126_155442_668611` |
| C20 | `run_stage6_20261126_155500_c6071a` |

## 3. 56 项检查构成

| 分组 | 数量 | 内容 |
| --- | --- | --- |
| 配置与网表 | 10 | 保护协调、占空比可行、20 ns 步长上限、双环/前馈/冻结行为源 |
| 数值可靠性 | 6 | 50 ns 拒绝、积分冻结、PI 参考计算、跨层次对照、无反向电流、断点记录 |
| 预登记限值 | 13 | 见第 1 节 |
| 工况判定 | 20 | 12 个开关级 + 8 个非开关级 |
| 综合证据 | 7 | 20 工况全通过、求解预算、落盘完整、无预生成波形、保护阈值未变、SOC 一致性、能量闭合 |

## 4. 文档化的设计修正（限值未改）

| 项 | 原值 | 现值 | 理由 |
| --- | --- | --- | --- |
| 软启动 | 5 ms | 1 ms | 8–12 ms 窗口与 4 ms 阶跃使 CC 指标落在软启动瞬态上 |
| C11 参数 | SOC 0.55/0.62/0.72，CV 开 | SOC 0.55/0.55/0.95，CV 关 | 原参数在 12.15 V 恒压下永远不会触发 4.25 V；改为故障注入并保留负结果 |
| C16 参数 | 仅最大时间 | 增加 0.2 A、SOC 0.3 | 使 14400 s 上限成为约束，验证 TIMEOUT 路径 |
| C20 参数 | 仅输入掉电 | 增加使能拉低 | 与工况描述"PWM 关闭"一致 |

以上均为工况/设计参数，不是验收限值；13 项预登记限值未改。

## 5. 数值可靠性结论（详见 docs/55、docs/56）

1. 闭环时间步必须 ≤ 20 ns：50 ns 出现 0.1–0.4 A 伪极限环，10 ns 报
   `timestep too small`。
2. 前馈必须用滤波后的输出电压（τ=1 ms）且不乘软启动，否则形成代数正反馈或
   DCM 追赶过冲。
3. 抗饱和必须"条件积分冻结 + 反计算"；纯反计算会把 C01 恒流指令拉低约 25 mA。
4. 电流环线性化必须用电池内阻作负载（0.26 Ω），不能用 Vout/I（会把穿越频率
   低估约 40 倍）。

## 6. 测试与依赖

| 项 | 结果 |
| --- | --- |
| `pytest tests/test_stage6_*.py -q` | 50 passed |
| `pytest tests -q` | 366 passed（65.89 s） |
| `pip check` | No broken requirements found |

## 7. NOT_VERIFIED（不计入 56 项通过）

| 项 | 原因 |
| --- | --- |
| 保护 FET 断开后的电气重分布 | 网表不含保护 FET |
| 真实 BQ24610 ACFET/BATDRV 行为 | 未建模 |
| 硬件效率、温升、保护响应时间 | 无硬件 |
| NTC 开路/短路故障 | 仅注入过温与 NaN |
| 5 s 故障全清的长时行为 | 未构造 5 s 稳定恢复场景 |
| 绝对 SOC 与充电进度 | 终止 SOC 超出辨识区间 0.0106–0.5068，属外推 |
| DCM 下的小信号稳定性 | 线性化模型不适用 |
| 同步整流与开关损耗 | 器件模型简化 |

## 8. 复现

```bash
conda run -n kaifa_battery python -m scripts.stage6_validation_demo
conda run -n kaifa_battery python -m pytest tests -q
conda run -n kaifa_battery pip check
```
