# 17 模型对比与外部交叉验证

## 1. 对比设计

同一工况、同一初始 SOC、同一 OCV 曲线下，只改变模型结构：

- Rint：R0；
- 一阶 RC：R0 + R1/C1；
- 二阶 RC：R0 + R1/C1 + R2/C2。

动态工况来自 `configs/stage2_cases.yaml` 的 A–F 六组。外部验证包括 PyBaMM 官方 Thevenin 模型与 CALCE 公开实验电流重放。

## 2. 专业公式

模型差异用同一时刻端电压差衡量：

```text
ΔV(t) = Vmodel2(t) - Vmodel1(t)
```

误差指标：

```text
MAE  = (1/N)·Σ|Vmodel - Vref|
RMSE = sqrt((1/N)·Σ(Vmodel - Vref)²)
```

时间加权版本用相邻采样间隔作为权重，避免采样不均匀导致的偏差。

## 3. 变量与单位

| 符号 | 含义 | 单位 |
| --- | --- | --- |
| Vref | 参考电压（解析、SPICE、PyBaMM 或实测） | V |
| N | 有效采样点数 | – |
| ΔV | 模型间电压差 | V |

## 4. 公式推导

各模型共享 SOC 与 OCV 计算，差异仅来自极化项：

```text
ΔV = (V1,2 + V2,2) - V1,1
```

因此模型差异在电流阶跃后迅速增大，在静置后逐渐收敛到 0，收敛速度由最慢时间常数决定。

## 5. 适用条件

- 模型间对比只能说明结构差异，不能说明谁更接近真实电池。
- PyBaMM 对比使用相同教学参数，验证的是实现一致性，不是模型精度。
- CALCE 重放未做参数辨识，只能作为基线。

## 6. 实际代码与核心函数

| 功能 | 路径 | 函数 |
| --- | --- | --- |
| 误差指标 | `analysis/model_comparison.py` | `error_metrics`、`time_weighted_metrics` |
| 时间对齐 | `analysis/model_comparison.py` | `align_series`、`compare_frames` |
| 动态工况对比 | `scripts/model_comparison_demo.py` | `main` |
| PyBaMM 交叉验证 | `battery_models/pybamm_backend.py` | `run_thevenin_teaching_case` |
| CALCE 重放 | `simulations/load_profiles.py` | `profile_from_frame` |

## 7. 关键代码逐行解释

```python
lower = max(reference_time[0], model_time[0], start_s or -inf)
upper = min(reference_time[-1], model_time[-1], end_s or inf)
mask = (reference_time >= lower) & (reference_time <= upper)
target_model = np.interp(target_time, model_time, model)
```

只在两条曲线共同覆盖的时间区间内插值，禁止外推；阶跃附近通过 `exclude_times_s` 与 `exclude_window_s` 排除。

## 8. 实际运行命令

```powershell
conda run -n kaifa_battery python -m scripts.model_comparison_demo
```

## 9. 真实结果：动态工况

运行编号：`stage2_20261126_123044_d2d0af`。

| 工况 | 指标 | Rint | 一阶 RC | 二阶 RC |
| --- | --- | --- | --- | --- |
| A 1A 恒流 600s | 末端电压 (V) | 3.728333 | 3.708333 | 3.693334 |
| B 2A 恒流 600s | 末端电压 (V) | 3.656667 | 3.616667 | 3.586668 |
| C 2A 60s 脉冲 | 最低电压 (V) | 3.731681 | 3.693682 | 3.674737 |
| C 2A 60s 脉冲 | 静置末端 (V) | 3.791667 | 3.791572 | 3.789006 |
| D 0.5/1/2A 分段 | 最低电压 (V) | 3.710847 | 3.670897 | 3.643087 |
| D 0.5/1/2A 分段 | 末端电压 (V) | 3.770833 | 3.768844 | 3.758612 |
| E −1.5A 充电 | 最高电压 (V) | 3.811250 | 3.811321 | 3.813245 |
| F 放电后充电 | 最低电压 (V) | 3.731681 | 3.693682 | 3.674737 |

模型间最大电压差（D 工况）：

- 二阶 − Rint：0.067764 V
- 二阶 − 一阶：0.027814 V

6 个工况 × 3 个模型的能量平衡全部为 `PASS_RELATIVE`。

## 10. 真实结果：PyBaMM Thevenin 交叉验证

| 指标 | 实际值 |
| --- | --- |
| PyBaMM 版本 | 26.11.0.0 |
| 模型 | `pybamm.equivalent_circuit.Thevenin`（2 RC） |
| 求解器 | IDAKLUSolver |
| 有效点数 | 1895 |
| MAE | 3.108 µV |
| RMSE | 4.077 µV |
| 最大误差 | 11.386 µV |
| PyBaMM 求解耗时 | 0.547 s |

说明：两者使用相同教学参数与相同电流定义，微伏级差异来自 PyBaMM 内部状态与插值方式。**PyBaMM 是官方模型，不是本项目自主求解器。**

原始证据：`results/stage2/run_stage2_20261126_123044_d2d0af/pybamm_comparison.csv`。

## 11. 真实结果：CALCE 电流重放

- 数据：`calce_inr18650_20r_sp2_25c_dst.csv.gz`，片段 60.01–1558.54 s，151 点（去除重复时间戳 150 点）。
- 初始 SOC 0.6、教学参数、教学 OCV 曲线，均未辨识。
- 状态：`UNCALIBRATED_BASELINE`。

| 模型 | MAE | RMSE | 最大误差 |
| --- | --- | --- | --- |
| Rint | 0.299275 V | 0.299492 V | 0.364933 V |
| 二阶 RC | 0.333052 V | 0.333280 V | 0.364933 V |

二阶模型的误差反而略大，原因是教学 OCV 曲线与初始 SOC 均不匹配该电芯，增加极化支路并不能修正系统性偏差。这组数据必须如实保留，不能通过调参“美化”。

## 12. 为什么二阶 RC 不一定更准确

1. 模型结构必须匹配真实过程；参数错误时增加支路只会增加偏差。
2. 本阶段未做参数辨识，二阶多的那一项没有物理依据。
3. CALCE 的误差主要来自 OCV 与初始 SOC 失配，而不是极化项数量。
4. 真实精度结论必须建立在独立训练/验证集与辨识参数上，属于第三阶段。

## 13. 常见错误

- 用同一段数据既拟合又验证。
- 只报告最好看的模型，不报告更差的模型。
- 把 PyBaMM 官方结果写成自研成果。
- 把 CALCE 重放误差写成“模型精度 0.33 V”。

## 14. 独立练习

1. 用 `error_metrics` 计算一阶与二阶在 C 工况的误差。
2. 将排除窗口改为 0，观察误差如何变化并解释。
3. 设计一个只含充电的工况，比较三种模型。

## 15. 面试题

1. 模型对比实验应如何控制变量？
2. 为什么参数辨识与模型验证必须分开？
3. 如何判断一个更复杂的模型是否值得使用？
4. PyBaMM 与自研模型交叉验证能证明什么、不能证明什么？
5. 面对公开数据误差较大时，应如何定位原因？
