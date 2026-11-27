# 23 欧姆内阻 R0 辨识（脉冲/阶跃）

## 1. 专业原理

内阻由欧姆电阻、电荷转移与扩散共同贡献。采样分辨率有限时，无法把纯欧姆压降与毫秒级快极化分开，
因此本项目定义 **1 s 窗口表观内阻**：

```text
R0_apparent = |ΔV| / |ΔI|   （阶跃后 1 s 窗口内电压变化）
```

它是“指定时间尺度下的等效内阻”，不是电化学意义上的纯欧姆电阻。

## 2. 公式推导

阶跃时刻 `t_s`，取窗口 `[t_s, t_s + 1 s]`：

```text
ΔV = V(t_s + 1 s) − V(t_s)
ΔI = I(t_s + 1 s) − I(t_s)
R0 = −ΔV / ΔI
```

负号保证放电（`ΔI > 0`）时 `R0 > 0`。SOC 分箱中位数：

```text
R0_bin(SOC_i) = median{ R0_k : SOC_k ∈ bin_i }
```

## 3. 参数物理意义与单位

| 量 | 含义 | 单位 |
| --- | --- | --- |
| `R0_apparent` | 1 s 窗口表观内阻 | Ω（报告 mΩ） |
| `ΔI` | 电流阶跃幅值 | A |
| `ΔV` | 窗口内电压变化 | V |
| `SOC_bin` | 0.2 宽 SOC 分箱 | 1 |
| 有效样本 | 满足最小阶跃与稳定性的阶跃数 | 个 |

## 4. 实际文件路径

- `identification/pulse_detector.py`
- `identification/resistance_estimator.py`
- `results/pulse_identification/run_pulse_identification_20261126_132427_a51bf8/pulse_summary.json`
- `results/pulse_identification/run_pulse_identification_20261126_132427_a51bf8/soc_parameter_exploration.json`

## 5. 实际类与函数

| 名称 | 作用 |
| --- | --- |
| `DetectionConfig` | 静置容差、最小阶跃、最小脉宽、稳定窗口 |
| `detect_events(...)` | 检测电流阶跃事件与表 |
| `detect_steps_within_dynamic(...)` | 在动态段内检测阶跃 |
| `estimate_from_steps(frame, steps, window_s)` | 1 s 窗口 R0 |
| `soc_binned_resistance(resistance)` | SOC 分箱中位数与样本数 |

## 6. 关键源码逐行解释

```python
after = frame[frame["time_s"] >= step_time_s + window_s]
if after.empty:                    # 窗口不足，拒绝
    continue
delta_v = after["voltage_v"].iloc[0] - frame.loc[frame["time_s"] >= step_time_s, "voltage_v"].iloc[0]
delta_i = after["current_a"].iloc[0] - frame.loc[frame["time_s"] >= step_time_s, "current_a"].iloc[0]
if abs(delta_i) < minimum_current_change_a:   # 小信号不可辨识
    continue
r0 = -delta_v / delta_i
```

- 第 1–2 行保证窗口完整；
- 第 3–4 行分别取窗口两端电压、电流；
- 第 5–6 行拒绝过小阶跃，避免噪声放大；
- 第 7 行按符号约定给出正值内阻。

## 7. 运行命令

```powershell
conda run -n kaifa_battery python -m scripts.pulse_identification_demo
```

## 8. 实际结果

| 实验 | 有效样本 | 中位数 | 均值 | P05–P95 | 最大 |
| --- | --- | --- | --- | --- | --- |
| DST 50% | 281 | 71.56 mΩ | 73.64 mΩ | 69.87–85.23 mΩ | 124.57 mΩ |
| DST 80% | 446 | 71.61 mΩ | 72.62 mΩ | 69.95–78.60 mΩ | 116.70 mΩ |

SOC 分箱（Task 25 可选探索，仅训练数据）：

| SOC 区间 | DST50 样本/中位数 | DST80 样本/中位数 |
| --- | --- | --- |
| 0.0–0.2 | 106 / 75.72 mΩ | 105 / 74.72 mΩ |
| 0.2–0.4 | 115 / 71.16 mΩ | 111 / 71.42 mΩ |
| 0.4–0.6 | 60 / 70.89 mΩ | 114 / 71.04 mΩ |
| 0.6–0.8 | 0 / N/A | 114 / 71.84 mΩ |
| 0.8–1.0 | 0 / N/A | 2 / 71.36 mΩ（样本不足） |

结论：R0 在 0–0.6 SOC 内中位数仅变化约 4.8 mΩ，可保留全局常参数；若做分段常数查表，0.6 以上必须
标 `NOT_VERIFIED`，不得外推。R1/tau 的 SOC 依赖因独立静置段只有 2 个，`INSUFFICIENT_DATA`，保留全局参数。

## 9. 已知局限

1. 1 s 窗口包含快速极化，R0 偏大；
2. 采样分辨率与阶跃时刻对齐误差会引入偏差；
3. 低 SOC 端样本少，分箱不稳定；
4. 验证集未参与 R0(SOC) 选择，避免信息泄漏。

## 10. 独立学习练习

1. 把窗口改为 0.5 s / 2 s，观察 R0 变化并解释；
2. 用 P05–P95 估计分箱不确定性；
3. 说明为什么不能用 FUDS 验证集决定 R0(SOC) 查表值。

## 11. 相关面试题

1. 为什么电池内阻随 SOC 与温度变化？
2. 1 s、10 ms、1 kHz 测得的内阻为什么不同？
3. 如何区分欧姆内阻与电荷转移内阻？实验上怎么设计？
