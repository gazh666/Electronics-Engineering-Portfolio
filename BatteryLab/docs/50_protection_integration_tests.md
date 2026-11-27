# 50 第五阶段测试与证据索引

## 1. 测试结构

| 文件 | 覆盖 |
| --- | --- |
| `tests/test_protection_limits.py` | 阈值边界、回差顺序、非法配置拒绝、可追溯性 |
| `tests/test_protection_comparator.py` | 确认延时、迟滞释放、传输延时、噪声抖动 |
| `tests/test_fault_state_machine.py` | 锁存、独立许可、恢复规则、禁止自动重启 |
| `tests/test_protection_controller.py` | 逐节 OV/UV、双向过流、短路、温度、均衡许可 |
| `tests/test_balancing.py` | 电流/功耗公式、选择规则、12 h 收敛 |
| `tests/test_protection_spice.py` | 真实 ngspice：开关矩阵、瞬态、比较器、栅极、均衡 |
| `tests/test_stage5_integration.py` | 保护判决 → 许可 → 真实阻断 |

## 2. 真实 SPICE 与数学仿真分离

| 类别 | 次数/规模 | 说明 |
| --- | --- | --- |
| 真实 ngspice 求解 | 12 次 | 7 开关工况 + 1 瞬态 + 2 比较器 + 1 栅极 + 1 均衡 |
| ECM 长时积分 | 4321 点 × 3 节 | 被动均衡收敛 |
| 状态机离散仿真 | 数千步 | 不消耗 SPICE |

不把 ECM 积分或状态机步进称为 SPICE。

## 3. 运行命令

```powershell
conda run -n kaifa_battery python -m pytest tests -q
conda run -n kaifa_battery python -m scripts.battery_stage5_demo
conda run -n kaifa_battery python -m pip check
```

## 4. 验收结果

- Pytest：**316 passed**（原 257 + 新增 59）。
- 第五阶段综合检查：**41 PASS / 0 FAIL**。
- 真实 SPICE：12 次（预算 40）。

## 5. 证据路径

| 内容 | 路径 |
| --- | --- |
| 综合验收 | `results/stage5_validation/run_stage5_validation_20261126_143914_3f8da9/` |
| 开关实验 | `results/protection/run_protection_20261126_143914_82fa77/` |
| 比较器实验 | `results/protection/run_protection_20261126_143915_9a84ab/` |
| 状态机实验 | `results/protection/run_protection_20261126_143915_7354a8/` |
| 均衡实验 | `results/protection/run_protection_20261126_143916_7ed424/` |

## 6. 不允许的替代

- 不允许用 Mock 替代全部真实 SPICE。
- 不允许预设 PASS 或修改限值。
- 不允许用布尔变量冒充完整保护电路验证。

## 7. 面试题

1. 如何区分真实 SPICE 与数学仿真？
2. 为什么保护测试要覆盖正常、边界、故障三类？
3. 如何证明测试没有"假通过"？
4. 集成测试应该验证哪条链路？
5. 测试预算有限时如何取舍？

