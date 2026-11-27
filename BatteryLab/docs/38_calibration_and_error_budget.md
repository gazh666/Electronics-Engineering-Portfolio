# 38 校准与工程误差预算

## 1. 电路拓扑

```text
真实输入 x ──采集链路── 读数 y ──校准模型── 估计 x̂
                              │
                     y = a*x + b
                     x̂ = (y−b)/a
```

校准不改变硬件，只修正可重复的系统误差。

## 2. 专业原理

- 零点校准只修正截距：适合失调主导的电流通道。
- 两点校准同时修正增益与截距：适合电压/温度通道。
- 校准集与验证集必须分离；验证点不得参与拟合。
- 校准不能消除随机噪声、非线性、温漂与未建模的共模误差。

## 3. 公式推导

```text
a = (y2−y1)/(x2−x1)
b = y1 − a*x1
x̂ = (y−b)/a
```

误差指标：

```text
MAE = mean(|x̂−x|)
RMSE = sqrt(mean((x̂−x)²))
Max = max(|x̂−x|)
```

误差预算：

```text
worst_case = Σ|e_i|
RSS = sqrt(Σe_i²)
```

## 4. 变量及单位

| 量 | 含义 | 单位 |
| --- | --- | --- |
| `a` | 校准增益（输出/输入） | 1 |
| `b` | 校准截距 | 与输入同单位 |
| `x` | 真实输入 | V/A/℃ |
| `y` | 采集读数 | V/A/℃ |
| `MAE/RMSE/Max` | 误差指标 | mV/mA/℃ |

## 5. 实际器件参数来源

- 校准点：电压 3.0/4.1 V；电流 −2.0/+2.0 A；温度 0/60 ℃。
- 验证点：电压 2.5/3.3/3.7/3.9/4.25 V；电流 ±2.5/±1.5/±0.5 A；温度 10/20/25/30/40/50 ℃。
- 容差：0.1% 电阻、1% 分流电阻、±1% NTC R25/B、±1% 上拉；均匀独立分布，seed 42，1000 组。
- 这些是**教学容差假设**，不是真实生产批次分布或良率。

## 6. 实际核心源码

- `sensing/calibration.py`
- `analysis/tolerance_analysis.py`
- `analysis/error_budget.py`
- `scripts/calibration_demo.py`
- `scripts/sensing_tolerance_demo.py`

## 7. 函数名称及行号

| 名称 | 位置 | 作用 |
| --- | --- | --- |
| `CalibrationModel` | `sensing/calibration.py:28` | 校准模型 |
| `fit_zero_calibration` | `sensing/calibration.py:65` | 零点校准 |
| `fit_two_point_calibration` | `sensing/calibration.py:77` | 两点校准 |
| `calibration_error_report` | `sensing/calibration.py:112` | 误差指标 |
| `run_voltage_tolerance` | `analysis/tolerance_analysis.py:234` | 电压容差 |
| `run_current_tolerance` | `analysis/tolerance_analysis.py:292` | 电流容差 |
| `run_temperature_tolerance` | `analysis/tolerance_analysis.py:352` | 温度容差 |
| `voltage_error_budget` | `analysis/error_budget.py:91` | 电压预算 |
| `current_error_budget` | `analysis/error_budget.py:197` | 电流预算 |
| `temperature_error_budget` | `analysis/error_budget.py:292` | 温度预算 |

## 8. 核心代码逐行解释

```python
model = fit_two_point_calibration(cal1, meas1, cal2, meas2)   # 只用校准点
measured = [reading(device, point) for point in validation]    # 独立验证点
post = [model.apply(v) for v in measured]
```

- 第 1 行只用两个预先登记的校准点，验证点不参与；
- 第 2 行在**同一个器件实例**上读验证点；
- 第 3 行应用校准，保证前后比较的是同一组随机参数。

## 9. 实际运行命令

```powershell
conda run -n kaifa_battery python -m scripts.calibration_demo
conda run -n kaifa_battery python -m scripts.sensing_tolerance_demo
```

## 10. 实际图表及原始结果路径

校准 Run ID：`sensing_20261126_135458_c01b86`

- `results/sensing/run_sensing_20261126_135458_c01b86/plots/20_voltage_calibration.png`
- `results/sensing/run_sensing_20261126_135458_c01b86/plots/21_current_calibration.png`
- `results/sensing/run_sensing_20261126_135458_c01b86/plots/22_temperature_calibration.png`

容差 Run ID：`sensing_20261126_135449_d8a6d3`

- `results/sensing/run_sensing_20261126_135449_d8a6d3/plots/23_voltage_tolerance_histogram.png`
- `results/sensing/run_sensing_20261126_135449_d8a6d3/plots/24_current_tolerance_histogram.png`
- `results/sensing/run_sensing_20261126_135449_d8a6d3/plots/25_temperature_tolerance_histogram.png`
- `results/sensing/run_sensing_20261126_135449_d8a6d3/plots/26_calibration_improvement.png`
- `results/sensing/run_sensing_20261126_135449_d8a6d3/plots/27_voltage_budget.png`
- `results/sensing/run_sensing_20261126_135449_d8a6d3/plots/28_current_budget.png`

### 10.1 单组校准示例（5/6 个验证点）

| 通道 | 校准前最大 | 零点后最大 | 两点后最大 |
| --- | --- | --- | --- |
| 电压 | 2.4714 mV | — | 0.000858 mV |
| 电流 | 10.7286 mA | 8.7316 mA | ≈0（1e−13 A） |
| 温度 | 0.4507 ℃ | — | 0.02050 ℃ |

### 10.2 1000 组容差

| 通道 | 校准前 RMSE | 校准后 RMSE | 校准后最大 | RMSE 改善 |
| --- | --- | --- | --- | --- |
| 电压 | 7.585 mV | 0.873 mV | 3.226 mV | 88.49% |
| 电流 | 6.525 mA | 0.840 mA | 3.004 mA | 87.13% |
| 温度 | 0.1596 ℃ | 0.01994 ℃ | 0.0726 ℃ | 87.51% |

### 10.3 最坏情况预算（线性叠加 / RSS）

| 通道 | 最坏情况 | RSS | 主导项 |
| --- | --- | --- | --- |
| 电压 | **30.887 mV** | 23.189 mV | 四电阻失配 22.679 mV |
| 电流 | **37.736 mA** | 15.868 mA | 分流电阻容差 12.5 mA |
| 温度 | **0.2457 ℃** | 0.2248 ℃ | NTC R25 容差 0.2238 ℃ |

角点 SPICE 与解析最大偏差：**16.25 µV**（12 次 SPICE 复验）。

## 11. 常见错误

1. 用验证点重新拟合校准系数，制造“零误差”。
2. 把 1000 组随机样本通过比例当商业良率。
3. 把统计最大误差 3.226 mV 当“保证最坏情况”。
4. 认为两点校准能消除温漂与非线性。
5. 零点校准后仍保留增益误差却宣称全量程达标。

## 12. 独立学习练习

1. 用 20 组样本重复容差实验，比较与 1000 组的差异。
2. 把校准点移出量程中心，观察外推误差。
3. 把电阻容差从 0.1% 改为 1%，重算电压预算。

## 13. 面试问题

1. 零点校准与两点校准分别修正什么？
2. 为什么校准不能消除全部误差？
3. 如何进行工程误差预算？
4. 最坏情况与 RSS 有什么区别？
5. 如何证明校准没有数据泄漏？
