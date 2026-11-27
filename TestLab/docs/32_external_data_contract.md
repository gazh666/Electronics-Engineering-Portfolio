# 32 外部数据接入契约（PowerLab / BatteryLab 预留）

本文件定义 TestLab 与未来 PowerLab（SPICE 电路仿真）、BatteryLab（电池模型与
公开实验数据）之间的数据交换规范。**本阶段只定义接口，不实现 PowerLab 或
BatteryLab，也不重构现有 DC-DC 测试链路。**

## 1. 公共元数据（所有来源必填）

```text
schema_version   契约版本，例如 "1.0"
source_type      behavioral_model | spice_simulation | battery_model |
                 public_dataset | real_measurement
source_name      来源名称，例如 "PowerLab" / "BatteryLab" / "VirtualDUT"
source_version   来源软件或模型版本
run_id           运行编号（全局唯一，禁止复用）
case_id          用例编号
timestamp        ISO 8601，必须带时区；推荐 UTC
configuration    该次运行的参数快照（映射）
units            字段单位声明（映射）
quality_status   VALID | INVALID | PARTIAL
```

约束：

- `source_type` 必须与数据实际来源一致，禁止把模型结果标为
  `real_measurement`；
- `quality_status=INVALID` 的数据不得进入 PASS/FAIL 判定；
- `run_id` 与 `case_id` 必须能追溯回运行目录与配置快照。

## 2. PowerLab 电源数据

```text
schema_version
source_type = spice_simulation
vin, iin, vout, iout        V / A
pin, pout                   W
efficiency                  0–1 比例（不是百分数）
operating_state             枚举，例如 NORMAL / UNDERVOLTAGE / OVERVOLTAGE /
                            OVERCURRENT / OFF
```

映射到 TestLab：

| PowerLab 字段 | TestLab 字段 | 说明 |
| --- | --- | --- |
| `vin` | `vin` | 输入电压 |
| `iin` | `iin` | 输入电流 |
| `vout` | `vout` | 输出电压 |
| `iout` | `iout` | 输出电流 |
| `pin` / `pout` | `pin` / `pout` | 功率 |
| `efficiency` | `efficiency_percent = efficiency × 100` | 统一转换为百分数后再判定 |
| `operating_state` | `actual_state` | 保护状态不按稳压限值判 FAIL |

适用指标：效率、电压误差、负载/线性调整率、功率守恒。
不适用的指标：纹波、瞬态响应（当前无时间序列，禁止伪造）。

## 3. BatteryLab 电池数据

```text
schema_version
source_type = battery_model | public_dataset
time_s                       s（时间基准为放电/充电开始时刻）
voltage_v                    V
current_a                    A（放电为正或负必须在 configuration 中声明）
temperature_c                °C
soc                          0–1
capacity_ah                  Ah
soh                          0–1
```

约束：

- 电池是**双向储能器件**，不得强行套用单向 DC-DC 的
  `pout / pin` 效率判定；
- 需要新增指标族：容量保持率、能量效率（充放电循环）、内阻趋势、温升；
- `current_a` 的符号约定必须写入 `configuration`；
- 公开数据集必须记录来源 URL、许可证与预处理步骤；
- 数据质量规则需单独定义（如 SOC 单调性、温度越界、容量跳变）。

## 4. 来源类型与可信度标签

| source_type | 含义 | 能否用于真实硬件结论 |
| --- | --- | --- |
| `behavioral_model` | 当前 VirtualDUT 稳态模型 | 否 |
| `spice_simulation` | PowerLab 电路级仿真 | 否（仿真结论） |
| `battery_model` | BatteryLab 电池模型 | 否 |
| `public_dataset` | 公开实验数据 | 仅限数据集覆盖范围 |
| `real_measurement` | 真实仪器测量 | 是（需另行校准与不确定度分析） |

## 5. 兼容性设计（本阶段已具备）

- TestLab 现有记录均带 `data_source` 字段，报告按来源展示；
- `engine/dut_bridge.py` 是显式数据桥接点，未来可替换为 PowerLab 数据源，
  而不改判定层；
- 指标限值来自 `configs/performance_limits.yaml`，不硬编码在算法中；
- 报告识别 `results/` 内的扫描文件，不合并其他运行的数据。

## 6. 明确不做的事情（本阶段）

- 不实现 PowerLab/BatteryLab 的任何仿真代码；
- 不把电池数据接入现有 DC-DC 用例；
- 不为未来规划大规模重构当前项目；
- 不宣称已支持真实仪器测量或真实芯片 Datasheet 对比。
