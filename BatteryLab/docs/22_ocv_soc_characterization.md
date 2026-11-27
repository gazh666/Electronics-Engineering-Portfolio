# 22 OCV-SOC 特性提取与查表模型

## 1. 专业原理

端电压 `V_t = OCV(SOC) − I·R0 − V_p`。只有在电流接近零、极化充分松弛时，端电压才近似 OCV。
CALCE 低电流实验以 ±0.1 A 连续充放电并插入静置，项目用其构造 OCV-SOC 曲线，并用增量 OCV 静置段
做独立质量核对。

## 2. 公式推导

低电流分支的 SOC 由电流积分得到：

```text
SOC(t) = SOC_anchor − (1/3600Q) ∫ I dt
```

平均 OCV（仅在两方向共同覆盖区间）：

```text
OCV_avg(SOC) = [OCV_charge(SOC) + OCV_discharge(SOC)] / 2
```

迟滞：

```text
H(SOC) = OCV_charge(SOC) − OCV_discharge(SOC)
```

静置质量判据（末端窗口漂移）：

```text
|dV/dt|_end < 2 mV/h  且  静置时长 ≥ 1800 s
```

## 3. 参数物理意义与单位

| 量 | 含义 | 单位 |
| --- | --- | --- |
| `OCV_charge/discharge` | 充电/放电方向准开路电压 | V |
| `H` | 充放电迟滞 | V |
| `SOC` | 荷电状态 | 1 |
| 查表点 | SOC 网格 0–1 共 201 点 | — |
| `dV/dt` | 静置末端漂移率 | V/h |

## 4. 实际文件路径

- `identification/ocv_extractor.py`
- `battery_models/ocv_model.py::IdentifiedOcvModel`
- `data/identified/ocv/ocv_soc_average.csv`
- `results/ocv/run_ocv_20261126_131453_852541/ocv_quality_report.json`

## 5. 实际类与函数

| 名称 | 作用 |
| --- | --- |
| `_branch_curve(...)` | 单方向低电流曲线，支持跨表去重与方向判定 |
| `extract_low_current_ocv(...)` | 同时提取充电/放电/平均/迟滞 |
| `relaxation_points(...)` | 增量 OCV 静置点与质量判据 |
| `build_ocv_table(average)` | 生成 201 点单调 SOC 表 |
| `IdentifiedOcvModel` | 查表插值，覆盖 [0,1]，禁止外推 |

## 6. 关键源码逐行解释

```python
mean_current = float(branch["current_a"].mean())
if abs(mean_current) > tolerance_a:      # 只接受低电流段
    continue
duplicate_removed = branch["time_s"].duplicated().sum()
branch = branch.drop_duplicates("time_s")  # 跨工作表重复时间戳
soc = anchor - cumulative_charge_ah(t, i) / capacity_ah
```

- 第 2–3 行用绝对平均电流筛选，避免把 1 A 工步误当 OCV；
- 第 4–5 行处理 SP3 跨表重复时间戳，避免积分重复计数；
- 第 6 行按锚点 SOC 积分，充电从 0 起、放电从 1 起。

## 7. 运行命令

```powershell
conda run -n kaifa_battery python -m scripts.ocv_extraction_demo
```

## 8. 实际结果

| 指标 | 数值 |
| --- | --- |
| 实测 OCV 点 | 147659（充电 69685 + 放电 77974） |
| 查表点数 | 201 |
| 覆盖 SOC | 0.0–1.0（端点由实测分支常量延伸） |
| 两方向共同区间 | 0.0–0.89 |
| 平均迟滞 | 96.9 mV |
| 最大迟滞 | 129 mV @ SOC 0.87 |
| 端点差 | 370 mV（带载截止差异，不是迟滞） |
| 跨样品（SP1 vs SP3） | 平均 6.36 mV，最大 23.2 mV |
| PCHIP 与线性最大差 | 11.6 mV |
| 增量 OCV | 22 段仅 1 段通过质量检查 → `NOT_VERIFIED` |

## 9. 已知局限

1. 低电流端电压仍是近似 OCV，不是绝对平衡电位；
2. 充电分支只到 SOC 0.893，高 SOC 段依赖放电分支实测值延伸；
3. 增量 OCV 静置不足，不能作为独立 OCV 真值；
4. 跨样品差异包含样品间真实差异，不能当作测量噪声。

## 10. 独立学习练习

1. 用 `ocv_hysteresis.csv` 复算平均迟滞并核对 96.9 mV；
2. 把插值改为 PCHIP，解释 11.6 mV 差异出现在哪些 SOC 区间；
3. 设计更严格的静置判据，说明会损失多少增量 OCV 点。

## 11. 相关面试题

1. 为什么端电压不等于 OCV？列出至少三项压降来源。
2. 充放电迟滞的物理来源是什么？为什么低温更明显？
3. OCV 查表为什么必须覆盖 [0,1] 且禁止外推？
