# 15 测试用例与方案配置

本文件说明 `configs/test_cases.yaml` 与 `configs/test_suites.yaml` 的字段、
校验规则和扩展方式。全部数据来自 PyVISA-sim 虚拟仪器与 `VirtualDUT`
行为模型，属于仿真配置，不代表真实硬件规格。

## 1. 用例文件结构

```yaml
version: "1.0"
specification_type: "component_performance_verification"
notes:
  - "说明文字"
test_cases:
  - id: TC001
    name: 标称输入电压测试
    category: normal
    vin: 12.0
    input_current_limit: 3.0
    load_current: 1.0
    expected_state: NORMAL
    output_enabled: true
    load_enabled: true
    enabled: true
    limits:
      vout: { min: 4.9, max: 5.1 }
      efficiency_percent: { min: 85.0, max: 100.0 }
```

### 1.1 字段

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `id` | 是 | 用例编号，全局唯一 |
| `name` | 是 | 用例名称 |
| `category` | 是 | 分类：`normal / boundary / protection / control / engine` |
| `vin` | 是 | 电源设定电压，0–30 V |
| `input_current_limit` | 是 | 电源限流，0–5 A |
| `load_current` | 是 | 电子负载 CC 电流，0–5 A |
| `expected_state` | 是 | `DUTState` 枚举值 |
| `output_enabled` | 否 | 电源输出开关，默认 `true` |
| `load_enabled` | 否 | 负载输入开关，默认 `true` |
| `enabled` | 否 | `false` 时只记 SKIP，不访问仪器 |
| `limits` | 否 | 指标限值，键必须在允许集合内 |

### 1.2 允许的限值指标

- 原始模型字段：`vin / iin / vout / iout / pin / pout / power_loss`
- 派生指标：`efficiency_percent / voltage_error_v /
  voltage_error_percent / absolute_voltage_error_percent`

注意：`efficiency`（0–1 小数）不在一级限值集合中，避免与百分数混用；
需要效率限值时使用 `efficiency_percent`。

## 2. 校验规则（加载阶段完成）

`engine/case_loader.py` 在**控制任何仪器之前**完成全部检查，任一失败直接
抛 `ValueError`，不会产生半执行的测试：

1. `version` 必须为 `"1.0"`；
2. 顶层/用例/限值中的未知字段一律拒绝（拼写错误不会被忽略）；
3. 用例 `id` 不得重复，必填字段不得缺失；
4. 数值必须有限、非布尔；`vin`、电流必须落在驱动额定范围内；
5. `expected_state` 必须在 `DUTState` 中；
6. 布尔字段必须是真正的 `true/false`，字符串 `"false"` 会被拒绝；
7. `limits` 的每个指标必须同时给出 `min` 与 `max`，且 `min <= max`。

参数范围复用驱动常量（`instruments/electronic_load.py` 的
`MIN_CURRENT/MAX_CURRENT`、电源 0–30 V），避免两处维护同一限制。

## 3. 测试方案

```yaml
version: "1.0"
test_suites:
  - id: SUITE-SMOKE
    name: 冒烟测试
    cases: [TC001, TC003]
    stop_on_fail: false
    stop_on_error: true
```

- `cases` 必须是已存在的用例编号，不得为空、不得重复；
- `stop_on_fail`：出现 FAIL 后停止，默认 `false`；
- `stop_on_error`：出现 ERROR 后停止，默认 `true`；
- 方案只引用编号，不复制参数，避免同一阈值出现两份。

## 4. 现有配置

| 文件 | 用途 |
| --- | --- |
| `configs/test_cases.yaml` | 12 条正式用例 |
| `configs/test_suites.yaml` | 冒烟 / 保护 / 完整回归 |
| `configs/engine_validation_cases.yaml` | 引擎自校验（故意 FAIL/SKIP/ERROR） |
| `configs/scenario_cases.yaml` | 旧版字典用例，仅回归旧执行器 |

## 5. 局限

- 当前 DUT 为 12 V→5 V、最大 2 A 的行为模型；保护阈值是模型假设，
  不是厂商数据手册；
- 4.9–5.1 V、效率 85–100% 等限值均为项目假设；
- 用例配置不会改变真实仪器量程，越界参数在驱动层已被拦截。
