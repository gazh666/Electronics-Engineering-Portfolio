# 26 动态工况独立验证与模型选择

## 1. 专业原理

参数在 DST 50% 上辨识并冻结后，在从未参与调参的 FUDS/US06/BJDST 上做开环电压预测。
验证阶段不允许：调参、用验证电压修正 SOC 或极化状态、用验证结果反向选择参数。

## 2. 公式推导

开环仿真：

```text
SOC_{k+1} = SOC_k − I_k Δt/(3600Q)，SOC_0 由容量平衡给定
V_k = OCV(SOC_k) − I_k R0 − V_1,k − V_2,k
```

误差指标（`e_k = V_pred,k − V_meas,k`）：

```text
RMSE = sqrt(mean(e²))，MAE = mean(|e|)，P95 = percentile(|e|, 95)，Max = max|e|
```

模型选择：若高阶模型相对低阶的 RMSE 改善 < 10%，优先低阶。

## 3. 参数物理意义与单位

| 量 | 含义 | 单位 |
| --- | --- | --- |
| `RMSE` | 均方根误差 | mV |
| `MAE` | 平均绝对误差 | mV |
| `P95` | 95% 分位绝对误差 | mV |
| `Max` | 最大瞬时绝对误差 | mV |
| `bias` | 平均有符号误差 | mV |

## 4. 实际文件路径

- `validation/dynamic_validation.py`
- `validation/model_selection.py`
- `analysis/residual_analysis.py`
- `results/dynamic_validation/run_dynamic_validation_20261126_131720_0e4677/`
  （`validation_summary.csv`、`validation_metrics.json`、`frozen_parameters.yaml`、`validation_manifest.json`、
  `predicted_waveform.csv.gz`、`residuals.csv.gz`）

## 5. 实际类与函数

| 名称 | 作用 |
| --- | --- |
| `run_open_loop_validation(experiment, frozen)` | 冻结参数开环预测与指标 |
| `validate_all_models(...)` | 多模型批量验证 |
| `validation_table(results)` | 汇总表 |
| `aggregate_validation_rmse(table, prefix)` | 聚合验证 RMSE |
| `select_model(...)` | 10% 阈值优先低阶 |
| `residual_correlations / steady_state_bias / worst_error_windows` | 残差诊断 |

## 6. 关键源码逐行解释

```python
result = simulate_ecm(..., stop_on_limits=False)      # 验证不因限压提前终止
prediction = np.interp(time_values, result.frame["time_s"], result.frame["terminal_voltage_v"])
waveform = pd.DataFrame({..., "residual_v": prediction - measured})
```

- 第 1 行：关闭限压终止，保证整段可比；
- 第 2 行：插值到实测时间轴，避免采样点不一致；
- 第 3 行：保存逐点残差，供区间统计与图表。

## 7. 运行命令

```powershell
conda run -n kaifa_battery python -m scripts.dynamic_validation_demo
```

## 8. 实际结果

预先登记限值：RMSE ≤ 30 mV、MAE ≤ 25 mV、最大绝对误差 ≤ 100 mV。

| 工况 | 模型 | MAE | RMSE | P95 | Max | 点数 |
| --- | --- | --- | --- | --- | --- | --- |
| FUDS 50% | Rint | 16.82 | 24.96 | 42.39 | 319.67 | 6995 |
| FUDS 50% | 一阶 RC | 12.33 | 22.61 | 39.28 | 321.38 | 6995 |
| FUDS 50% | 二阶 RC | 12.03 | 22.62 | 39.31 | 321.07 | 6995 |
| FUDS 80% | Rint | 21.97 | 28.45 | 49.71 | 370.69 | 11092 |
| FUDS 80% | 一阶 RC | 16.11 | 22.15 | 34.13 | 371.76 | 11092 |
| FUDS 80% | 二阶 RC | 15.65 | 21.73 | 33.14 | 375.84 | 11092 |

额外工况（一阶 RC）：US06 50% 53.60 mV、US06 80% 51.10 mV、BJDST 50% 40.65 mV、BJDST 80% 48.91 mV；
DST 80% 开发集 27.77 mV。

模型选择：一阶 RC。依据：二阶相对一阶 FUDS RMSE 改善约 0.9%（< 10%），且二阶参数 `BOUND_LIMITED`。

验收：RMSE 与 MAE 全部达标；最大瞬时误差 375.84 mV 超标，**整体保留 FAIL**。
失败集中在 SOC 1.1%–1.5%、4 A 大电流末端，属于空电区非线性与参数外推误差。

## 9. 已知局限

1. 最大误差出现在 SOC 低于训练区间下沿（0.011）附近，属于外推；
2. US06/BJDST 误差 40–54 mV，说明模型对更激进工况泛化有限；
3. 全部为 25 ℃；
4. 未使用 EKF/UKF 闭环修正，开环误差是上界。

## 10. 独立学习练习

1. 用 `residuals.csv.gz` 复算 FUDS 80% 的 P95；
2. 找出最大误差对应的时间点与 SOC，解释成因；
3. 把模型选择阈值改为 5%，结论是否变化？

## 11. 相关面试题

1. 为什么训练误差和独立验证误差必须分开报告？
2. RMSE 达标但最大误差超标，工程上能否接受？如何设保护策略？
3. 开环验证与闭环（EKF）验证的差异是什么？
