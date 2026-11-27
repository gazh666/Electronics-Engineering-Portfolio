# 52 第六阶段开发基线核查

本文件记录在开始第六阶段前，对前五阶段真实代码与运行证据的核查结果。
所有结论来自实际源码、配置与 `results/` 目录，不以文档描述代替代码事实。

## 1. 环境与工具

| 项目 | 实际值 | 说明 |
| --- | --- | --- |
| 工作根 | `<repo-root>` | 项目根 `BatteryLab` |
| Conda 环境 | `kaifa_battery` | Python 3.11.18 |
| PySpice | 1.5 | 通过 DLL 调用 ngspice |
| ngspice | 34 | **无独立 CLI**，只能经 PySpice 求解 |
| Git | 非 Git 仓库 | `git status` 返回 "not a git repository"，本阶段不提交 |
| 前五阶段测试 | 316 passed | 第五阶段结束时记录，本阶段结束会重新执行 |

## 2. 电池模型真实参数（第三阶段冻结辨识）

从 `identification/parameter_store.load_frozen_model("calce_sp2_25c_inr18650_20r_first_order_v1")`
实际读取：

| 参数 | 数值 | 单位 |
| --- | --- | --- |
| 容量 `capacity_ah` | 2.028083 | Ah |
| 欧姆内阻 `r0_ohm` | 0.077068 | Ω |
| 极化电阻 `r1_ohm` | 0.022845 | Ω |
| 极化电容 `c1_f` | 788.62 | F |
| 时间常数 `tau1_s` | 18.016 | s |
| 参数拟合 SOC 区间 | 0.010637 – 0.506837 | 1 |
| OCV 曲线覆盖 SOC | 0 – 1（201 点） | 1 |

- OCV 表来自 `data/identified/ocv/ocv_soc_average.csv`，两端由实测分支常量延伸；
  0.51 以上属于外推区，文档与结论必须标注。
- 三节串联教学等效：`Rpack = 3·R0 = 0.2312 Ω`，`R1_pack = 3·R1 = 0.06853 Ω`，
  `C1_pack = C1/3 = 262.87 F`，`OCV_pack = 3·OCV_cell`。
- 3S 组 OCV 参考：SOC 0.2 → 10.683 V，0.4 → 10.900 V，0.6 → 11.300 V，
  0.8 → 11.931 V，1.0 → 12.477 V（由辨识 OCV 表计算）。

## 3. 电流方向约定

- 第一至第五阶段 ECM：**放电为正、充电为负**（`battery_models/states.py` 注释与
  `update_soc` 实现一致）。
- 第六阶段控制器内部：**`Ichg > 0` 表示电流流入电池**，因此 `Iecm = -Ichg`。
- 转换统一放在 `charging/battery_adapter.py`，禁止对全部电流直接取绝对值。

## 4. BMS 充电许可接口（第五阶段真实实现）

真实接口（`protection/protection_controller.py`、`protection/limits.py`）：

```text
ProtectionController.create(limits, cell_ids)
ProtectionController.arm(time_s)
ProtectionController.update(time_s, cell_voltages_v, pack_current_a, temperature_c,
                            measurement_valid=True) -> ProtectionSnapshot
ProtectionSnapshot.charge_allowed / discharge_allowed / measurement_valid
ProtectionSnapshot.latched_faults / active_faults / charge_fet_enabled
```

实际阈值（`configs/protection_config.yaml`，运行前固定，本阶段不得降低）：

| 项目 | 触发 / 释放 | 依据 |
| --- | --- | --- |
| 单体过压 | 4.25 / 4.15 V | 采集上限 + 高于模型参考上限 |
| 单体欠压 | 2.80 / 3.00 V | 高于采集下限、低于模型参考下限 |
| 充电过流 | 1.50 / 1.30 A | 覆盖 1 A 恒流并留裕量 |
| 放电过流 | 4.00 / 3.60 A | 约 2C |
| 短路 | 8.00 / 6.00 A | 5 ms 确认 |
| 过温 | 65 / 55 ℃ | 高于 NTC 上限 |
| 充电温度窗 | 0 – 45 ℃ | 锂离子常规窗口 |
| 恢复 | 全清 5 s + 显式请求 + 重新使能 | 禁止自动重启 |

12.15 V 恒压目标 = 3 × 4.05 V，低于 4.15 V 释放阈值，也与 4.25 V 触发阈值
保持 100 mV 以上裕量，不需要修改任何保护限值。

## 5. 真实发现：第五阶段 ECM 参数来源不一致

核查代码后发现一处需要如实记录的差异：

- `circuits/protection_mosfet.py` 使用 `CELL_R0_OHM = 0.077068`（第三阶段辨识值）。
- `scripts/stage5_common.make_pack()` 使用 `battery_models.parameters.load_ecm_models()`，
  其数据源 `configs/ecm_parameters.yaml` 的 `r0_ohm = 0.03`（教学假设值）。
- 因此第五阶段均衡/控制器使用的 ECM 内阻是教学值 0.03 Ω，而不是文档中写的辨识值。

结论：第六阶段不复制这一不一致。第六阶段显式从冻结辨识目录读取 R0/R1/C1 与 OCV 曲线，
并在所有输出元数据中写入真实来源与 SOC 有效区间。

## 6. PowerLab 只读参考盘点

| 文件 | 可复用思想 | 局限（不得直接照搬） |
| --- | --- | --- |
| `control/pi_controller.py` | 限幅、前馈、积分状态、诊断计数 | 电压模式单环，无 CC-CV 级联 |
| `control/anti_windup.py` | `clamp_duty`、积分增量 | 以"裁剪积分"为主，需补反计算抗饱和 |
| `control/soft_start.py` | 线性斜坡 | 只针对占空比，第六阶段需同时限制电流参考 |
| `control/spice_controller.py` | 行为源生成网表 | 面向 5 V Buck 恒阻负载，不是 3S 电池 |
| `circuits/closed_loop_buck.py` | 闭环网表结构 | 5 V/2 A、无电池端口、无 BMS 许可 |
| `analysis/transient_metrics.py` | 过冲/建立时间 | 需扩展为 PWM 周期加权统计 |

PowerLab 全部只读，本阶段不修改。

## 7. ngspice 真实后端注意事项（本阶段实测）

1. `analysis.branches` 键为小写完整元件名（如 `vsense`）。
2. ngspice 的 gmin/source stepping 提示会写入 stderr，PySpice 会误判为失败；
   必须保证电路有明确地参考并让工作点可解。
3. 电池组不能整体浮空，需有直流通路到地。
4. **网表内积分器直流工作点**：理想 PI 积分节点在 DC 下没有唯一解。实测解决方案：
   - 积分电容节点并联 1 kΩ 泄漏电阻（时间常数 1000 s，对毫秒级仿真可忽略）；
   - 控制量乘以 `u(time-1e-9)`，使 DC 工作点强制为 0；
   - PWM 比较器加 1 mV 阈值偏置，保证 t=0 时开关关断；
   - 栅极 100 Ω + 1 nF 平滑边沿，开关节点 1 nF 缓冲。
5. 实测闭环 8 ms 可在 11.4 / 11.9 / 12.10 V 三种电池等效电压下收敛，
   CC 稳态电流约 1.04 / 0.53 / 0.16 A，说明级联控制真实有效。

## 8. 阻塞项与边界

- 无阻断性阻塞。
- 已知边界：
  - 辨识 SOC 拟合区间仅 0.01–0.51，高 SOC 属于 OCV 曲线外推；
  - 12.15 V ≠ 100% SOC，最终 SOC 需由 ECM 实际积分确定；
  - 无法进行真实锂电池充电、过充或短路实验；
  - ngspice 34 不支持独立 CLI，全部求解经 PySpice。

## 9. 阶段 6 采用的充电设计规格

| 项目 | 值 |
| --- | --- |
| 输入电压 | 18 V |
| 开关频率 | 100 kHz |
| 电感 | 100 µH（DCR 50 mΩ） |
| 输出电容 | 220 µF（ESR 30 mΩ） |
| 功率 MOSFET | level-1 / S 开关教学模型，Rds(on) 20 mΩ |
| 续流二极管 | 0.5 V 估计，RS 20 mΩ |
| 充电通路电阻 | 30 mΩ |
| 恒流 | 1.0 A |
| 恒压 | 12.15 V |
| 终止电流 / 保持 | 0.1 A / 60 s |
| 最大充电时间 | 14400 s |
| 软启动 | 5 ms |
| 占空比范围 | 0 – 0.9 |

以上均为教学设计值，不是真实电芯充电规范。

> 实施备注：最终实现把软启动改为 1 ms。原因是开关级工况窗口只有 8–12 ms，
> 且输入/电流阶跃设在 4 ms，5 ms 软启动会让 CC 指标落在瞬态上。该项属于
> 实验设计修正，13 项预登记限值未改；详见 docs/64 §4。

