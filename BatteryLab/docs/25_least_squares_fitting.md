# 25 最小二乘参数辨识（DST 动态工况）

## 1. 专业原理

在真实动态电流下，模型端电压由 OCV 查表、欧姆压降与 RC 极化共同决定。辨识即求参数使残差平方和最小：

```text
min_θ  Σ_k [V_model(t_k; θ) − V_measured(t_k)]²
```

`θ = [R0, R1, log10 τ1, R2, log10 τ2]`。用对数参数化时间常数，避免量纲差异导致条件数恶化。

## 2. 公式推导

离散状态更新（零阶保持）：

```text
SOC_{k+1} = SOC_k − I_k·Δt/(3600Q)
V_i,k+1 = V_i,k·exp(−Δt/τ_i) + I_k·R_i·(1 − exp(−Δt/τ_i))
V_k = OCV(SOC_k) − I_k·R0 − Σ_i V_i,k
```

残差：

```text
r_k = V_k(θ) − V_measured,k
```

`scipy.optimize.least_squares(method="trf")` 在边界内求解。SOC 越界时附加惩罚残差 `0.5·√violation`，
继续算术积分，避免求解器因异常中断。

## 3. 参数物理意义与单位

| 参数 | 含义 | 单位 | 典型边界 |
| --- | --- | --- | --- |
| `R0` | 欧姆内阻 | Ω | 0.02–0.15 |
| `R1` | 快极化电阻 | Ω | 0.002–0.05 |
| `τ1` | 快时间常数 | s | 5–300 |
| `R2` | 慢极化电阻 | Ω | 0.002–0.05 |
| `τ2` | 慢时间常数 | s | 100–5000 |

## 4. 实际文件路径

- `identification/ecm_fitter.py`
- `configs/identification_config.yaml`
- `configs/parameter_bounds.yaml`
- `results/identification/run_identification_20261126_131901_fb66db/`
  （`identification_config.yaml`、`dataset_manifest.json`、`optimization_trials.csv`、`training_metrics.json`、
  `identified_parameters.yaml`、`training_waveform.csv.gz`）

## 5. 实际类与函数

| 名称 | 作用 |
| --- | --- |
| `simulate_voltage(...)` | 纯 numpy 前向仿真，捕获 `StateError` 走惩罚路径 |
| `fit_single_start(...)` | 单初值 `least_squares` |
| `multi_start_fit(...)` | 多初值，返回 best/trials/spread |
| `ocv_callable(model)` | 把查表模型转为函数 |
| `_pack_vector/_unpack_vector` | 参数向量与字典互转 |

## 6. 关键源码逐行解释

```python
try:
    soc = update_soc(soc, current, dt, capacity_ah)
except StateError:
    violation += abs(soc)                  # 记录越界量
    soc = max(min(soc, 1.0), 0.0)          # 仅用于继续积分
residual = predicted_voltage - measured_voltage
if violation > 0:
    residual = np.concatenate([residual, [0.5 * np.sqrt(violation)]])
```

- 第 1–4 行：越界不静默夹紧，先累计越界量再临时夹紧；
- 第 5 行：主残差；
- 第 6–7 行：附加惩罚残差，让优化器“感知”越界成本。

## 7. 运行命令

```powershell
conda run -n kaifa_battery python -m scripts.ecm_identification_demo
conda run -n kaifa_battery python -m scripts.ecm_identification_demo --refit   # 需要重新拟合时
```

默认复用 `data/identified/model_*/` 冻结模型，不无条件重跑优化器。

## 8. 实际结果

训练集 DST 50%（6685 点，SOC 0.011–0.507），25 ℃：

| 模型 | 训练 RMSE | 训练 MAE | 最大误差 | 条件数 | 质量 |
| --- | --- | --- | --- | --- | --- |
| Rint | 28.83 mV | 15.13 mV | 421.77 mV | — | IDENTIFIED |
| 一阶 RC | 25.99 mV | 12.03 mV | 421.77 mV | 2.84 | IDENTIFIED |
| 二阶 RC | 25.94 mV | 11.66 mV | 422.30 mV | 8.91 | BOUND_LIMITED |

开发集 DST 80%（10621 点）：Rint 33.06 mV、一阶 27.77 mV、二阶 27.34 mV。
二阶相对一阶训练改善仅 0.19%，不构成模型升级理由。

## 9. 已知局限

1. 训练残差非白噪声，存在系统性偏置；
2. 二阶参数弱可辨识，τ2 触下界；
3. OCV 来自 SP1，动态数据来自 SP2，属跨样品模型；
4. 仅 25 ℃，参数不可外推到其他温度；
5. 训练成功不等于参数唯一。

## 10. 独立学习练习

1. 把 `log10 τ` 换成直接拟合 τ，比较迭代次数与条件数；
2. 去掉 SOC 惩罚项，观察越界与拟合结果；
3. 用 3 个初值重跑一阶模型，记录 RMSE 离散度。

## 11. 相关面试题

1. 为什么最小二乘可以用于电池模型辨识？它对噪声分布有什么假设？
2. 多初值拟合解决什么问题？如何判断结果一致？
3. 参数触界时应该报告什么？为什么不能直接采用触界值？
