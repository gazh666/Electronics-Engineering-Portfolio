# 74 容量型 SOH 与内阻健康

日期：2026-11-26
对应源码：`health/capacity_soh.py`、`health/cycle_analysis.py`、
`health/resistance_health.py`、`health/aging_data_loader.py`、`health/capacity_update.py`

## 1. 容量型 SOH

```text
SOH_Q = Q_current / Q_reference × 100%
```

规则：

- 基准容量优先用同一电芯、同温度、同倍率的完整容量实验；
- SOH 可以因测试差异暂超 100%，不裁剪；
- 不强制单调下降；
- 没有真实老化数据时，不给循环寿命或 RUL 结论。

## 2. 真实数据：一次完整放电的一致性检查

运行：`results/battery_health/run_battery_health_20261126_161753_3e607b`

来源：`10_16_2015_Initial capacity_SP20-2.xls`，Channel_1-015，step_index 6。

| 项 | 数值 |
| --- | --- |
| 积分容量 | 2.0280827046460144 Ah |
| 文件记录容量 | 2.028062744229916 Ah |
| 差值 | 1.996e-05 Ah |
| 相对差 | **0.000984%** |
| 截止电压 | 2.49997 V |
| 质量状态 | `VALID_COMPLETE_DISCHARGE` |

结论：同一次实验的容量字段与电流积分高度一致（远小于 1% 预登记限值）。
这属于**容量计算一致性检查**，不是独立在线 SOH 估计精度。

## 3. 合成老化管线

参数：初始 2.0 Ah，每循环衰减 0.002 Ah，100 循环，`synthetic_truth`。

| 指标 | 数值 |
| --- | --- |
| 最终容量 | 1.802 Ah |
| 最终 SOH | 90.1% |
| 容量损失 | 9.9% |
| 解析积分误差 | 0 Ah |
| 单调下降 | 是 |

容量更新（只在会话边界生效）：

```text
2.0 Ah --记录 1.98 Ah--> 会话内不变 --begin_session--> 2.0 + 0.2×(1.98-2.0) = 1.996 Ah
```

这避免"用本循环最终容量反向修正本循环开始 SOC"的作弊式自适应。

## 4. 真实老化数据可用性

`health/aging_data_loader.py` 扫描 `data/raw`：

| 项 | 结果 |
| --- | --- |
| 文件数 | 9 个 zip |
| 老化候选 | 0 |
| 状态 | **NOT_VERIFIED** |
| 原因 | 只有初始容量/OCV/DST/FUDS/US06/BJDST，无连续循环老化 |
| NASA 老化数据 | 未下载 |

因此真实容量保持率、循环老化速率、真实 SOH 趋势全部 NOT_VERIFIED。
"1 个循环、保持率 100%"没有老化含义。

## 5. 内阻健康

### 5.1 真实单点表观 DCIR

运行：`results/battery_health/run_battery_health_20261126_161844_389769`

从 US06_50 真实电流阶跃估计：

| 项 | 数值 |
| --- | --- |
| 表观 DCIR | 0.073274 Ω |
| 时点 SOC | 0.3907 |
| 温度 | 25℃ |
| 电流方向 | charge |
| 阶跃幅值 | 4.4827 A |
| 取样窗口 | 1.0030 s |
| 指标类型 | dcir |

这是**单点、非老化**的内阻估计，不能据此得出增长率。

### 5.2 可比性

| 对比 | 结果 |
| --- | --- |
| 自身对自身 | COMPARABLE |
| 温度 +10℃ | CONDITION_MISMATCH（TEMPERATURE_MISMATCH） |

规则：不同电芯、SOC、温度、方向、幅值、窗口、方法任一不满足即不可比。
瞬时欧姆内阻、DCIR、ECM R0、EIS 阻抗不能互相替代。

### 5.3 合成增长序列（仅教学）

以真实单点为基准，每循环 +0.4%，100 循环：

| 项 | 数值 |
| --- | --- |
| 初始 | 0.073274 Ω |
| 最终 | 0.102290 Ω |
| 最终增长 | 39.6% |

标记 `synthetic_truth`，**不是实测老化**。真实内阻增长率 NOT_VERIFIED。

## 6. 设计取舍

| 取舍 | 选择 | 理由 |
| --- | --- | --- |
| 容量基准 | 冻结模型辨识容量 | 同电芯同温度同倍率，可追溯 |
| 超 100% | 保留 | 隐藏原始差异会掩盖测试问题 |
| 平滑 | 默认关闭 | 原始容量与 SOH 必须同时保留 |
| 容量更新时机 | 会话边界 | 防止未来信息泄漏到当前 SOC |
| 内阻指标 | 明确标 DCIR | 防止把不同定义混为一谈 |

## 7. 常见错误

1. 只有 1 个循环就画"容量衰减曲线"。
2. 把不同温度的内阻差归因于老化。
3. 用本循环末容量反向修正本循环初始 SOC。
4. 把 SOH 强制裁剪到 ≤100%。
5. 把合成增长曲线写成"实验测得的内阻增长"。

## 8. 运行命令

```bash
conda run -n kaifa_battery python -m scripts.capacity_soh_demo
conda run -n kaifa_battery python -m scripts.resistance_health_demo
conda run -n kaifa_battery python -m pytest tests/test_capacity_soh.py tests/test_resistance_health.py -q
```

## 9. 练习与面试题

练习：

1. 把合成衰减率改为 0.005 Ah/cycle，计算 200 循环后的 SOH。
2. 用 us06_50 中不同 SOC 的两个脉冲比较内阻，判断是否可比。

面试题：

1. 为什么"积分容量与记录容量一致"不能证明在线 SOH 精度？
2. 容量更新为什么必须放在会话边界？
3. DCIR 与 ECM R0 的区别是什么？何时可以互相替代？
