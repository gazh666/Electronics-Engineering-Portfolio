# 13 数据质量检查

## 1. 目标

性能指标只有在数据可信时才有意义。数据质量层在指标计算之前运行，
负责识别缺失、非法、功率不守恒、来源不一致和重复记录，并把问题
显式记录到报告中。

## 2. 检查项

| 编号 | 检查 | 代码 | 级别 |
| --- | --- | --- | --- |
| 1 | 必要字段缺失 | `MISSING_FIELD` | ERROR |
| 2 | 数值字段不是数字 | `INVALID_NUMBER` | ERROR |
| 3 | NaN / inf | `NON_FINITE` | ERROR |
| 4 | 负电压/负电流 | `NEGATIVE_VALUE` | ERROR |
| 5 | 输入功率为 0 但输出功率大于 0 | `ZERO_INPUT_POWER` | ERROR |
| 6 | 输出功率大于输入功率 | `POWER_BALANCE_ERROR` | ERROR |
| 7 | 效率超过 100% | `EFFICIENCY_ABOVE_100` | ERROR |
| 8 | 上报功率与计算功率不一致 | `METRIC_MISMATCH` | ERROR |
| 9 | 保护状态与模型输出不一致 | `STATE_OUTPUT_MISMATCH` | ERROR |
| 10 | 数据来源错误 | `SOURCE_MISMATCH` | ERROR |
| 11 | 工况参数缺失 | `MISSING_CONTEXT` | WARNING |
| 12 | 重复记录 | `DUPLICATE_RECORD` | WARNING |

负电压/负电流检查针对当前单向 DC-DC 模型；若接入双向电源、充放电
设备或再生电子负载，电流允许为负，需要调整规则。该限制已写入文档。

## 3. 容差

功率一致性使用绝对 + 相对混合容差，默认 `1e-6`、`1e-6`，可在
`configs/performance_limits.yaml` 的 `data_quality` 段配置。

浮点计算存在舍入误差，因此不使用 `==` 比较。

## 4. 异常数据处理

- 原始记录**不删除、不覆盖**；
- `validate_dataset()` 返回 `DatasetQualityReport`，包含：
  - `total_records`；
  - `valid_indices` / `valid_count`；
  - `excluded_indices` / `excluded_reasons` / `excluded_count`；
  - 每条记录的 `issues`；
  - 数据集级 `dataset_issues`（重复记录）。
- 重复记录保留第一次出现，后续项排除出统计，但原因写入报告；
- 性能分析器遇到 ERROR 级问题时输出 `metric_status=INVALID_DATA`，
  不计算指标，也不把异常值当作真实性能。

## 5. 数据来源

合法性能数据的来源必须与预期一致：

| 来源 | 用途 | 是否可用于性能判定 |
| --- | --- | --- |
| `behavioral_model` | 虚拟 DUT 稳态计算 | 是 |
| `static_mock` | SCPI 链路/固定响应验证 | 否 |
| `real hardware` | 未来真实硬件 | 是（需新增接入） |

分析器默认期望 `behavioral_model`。固定 DMM 响应若被误当作性能数据，
会因 `SOURCE_MISMATCH` 被判为 `INVALID_DATA`。

## 6. 与指标计算的关系

```text
原始 DUTResult
   ↓ 保留全部原始字段
validate_record / validate_dataset
   ↓ VALID / ERROR / WARNING
calculate_metrics
   ↓
限值判定 checks（PASS / FAIL / N/A）
```

数据质量失败时**不进入**限值判定，避免“用错误数据算出一个 PASS”。
