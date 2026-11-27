# 48 充放电独立许可与 MOSFET 控制接口

## 1. 接口定义

`ProtectionSnapshot` 是第五阶段对外的唯一接口：

| 字段 | 含义 |
| --- | --- |
| `charge_allowed` | 允许充电 |
| `discharge_allowed` | 允许放电 |
| `charge_fet_enabled` | 充电管栅极使能 |
| `discharge_fet_enabled` | 放电管栅极使能 |
| `latched_faults` | 锁存故障码 |
| `active_faults` | 当前仍在发生的故障 |
| `balancing` | 每节均衡通道状态 |

第六阶段充电器只能通过该接口申请充电，不得绕开。

## 2. 映射到真实开关

| 许可 | 栅极 | 方向 |
| --- | --- | --- |
| `charge_fet_enabled=True` | CHG 栅极 10 V | 允许 BATT_N→CS |
| `discharge_fet_enabled=True` | DSG 栅极 10 V | 允许 PACK_N→CS |
| 两者 False | 双管关断 | 双向阻断 |

真实阻断能力已在 `CASE_C/CASE_D/CASE_E` 中测量，残余电流 ≤13.2 nA。

## 3. 为什么不能只给一个 `allowed`

- 过压时应停止充电但允许放电。
- 欠压时应停止放电但允许充电。
- 短路/测量失效时才双向禁止。

单一布尔量会迫使系统在过压时完全断电，损失可用性，也不符合真实 BMS 行为。

## 4. 与均衡的关系

均衡仅在以下条件同时满足时允许：

```text
状态机已使能 ∧ 无锁存故障 ∧ 测量有效
∧ |I_pack| ≤ 0.05 A（静置或充电）
∧ 最高单体 ≥4.10 V ∧ 压差 ≥30 mV
```

放电时不均衡，避免把正在工作的电芯继续耗散。

## 5. 代码

```python
snapshot = controller.update(t, cell_voltages, pack_current, temperature)
if snapshot.charge_allowed:
    charger.enable()
```

## 6. 测试

- `tests/test_protection_controller.py`：方向许可、失效禁止。
- `tests/test_stage5_integration.py`：许可 → 真实阻断。

## 7. 面试题

1. 为什么 BMS 要提供独立充放电许可？
2. 许可为 False 时如何保证硬件真的关断？
3. 第六阶段充电器如何安全复用该接口？
4. 测量失效时的失效安全策略是什么？
5. 如何避免软件许可与硬件状态不一致？
