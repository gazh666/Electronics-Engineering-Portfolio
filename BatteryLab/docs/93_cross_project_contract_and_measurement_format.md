# 93 跨项目数据契约与测量格式

## 1. 为什么需要契约

三个项目各自的数据结构不同：BatteryLab 有 ECM 状态与保护快照，PowerLab 有
开关级波形与效率指标，TestLab 只有限值判定。若直接把数字互相传递，很容易
把"未验证"当成"通过"。本阶段因此固定一份最小契约。

## 2. 测量交换格式

Schema：`schemas/system_measurements_v1.schema.json`

| 字段 | 约束 | 说明 |
| --- | --- | --- |
| `schema_version` | 固定 `"1.0"` | 拒绝未知版本 |
| `run_id` | 非空 | 对应真实结果目录 |
| `source` | 五类枚举 | `historical_replay`、`quasi_steady_coupled_simulation`、`averaged_dynamic_coupled_simulation`、`spice_coupled_simulation`、`behavioral_protection_simulation` |
| `hardware_validated` | 必须 `false` | 防止把仿真写成实测 |
| `measurements[]` | 至少 1 项 | 每项含 metric/value/unit/status/source |
| `measurements[].status` | `VERIFIED` / `NOT_VERIFIED` / `FAIL` / `ERROR` | `VERIFIED` 需同时给出 `source_run_id` 与存在的 `evidence_path` |

校验实现：`integration/interface_validator.py`

- 缺字段 → ERROR；
- `VERIFIED` 但无值、无 Run ID、无证据文件 → ERROR；
- 证据路径不存在 → ERROR；
- 重复 metric → WARN（不阻止，但会在报告中列出）。

## 3. 测试结果格式

Schema：`schemas/system_test_result_v1.schema.json`

- 单工况状态：`PASS` / `FAIL` / `NOT_VERIFIED` / `ERROR`；
- 聚合规则：`ERROR > FAIL > NOT_VERIFIED > PASS`；
- 没有检查项 → `NOT_VERIFIED`，绝不默认 PASS。

## 4. 单位与符号约定

| 量 | 单位 | 约定 |
| --- | --- | --- |
| 电流 | A | **放电为正**，充电为负 |
| 电压 | V | 单体、组端、转换器输入、输出分别命名 |
| 功率/能量 | W / J 或 Wh | 能量用梯形积分 |
| 时间 | s | 波形文件列名带 `_s` |
| 效率 | % | `Pout / Pin × 100`，Pin > 0 才计算 |

## 5. 禁止项

1. 不允许其他项目读取 BatteryLab 内部对象；跨项目只传 JSON/CSV；
2. 不允许把 `VERIFIED` 解释为"满足设计限值"；
3. 不允许在缺证据时补默认值；
4. 不允许修改 TestLab/PowerLab 的配置来"适配"本阶段；
5. 不允许把行为级保护控制的时序写成 BQ76922 实测检测时间。

## 6. 契约验证结果

- `pytest tests/test_integration_contracts.py` 覆盖：有效包通过、缺证据失败、
  非法状态拒绝、Schema 文件 draft-07 校验；
- 每次标准运行都会生成 `system_measurements.json`，并在 TestLab 集成步骤
  重新校验后才交给判定模块。
