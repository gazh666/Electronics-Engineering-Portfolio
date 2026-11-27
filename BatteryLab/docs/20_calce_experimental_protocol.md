# 20 CALCE 实验协议、数据划分与 SOC 参考

## 1. 专业原理

CALCE（University of Maryland）公开的 INR18650-20R 数据由多类工步组成：初始容量标定、低电流
OCV、增量 OCV、DST/FUDS/US06/BJDST 动态工况。第三阶段必须做到：

1. 训练、开发、独立验证严格分离；
2. SOC 参考轨迹只由电流积分与实测容量得到，不用验证电压修正；
3. 任何跨样品使用必须显式说明。

## 2. 数据划分

| 角色 | 数据集 | 样品 | 温度 | 用途 |
| --- | --- | --- | --- | --- |
| capacity_reference | SP2 初始容量 | SP2 | 25 ℃ | 提供 `Q = 2.028083 Ah` |
| capacity_cross_check | SP1 初始容量 | SP1 | 25 ℃ | 样品间容量对照 |
| ocv_low_current_primary | SP1 低电流 OCV | SP1 | 25 ℃ | 提取 OCV-SOC 主曲线 |
| ocv_low_current_cross_cell | SP3 低电流 OCV | SP3 | 25 ℃ | 跨样品 OCV 差异 |
| ocv_incremental | SP3 增量 OCV | SP3 | 25 ℃ | 静置质量核对（不参与拟合） |
| training | SP2 DST 50% | SP2 | 25 ℃ | 参数辨识 |
| development | SP2 DST 80% | SP2 | 25 ℃ | 开发集对照，不参与调参 |
| independent_validation | SP2 FUDS 50%/80% | SP2 | 25 ℃ | 冻结参数后一次性验证 |
| additional_validation | SP2 US06/BJDST | SP2 | 25 ℃ | 额外工况稳健性 |

划分规则写在 `configs/dataset_split.yaml`，每个数据集带 `role`、`sha256`、`source_file`。

## 3. SOC 参考公式推导

对归一化电流 `I(t)`（放电为正），累计放电量：

```text
qd(t) = (1/3600) ∫_0^t I(τ) dτ        [Ah]
```

已知动态段起点前已完成的放电量 `qd0` 与实测容量 `Q`，则

```text
SOC0 = 1 - qd0 / Q
SOC(t) = SOC0 - qd(t)/Q
```

零阶保持离散化（区间 `[t_k, t_{k+1})` 用 `I_k`）：

```text
qd_{k+1} = qd_k + I_k · (t_{k+1} - t_k)/3600
```

**为什么不能用验证电压反推 SOC0**：那会把验证集信息泄漏进模型，独立验证失效。

## 4. 参数物理意义与单位

| 符号 | 含义 | 单位 |
| --- | --- | --- |
| `Q` | 实测可用容量 | Ah |
| `I` | 归一化电流（放电为正） | A |
| `qd` | 累计放电量 | Ah |
| `SOC` | 荷电状态 | 1（0–1） |
| `SOC0` | 动态段初始 SOC | 1 |

## 5. 实际文件路径

- `configs/dataset_split.yaml`
- `validation/dataset_split.py`
- `scripts/stage3_common.py`

## 6. 实际类与函数

| 名称 | 作用 |
| --- | --- |
| `ExperimentSlice` | 一次实验切片的数据容器（含 `soc0`、`soc0_method`、`summary()`） |
| `load_experiment_frame(record)` | 按 `source_file` 过滤并校验时间轴 |
| `find_dynamic_step(frame)` | 选择电流方差最大的工步 |
| `initial_soc_from_recorded_capacity(frame, t0, Q)` | 由记录容量反算 SOC0 |
| `build_experiment(name, record, capacity_ah)` | 生成带 `soc_reference` 的切片 |
| `cumulative_charge_ah(t, I)` | 累计放电量 |

## 7. 关键源码逐行解释

```python
soc0 = 1.0 - discharged / capacity_ah            # 记录容量平衡
if not 0.0 < soc0 < 1.0:
    return None, f"INVALID_RESULT({soc0:.4f})"   # 越界不修正，明确失败
dynamic["soc_reference"] = soc0 - cumulative / capacity_ah
```

- 第 1 行只用动态段起点前的累计放电量与实测容量；
- 第 2–3 行：结果越界时返回 `None` 与原因，绝不夹紧到 0/1；
- 第 4 行：动态段内逐点积分，形成可审计的参考轨迹。

## 8. 运行命令

```powershell
conda run -n kaifa_battery python -m scripts.ecm_identification_demo
conda run -n kaifa_battery python -m scripts.dynamic_validation_demo
```

## 9. 实际结果

| 实验 | SOC0 | 方法 | 动态段点数 |
| --- | --- | --- | --- |
| DST 50% | 0.506837 | recorded_capacity_balance | 6685 |
| DST 80% | 0.802743 | recorded_capacity_balance | 10621 |
| FUDS 50% | 0.506867 | recorded_capacity_balance | 6995 |
| FUDS 80% | 0.802742 | recorded_capacity_balance | 11092 |
| US06 50% | 0.506813 | recorded_capacity_balance | 6874 |
| US06 80% | 0.802739 | recorded_capacity_balance | 10680 |
| BJDST 50% | 0.506803 | recorded_capacity_balance | 6940 |
| BJDST 80% | 0.802714 | recorded_capacity_balance | 11205 |

## 10. 已知局限

1. SOC 参考依赖实测容量 `Q`，若 `Q` 偏差 1%，SOC 轨迹同比例偏移；
2. 数据只有 25 ℃，无法验证温度对初始 SOC 的影响；
3. 动态段前的静置历史可能残留极化，SOC 参考不包含这部分误差；
4. 原始采样间隔不完全均匀，积分使用零阶保持而非样条。

## 11. 独立学习练习

1. 用表 9 的 SOC0 与 6685 点重算 DST 50% 末端 SOC，与 `soc_reference_min` 对比；
2. 把容量换成 2.0 Ah，观察 SOC 轨迹变化并解释；
3. 设计一个测试证明“用验证电压修正 SOC0”会造成信息泄漏。

## 12. 相关面试题

1. 为什么 BMS 里 SOC 初值通常来自开路静置 + OCV 查表，而不是电压瞬时值？
2. 容量误差如何传播到 SOC 误差？给出定量关系。
3. 训练/开发/验证三分法的目的是什么？开发集可以参与调参吗？
