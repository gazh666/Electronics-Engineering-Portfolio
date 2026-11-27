# 21 电池容量辨识（真实 CALCE 恒流放电）

## 1. 专业原理

额定容量是厂商标称值；实际容量取决于温度、倍率、截止电压、老化与测量路径。
本项目不直接读取文件中的“容量”列作为真值，而是用原始电流对时间积分，再与文件记录值核对。

## 2. 公式推导

安时积分：

```text
Q = (1/3600) ∫ I(t) dt        [Ah]
```

零阶保持离散化（`I_k` 为区间 `[t_k, t_{k+1})` 的左端电流）：

```text
Q ≈ (1/3600) Σ I_k · Δt_k
```

差异与比值：

```text
ΔQ = Q_integrated − Q_recorded
ratio = Q_integrated / Q_rated
```

`ratio` 只是本次实验的实测/额定比，**不是 SOH**。

## 3. 参数物理意义与单位

| 量 | 含义 | 单位 |
| --- | --- | --- |
| `I_k` | 放电电流（放电为正） | A |
| `Δt_k` | 采样间隔 | s |
| `Q_integrated` | 积分容量 | Ah |
| `Q_recorded` | 文件记录容量 | Ah |
| `Q_rated` | 额定容量 2.0 | Ah |
| `ΔQ` | 计算差异 | Ah |

## 4. 实际文件路径

- `identification/capacity_estimator.py`
- `scripts/capacity_analysis_demo.py`
- `results/capacity/run_capacity_20261126_132414_b91c92/capacity_results.json`

## 5. 实际类与函数

| 名称 | 作用 |
| --- | --- |
| `CapacityResult` | 容量结果数据类（`to_dict()` 输出全部字段） |
| `cumulative_charge_ah(t, I)` | 累计放电量 |
| `validate_series(t)` | 检查重复/倒退时间与缺口 |
| `estimate_capacity_from_frame(...)` | 选择完整放电工步并积分 |
| `compare_capacity_results(list)` | 多样品对照 |

## 6. 关键源码逐行解释

```python
mask = (frame["current_a"] >= minimum_discharge_current_a) & (frame["voltage_v"] > lower_cutoff_v)
segment = frame[mask].sort_values("time_s")
if segment["time_s"].diff().max() > maximum_gap_s:      # 时间缺口拒绝
    raise CapacityError(...)
charge = cumulative_charge_ah(segment["time_s"], segment["current_a"])
```

- 第 1 行同时要求“足够大的放电电流”和“未到截止电压”；
- 第 2 行按时间排序，保证积分方向正确；
- 第 3–4 行：缺口超过阈值直接拒绝，避免把中断实验算成完整容量；
- 第 5 行：零阶保持积分。

## 7. 运行命令

```powershell
conda run -n kaifa_battery python -m scripts.capacity_analysis_demo
```

## 8. 实际结果

| 样品 | 文件 | 积分容量 | 文件记录 | 差异 | 额定比 |
| --- | --- | --- | --- | --- | --- |
| SP2 | `10_16_2015_Initial capacity_SP20-2.xls` | 2.028083 Ah | 2.028063 Ah | 1.996×10⁻⁵ Ah | 1.0140 |
| SP1 | `10_16_2015_Initial capacity_SP20-1.xlsx` | 2.009165 Ah | 2.009162 Ah | 3.076×10⁻⁶ Ah | 1.0046 |

两样品均值 2.018624 Ah，极差 0.018918 Ah（占均值 0.937%）。
条件：25 ℃，约 1.0003 A / 1.0001 A 恒流放电至 2.5 V，采样 7224 / 7157 点。

## 9. 已知局限

1. 只有一个温度、一个小倍率，不能外推高倍率或低温容量；
2. 样品间差异不能解释为老化，缺少初始健康状态；
3. 文件记录容量本身来自测试设备积分，二者一致只说明解析正确；
4. 截止电压附近的采样稀疏会带来少量积分误差。

## 10. 独立学习练习

1. 用梯形积分重算 SP2 容量，比较与零阶保持的差异；
2. 人为删除中间 10 分钟数据，观察 `validate_series` 是否拒绝；
3. 解释为什么 `ratio = 1.014` 不能写成“SOH = 101.4%”。

## 11. 相关面试题

1. 安时积分为何在高频动态工况下误差更大？
2. 容量标定为什么要求完整放电到截止电压？
3. 如果只有部分放电数据，如何估计容量？误差来源是什么？
