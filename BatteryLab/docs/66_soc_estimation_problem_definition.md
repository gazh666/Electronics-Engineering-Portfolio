# 66 SOC 估计问题定义与符号约定

日期：2026-11-26
对应源码：`estimation/models.py`、`estimation/coulomb_counter.py`、`configs/soc_estimation.yaml`

## 1. 统一符号

| 符号 | 含义 | 单位 |
| --- | --- | --- |
| `SOC` | 荷电状态 | 0–1（报告时用 % 或 pp） |
| `I` | 电流，**放电为正、充电为负** | A |
| `Q` | 可用容量 | Ah |
| `t` | 时间 | s |
| `V_t` | 端电压 | V |
| `OCV(SOC)` | 开路电压 | V |
| `R0` | 欧姆内阻 | Ω |
| `R1, tau1` | 一阶 RC 极化 | Ω, s |
| `Vp` | 极化电压 | V |

方向约定与第二至第六阶段一致。**符号搞反是 SOC 估计最常见的致命错误**：
若把充电电流当放电，SOC 会朝反方向漂移，且残差反馈会把错误"修正"得更快。

## 2. 基本方程

安时积分（`estimation/coulomb_counter.py:37`）：

```text
SOC_{k+1} = SOC_k - I_eff,k · Δt_k / (3600 · Q)
I_eff = I / η_dis   (I ≥ 0)
I_eff = I · η_chg   (I < 0)
```

本阶段默认 `η_dis = η_chg = 1.0`，原因：CALCE 公开数据没有提供可信的库仑效率
标定，凭空设 0.99 会引入不可验证的系统偏差。效率作为参数保留，便于后续实测。

一阶 RC 端电压（`estimation/ecm_observer.py:58`）：

```text
Vp,k+1 = Vp,k · exp(-Δt/τ1) + I_k · R1 · (1 - exp(-Δt/τ1))
V_t,k+1 = OCV(SOC_{k+1}) - R0 · I_{k+1} - Vp,k+1
```

## 3. 时间轴约定

- 区间 `[t_k, t_k+1)` 内用 `I_k` 推进 SOC 与 RC；
- 到达 `t_k+1` 后用该时刻测量电压计算残差；
- 时间戳严格递增（`estimation/models.py:82` 的 `validate_sample_sequence` 直接报错重复/倒退）；
- 单步间隔超过 `maximum_sample_gap_s = 2.0` 标记 `DATA_GAP`，**不跨缺口积分**。

## 4. 为什么需要"参考 SOC"而不是"真实 SOC"

公开数据没有直接测量 SOC 的传感器。本阶段的参考轨迹由：

```text
SOC0 = 1 - qd_start / Q_measured
SOC_ref(t) = SOC0 - ∫ I dt / (3600 · Q_measured)
```

得到（`configs/dataset_split.yaml` 的 `initial_soc_method`）。

因此必须写清：

- 参考量类型是 `experimental_soc_reference`，不是 `measured_true_soc`；
- 若估计器使用同一电流、同一容量、同一初始 SOC，二者一致只能证明**积分实现
  一致**，不能证明绝对精度；
- 参考 SOC 可能略低于 0（容量口径差异），评价时掩码 `0 ≤ ref ≤ 1` 并报告覆盖率。

## 5. 数据质量规则（本阶段硬约束）

| 规则 | 实现位置 | 后果 |
| --- | --- | --- |
| 无效电流不得积分 | `estimation/estimation_runner.py:45` | 输出 `INVALID_CURRENT` |
| 缺口不得跨越 | 同上 | 输出 `DATA_GAP`，SOC 记 `None` |
| 无效电压只预测不校正 | `estimation/estimation_runner.py:203` | `PREDICT_ONLY_INVALID_VOLTAGE` |
| 未知 SOC 不得填 0 | `SOCEstimate` / 回放行 | 缺失值为 `None` |
| 限幅必须记录 | `CoulombCounter.bound_events` | 保留原始未限幅 SOC |

## 6. 典型错误

1. 把参考 SOC 当"真值"，声称"RMSE=0 说明算法准"。
2. 在缺口处直接跨过去积分，把数小时未知电流当零。
3. 电压无效时仍做残差校正，用 0 V 或上一次电压冒充。
4. SOC 限幅后不记录，掩盖积分发散。
5. 电流符号与 ECM 约定不一致。

## 7. 运行命令

```bash
conda run -n kaifa_battery python -m scripts.coulomb_counting_demo
```

结果目录：`results/soc_estimation/run_soc_estimation_20261126_161605_b57ca5`
（`estimation_metrics.json`、`reference_soc.csv`、`estimated_soc.csv`）。

## 8. 练习与面试题

练习：

1. 把 `CoulombCounter` 的电流符号整体取反，观察 DST 上的 SOC 曲线如何变化。
2. 人为在 us06_50 中插入 10 s 缺口，检查 `DATA_GAP` 行数与 SOC 是否被标记 `None`。

面试题：

1. 为什么"参考 SOC 由同一电流积分"时，纯安时积分 RMSE 必然接近 0？
2. 采样间隔 1.559 s 与 2 s 门限的关系是什么？若采样率更低应如何改？
3. 库仑效率设为 1.0 是"忽略损耗"还是"没有可信标定"？两者在报告中如何区分？
