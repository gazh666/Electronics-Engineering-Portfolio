# 24 RC 参数辨识（静置恢复、边界与可辨识性）

## 1. 专业原理

静置后电压按指数恢复。一阶 RC：

```text
V(t) = V∞ + A·exp(−t/τ1)
```

二阶 RC：

```text
V(t) = V∞ + A1·exp(−t/τ1) + A2·exp(−t/τ2)，τ1 < τ2
```

由脉冲电流 `I_p` 与脉宽 `T_p` 反推支路参数：

```text
R_i = A_i / [I_p · (1 − exp(−T_p/τ_i))]
C_i = τ_i / R_i
```

## 2. 公式推导

静置期间支路电压按 `V_i(t) = V_i(0)·exp(−t/τ_i)` 衰减，端电压是各支路与 OCV 之和。
把 `A_i = V_i(0)` 与脉冲结束时的稳态极化 `I_p·R_i·(1−exp(−T_p/τ_i))` 联立，即得上面的 `R_i`、`C_i`。
离散递推（求解器使用）：

```text
V_i,k+1 = V_i,k·exp(−Δt/τ_i) + I_k·R_i·(1 − exp(−Δt/τ_i))
```

## 3. 参数物理意义与单位

| 参数 | 含义 | 单位 |
| --- | --- | --- |
| `R1` | 快极化电阻 | Ω |
| `C1` | 快极化电容 | F |
| `τ1 = R1·C1` | 快时间常数 | s |
| `R2` | 慢极化电阻 | Ω |
| `C2` | 慢极化电容 | F |
| `τ2 = R2·C2` | 慢时间常数 | s |
| `V∞` | 静置稳态电压 | V |

## 4. 实际文件路径

- `identification/relaxation_fitter.py`
- `identification/parameter_validator.py`
- `configs/parameter_bounds.yaml`
- `results/pulse_identification/run_pulse_identification_20261126_132427_a51bf8/relaxation_fits.csv`
- `results/identification/run_identification_20261126_131901_fb66db/parameter_quality.json`

## 5. 实际类与函数

| 名称 | 作用 |
| --- | --- |
| `fit_relaxation(t, v, order, tau1_bounds_s, tau2_bounds_s)` | 一/二阶指数拟合 |
| `RelaxationFitResult.derive_rc(I_p, T_p)` | 由幅值反推 R、C |
| `validate_parameters(parameters, bounds)` | 正参数、顺序、边界检查 |
| `check_bounds(...)` | 返回触界参数名 |
| `identifiability_report(jacobian, names)` | 条件数与相关性 |
| `combine_quality(*statuses)` | 按严重程度合并质量状态 |

## 6. 关键源码逐行解释

```python
log_tau1 = vector[2]
log_delta = vector[4]
tau1 = 10 ** log_tau1
tau2 = tau1 + 10 ** log_delta        # 参数化保证 tau2 > tau1
model = v_inf + a1 * np.exp(-t / tau1) + a2 * np.exp(-t / tau2)
residual = model - voltage
```

- 第 1–4 行用 `tau1 + 正增量` 表示 `tau2`，从参数化上消除顺序约束；
- 第 5 行双指数模型；
- 第 6 行残差，交给 `least_squares` 最小化。

边界检查（`check_bounds`）：落在 `[low + 1%span, high − 1%span]` 之外即记为 `*_lower/*_upper`。
质量状态优先级：`OPTIMIZATION_FAILED > INSUFFICIENT_DATA > WEAKLY_IDENTIFIABLE > BOUND_LIMITED > NOT_VERIFIED > IDENTIFIED`。

## 7. 运行命令

```powershell
conda run -n kaifa_battery python -m scripts.pulse_identification_demo
conda run -n kaifa_battery python -m scripts.ecm_identification_demo
```

## 8. 实际结果

| 实验 | 阶数 | RMSE | τ1 | τ2 | 反推 R1 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| DST 50% | 1 | 2.54 mV | 300 s（触上界） | — | 26.00 mΩ | WEAKLY_IDENTIFIABLE |
| DST 50% | 2 | 0.32 mV | 119.3 s | 2245.4 s | 12.41 mΩ | IDENTIFIED |
| DST 80% | 1 | 0.90 mV | 300 s（触上界） | — | 13.25 mΩ | WEAKLY_IDENTIFIABLE |
| DST 80% | 2 | 0.24 mV | 51.3 s | 1582.9 s | 16.71 mΩ | IDENTIFIED |

动态辨识结果（DST 50%，`least_squares`）：

| 模型 | R0 | R1 | C1 | τ1 | R2 | C2 | τ2 | 状态 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Rint | 88.43 mΩ | N/A | N/A | N/A | N/A | N/A | N/A | IDENTIFIED |
| 一阶 RC | 77.07 mΩ | 22.84 mΩ | 788.6 F | 18.02 s | N/A | N/A | N/A | IDENTIFIED |
| 二阶 RC | 75.86 mΩ | 18.25 mΩ | 638.0 F | 11.64 s | 7.38 mΩ | 13555.6 F | 100.0 s | BOUND_LIMITED |

二阶 `τ2` 触及下界 100 s，多初值离散度高（R2 46.7%、τ2 202.9%），因此标记 `BOUND_LIMITED`，
不宣称两个时间常数都可靠。

## 9. 已知局限

1. 静置拟合只覆盖 2 个长静置段，不能证明参数在全 SOC 范围成立；
2. 一阶模型 τ1 触上界 300 s，说明观测窗口内快慢过程不可分；
3. 二阶 τ2 触下界，`R2` 与 `τ2` 强相关；
4. 条件数只反映局部线性化，不是严格置信区间。

## 10. 独立学习练习

1. 用 `derive_rc` 手算 DST50 二阶的 R1、C1，核对 12.41 mΩ、9608 F；
2. 把 τ2 下界改为 50 s，观察拟合与质量状态变化；
3. 解释为什么 `log10 τ` 参数化比直接拟合 τ 更稳定。

## 11. 相关面试题

1. 一阶 RC 的 τ 触界意味着什么？工程上如何处理？
2. 为什么二阶 RC 不一定优于一阶 RC？
3. 参数可辨识性差时，BMS 应该保留全局参数还是做查表？依据是什么？
