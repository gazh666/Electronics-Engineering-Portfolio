# 67 OCV-SOC 反向查表与可观测性

日期：2026-11-26
对应源码：`estimation/ocv_estimator.py:35`（`OCVSOCTable`）

## 1. 问题

第三阶段给出 `SOC → OCV` 曲线；估计器需要 `OCV → SOC`。直接线性插值有两个坑：

1. 原始平均 OCV 曲线在约 89%–90% 与 99.5%–100% SOC 附近**非单调/平台**；
2. 平台区 `dOCV/dSOC` 很小，几十毫伏误差可能对应几十个百分点 SOC。

## 2. 实现策略

| 步骤 | 做法 | 代码 |
| --- | --- | --- |
| 原始数据 | 完整保留 | `raw_ocv_table_v` |
| 单调化 | 累积最大包络 `np.maximum.accumulate` | `OCVSOCTable.__post_init__` |
| 审计 | 记录被调整索引 | `monotonic_indices`、`audit()` |
| 斜率 | 包络上的分段斜率 | `slope_at()`、`slope_series()` |
| 低可观测 | `slope < minimum_slope` 返回 `None` | `estimate()` |
| 外推 | 禁止 | `OUTSIDE_OCV_RANGE` |

核心反演：

```text
SOC = interp(OCV_meas, OCV_table, SOC_table)     仅当 slope ≥ 0.2 V/SOC
```

## 3. 真实数据审计结果

运行：`results/soc_estimation/run_soc_estimation_20261126_161618_8afdb0`

| 项 | 数值 |
| --- | --- |
| 表点数 | 2001 |
| OCV 范围 | 2.904 – 4.159 V |
| 原始非递增段数 | 20 |
| 单调包络调整点数 | 104（索引 1781–1884，约 89%–94.2% SOC） |
| 表级低斜率区间数（<0.2 V/SOC） | 129，覆盖约 0.271–0.9998 SOC |

在 US06_50 上直接把端电压当 OCV：

| 指标 | 数值 |
| --- | --- |
| MAE | 9.299 pp |
| RMSE | 12.778 pp |
| 最大误差 | 44.94 pp |
| 覆盖率（0≤ref≤1） | 0.9907 |
| `LOW_OBSERVABILITY` 样本 | 38 |
| `OUTSIDE_OCV_RANGE` 样本 | 26 |

结论：**带载端电压不是 OCV**。把端电压直接查表会把欧姆压降与极化压降当成
SOC 变化，误差可达 45 pp，且无法通过"调权重"解决。

## 4. 平台区为什么危险

误差放大关系：

```text
ΔSOC = ΔV / (dOCV/dSOC)
```

- 斜率 0.5 V/SOC 时，5 mV → 1 pp；
- 斜率 0.2 V/SOC 时，5 mV → 2.5 pp；
- 斜率 0.05 V/SOC 时，5 mV → 10 pp。

因此观测器在 `slope < 0.2` 时必须返回 `LOW_OBSERVABILITY`，而不是给一个
看似精确的 SOC。

## 5. 设计取舍

| 取舍 | 选择 | 理由 |
| --- | --- | --- |
| 删除异常点 | 否 | 保留原始数据，只做显式包络并审计 |
| 外推 | 否 | 超出 2.904–4.159 V 无物理依据 |
| 3.6 V 平台强制单调 | 是（仅可逆性需要） | 平台加 1e-9 增量，同时标记低可观测 |
| 用多项式拟合替代查表 | 否 | 会平滑掉真实平台，且不可审计 |

## 6. 常见错误

1. 直接对原始非单调曲线做 `np.interp`，得到错位 SOC。
2. 平台区仍返回 SOC，且不报告置信度。
3. 把 `OUTSIDE_OCV_RANGE` 的样本填成 0 或 1。
4. 用端电压代替 OCV 做"静置校正"，但在大电流时也校正。

## 7. 运行与结果

```bash
conda run -n kaifa_battery python -m scripts.ocv_soc_demo
```

输出：`ocv_table.csv`、`ocv_slope.csv`、`ocv_audit.json`、`raw_voltage_metrics.json`，
图 `02_ocv_inverse_curve.png`、`03_ocv_slope.png`、`04_ocv_platform_uncertainty.png`。

## 8. 练习与面试题

练习：

1. 把 `minimum_slope` 从 0.2 改成 0.05，观察 US06 上 `LOW_OBSERVABILITY` 样本数
   与最大误差如何变化。
2. 找出索引 1781–1884 对应的 SOC 区间，并与原始 OCV 数据对照。

面试题：

1. 为什么"单调化"不能解决平台区的可观测性问题？
2. 如果 OCV 测量有 +10 mV 固定偏差，在斜率 0.2 与 0.5 的区域各造成多少 SOC 误差？
3. 为什么本阶段禁止外推？外推在什么条件下才可以接受？
