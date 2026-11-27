# 47 故障状态机、故障锁存与合法恢复

## 1. 状态与故障码

```text
NORMAL ──任意故障──▶ LATCHED
LATCHED ──条件清零 + 保持 5 s + 显式请求──▶ NORMAL（未使能）
NORMAL（未使能）──显式 arm──▶ 可充/可放
```

故障码：`CELL_OVERVOLTAGE`、`CELL_UNDERVOLTAGE`、`CHARGE_OVERCURRENT`、
`DISCHARGE_OVERCURRENT`、`SHORT_CIRCUIT`、`OVER_TEMPERATURE`、
`UNDER_TEMPERATURE_CHARGE`、`CHARGE_HIGH_TEMPERATURE`、`MEASUREMENT_INVALID`。

## 2. 锁存记录

每个故障保存：首次触发时间、最后出现时间、涉及电芯、触发次数。条件消失后
记录仍保留，直到合法恢复清除。

## 3. 独立许可

```text
charge_allowed    = armed ∧ 无充电抑制故障 ∧ 测量有效
discharge_allowed = armed ∧ 无放电抑制故障 ∧ 测量有效
```

充电抑制：OV、充电过流、短路、过温、充电高温、充电低温、测量失效。
放电抑制：UV、放电过流、短路、过温、测量失效。

因此过压时仍可放电、欠压时仍可充电，这是 BMS 的正常行为。

## 4. 合法恢复

恢复必须同时满足：

1. 没有任何仍在发生的故障。
2. 全部故障条件清零后持续 ≥5 s（`all_clear_hold_s`）。
3. 外部显式 `request_recovery`。
4. 测量有效。

恢复成功后 `armed=False`，必须再次 `arm()` 才允许充放电。**禁止自动重启**。

## 5. 实测（Run `protection_20261126_143336_4c7ec2`）

| 检查 | 实测 | 状态 |
| --- | --- | --- |
| 过压锁存 | 0.154 s | PASS |
| 过压后独立许可 | 充电禁止/放电允许 | PASS |
| 未清除时恢复 | 拒绝 | PASS |
| 保持 5 s 后恢复 | 接受且要求重新使能 | PASS |
| 重新使能后 | 双向恢复 | PASS |
| 欠压锁存 | 0.154 s | PASS |
| 充电过流锁存 | 0.502 s | PASS |
| 放电过流锁存 | 0.202 s | PASS |
| 短路锁存 | 0.006 s | PASS |
| 过温锁存 | 2.005 s | PASS |
| 低温 | 充电禁止/放电允许 | PASS |
| 测量失效 | 立即双向禁止 | PASS |
| 自动重启次数 | 0 | PASS |

## 6. 源码

- `protection/state_machine.py`
- `protection/protection_controller.py`
- `scripts/protection_state_machine_demo.py`

## 7. 常见错误

1. 故障消失后自动恢复供电。
2. 用单一 `fault` 布尔量代替分方向许可。
3. 测量失效时仍使用旧值。
4. 恢复请求没有时间窗口约束。

## 8. 面试题

1. 为什么故障要锁存？
2. 为什么恢复后还要重新使能？
3. 全清保持时间的意义是什么？
4. 测量失效为什么必须立即双向禁止？
5. 如何设计可审计的保护事件日志？
