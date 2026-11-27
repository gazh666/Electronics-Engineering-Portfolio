# 14 脉冲响应分析

## 1. 分析对象

标准工况：`0–10 s` 静置、`10–70 s` 2 A 放电、`70–190 s` 静置，输出步长 0.1 s，初始 SOC 0.6，OCV 分别使用固定 3.8 V 与教学查表。

## 2. 指标定义与公式

| 指标 | 定义 |
| --- | --- |
| 接入前电压 | 接入前 5 s 端电压均值 |
| 瞬时压降 | 接入前电压 - 接入后首个采样电压 |
| R0 估计 | 瞬时压降 / ΔI |
| 脉冲结束电压 | 释放前最后一个采样点端电压 |
| 最大压降 | 接入前电压 - 脉冲期间最小端电压 |
| 恢复跳变 | 释放后首个采样电压 - 释放前电压 |
| 恢复时间 | 释放后首次进入容差带并保持指定时长的相对时间 |

R0 估计式：

```text
R0_est = (Vbefore - Vafter) / (Iafter - Ibefore)
```

恢复判定：参考电压 `Vref = Vbefore`，容差 1 mV，连续保持 1 s，观察窗 120 s；不满足则 `NOT_RECOVERED`。

## 3. 变量与单位

| 符号 | 含义 | 单位 |
| --- | --- | --- |
| Vbefore | 接入前平均端电压 | V |
| Vafter | 接入后首个采样电压 | V |
| ΔI | 电流变化 | A |
| trec | 恢复时间 | s |

## 4. 公式推导

接入瞬间电容电压未变化，只有 R0 响应电流阶跃：

```text
V(t0+) - V(t0-) = -ΔI·R0
```

因此两点差分即可反推 R0。释放瞬间同理，端电压回升 ΔI·R0；但此时 RC 极化尚未衰减，所以回升值略小于接入压降（本阶段一阶 59.990 mV、二阶 59.972 mV，差值是 0.1 s 采样期间极化衰减造成的）。

## 5. 适用条件

- 阶跃必须发生在采样点上；采样间隔远小于时间常数。
- 恢复判据依赖观察窗与容差，必须同时报告，不能只报“已恢复”。
- 仅适用于模型波形；真实硬件还需考虑采样率、量程与噪声。

## 6. 实际代码与核心函数

| 功能 | 路径 | 函数 |
| --- | --- | --- |
| 脉冲指标 | `analysis/pulse_response.py` | `analyze_pulse` |
| 运行封装 | `simulations/ecm_runner.py` | `analyze_run_pulse` |
| 三模型对照 | `scripts/battery_pulse_demo.py` | `main` |

## 7. 关键代码逐行解释

```python
pre_step_voltage = _window_mean(frame, step_time_s - baseline_window_s, step_time_s, "terminal_voltage_v")
step_index = int(np.searchsorted(times, step_time_s - 1e-12, side="left"))
current_before = float(currents[max(step_index - 1, 0)])
current_after = float(currents[step_index])
instantaneous_drop = pre_step_voltage - float(voltages[step_index])
r0_estimate = instantaneous_drop / delta_current
```

- 用左闭右开搜索定位阶跃后的第一个采样点。
- 阶跃前电流取前一个采样点。
- `r0_estimate` 使用压降除以电流增量，充电方向自动得到正值。

恢复搜索：

```python
within = np.abs(window_voltages - reference) <= tolerance_v
last_failure = None
for index, flag in enumerate(within):
    if not flag:
        last_failure = index
start_index = 0 if last_failure is None else last_failure + 1
```

找到最后一次越界之后的位置，若剩余时长满足保持时间，则判定恢复。

## 8. 实际运行命令

```powershell
conda run -n kaifa_battery python -m scripts.battery_pulse_demo
conda run -n kaifa_battery python -m scripts.first_order_rc_demo
conda run -n kaifa_battery python -m scripts.second_order_rc_demo
```

## 9. 真实结果

运行编号：`ecm_20261126_122858_dadfee`（三模型统一对照）。

| 指标 | Rint | 一阶 RC | 二阶 RC |
| --- | --- | --- | --- |
| 接入前电压 (V) | 3.800000 | 3.800000 | 3.800000 |
| 接入后瞬时电压 (V) | 3.740000 | 3.740000 | 3.740000 |
| 瞬时压降 (mV) | 60.000 | 60.000 | 60.000 |
| R0 反算 (Ω) | 0.030000 | 0.030000 | 0.030000 |
| 脉冲结束电压 (V) | 3.740000 | 3.702001 | 3.683056 |
| 释放后首个电压 (V) | 3.800000 | 3.761991 | 3.743028 |
| 恢复跳变 (mV) | 60.000 | 59.990 | 59.972 |
| 最大压降 (mV) | 60.000 | 97.999 | 116.944 |
| 恢复时间 (s) | 0.0 | 72.8 | 未恢复 |
| 恢复状态 | RECOVERED | RECOVERED | NOT_RECOVERED |

原始证据：

- `results/ecm/run_ecm_20261126_122858_dadfee/pulse_response_metrics.json`
- `results/ecm/run_ecm_20261126_122858_dadfee/summary.json`
- 各模型波形：`results/ecm/run_ecm_20261126_122856_9e8ca2/waveform.csv`（Rint）、`..._122856_492c95`（一阶）、`..._122857_cdbae7`（二阶）

## 10. 常见错误

- 用 0.1 s 采样点直接当“60.000 s 时刻”，造成 10 µV 级比较误差。
- 恢复判据只给“恢复/未恢复”而不给容差、保持时间与观察窗。
- 把 R0 反算值的小数位当成真实测量精度；本阶段是模型数值结果。
- 二阶模型未恢复就修改阈值直到通过。

## 11. 独立练习

1. 将采样步长改为 0.01 s，重新计算 60 s 端电压并解释差异。
2. 设计 0.5 A→2 A 两步脉冲，观察 R0 反算是否一致。
3. 将恢复容差改为 5 mV，比较恢复时间。

## 12. 面试题

1. 如何从脉冲响应中区分欧姆内阻与极化电阻？
2. 采样率不足会如何影响 R0 估计？
3. 为什么释放瞬间的回升值不等于接入压降？
4. 恢复时间应如何定义才具备工程可比性？
