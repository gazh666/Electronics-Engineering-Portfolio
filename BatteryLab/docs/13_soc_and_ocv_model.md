# 13 SOC 与 OCV 模型

## 1. 模型结构

- SOC：安时积分（库仑计数）。
- OCV：固定 3.8 V 基准，或教学 SOC-OCV 分段线性查表。
- 本阶段不做 OCV-SOC 真实曲线提取与参数辨识，这些属于第三阶段。

## 2. 专业公式

SOC 更新（放电为正）：

```text
SOCnext = SOC - I·dt / (3600·Qnom)          # 放电
SOCnext = SOC + |I|·dt·η/Qnom/3600          # 充电（等价形式）
```

教学 OCV 查表：

| SOC | 0.0 | 0.1 | 0.2 | 0.4 | 0.6 | 0.8 | 1.0 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| OCV (V) | 3.00 | 3.35 | 3.50 | 3.70 | 3.80 | 3.98 | 4.20 |

区间内使用线性插值 `OCV = OCVk + (OCVk+1-OCVk)·(SOC-SOCk)/(SOCk+1-SOCk)`。

## 3. 变量与单位

| 符号 | 含义 | 单位 |
| --- | --- | --- |
| Qnom | 额定容量 | Ah |
| I | 电流 | A |
| dt | 时间步长 | s |
| SOC | 荷电状态 | 0–1 |
| η | 库仑效率 | – |

## 4. 公式推导

电荷守恒：`dQ/dt = -I`，容量归一化得到 `dSOC/dt = -I/(3600·Qnom)`。在零阶保持电流下积分得精确离散式。OCV 查表采用分段线性插值，避免高阶插值在少量节点间的振荡。

## 5. 适用条件

- 库仑计数需要准确初始 SOC 与容量；误差会累积。
- 教学 OCV 曲线不是 CALCE 实测 OCV，不能用于精度声明。
- 查表覆盖 [0,1]，代码禁止越界外推。

## 6. 实际代码与核心函数

| 功能 | 路径 | 函数/类 |
| --- | --- | --- |
| SOC 更新 | `battery_models/states.py` | `update_soc` |
| 固定 OCV | `battery_models/ocv_model.py` | `ConstantOcvModel` |
| 查表 OCV | `battery_models/ocv_model.py` | `TableOcvModel`、`interpolate_ocv` |
| 配置加载 | `battery_models/ocv_model.py` | `load_ocv_reference` |
| 阶段一 SOC 派生 | `analysis/battery_metrics.py` | `derive_soc_from_current` |

## 7. 关键代码逐行解释

```python
if current >= 0.0:
    effective_current = current / eta_discharge   # 放电有效电流
else:
    effective_current = current * eta_charge      # 充电有效电流
return soc - effective_current * dt / (SECONDS_PER_HOUR * capacity)
```

`TableOcvModel.voltage`：

```python
if not 0.0 <= soc_value <= 1.0:
    raise OcvError("SOC 超出 0 至 1 范围")   # 明确拒绝外推
return float(np.interp(soc_value, soc_table, ocv_table))
```

## 8. 实际运行命令

```powershell
conda run -n kaifa_battery python -m scripts.second_order_rc_demo
conda run -n kaifa_battery python -m scripts.model_comparison_demo
```

## 9. 真实结果

- 2 A 放电 60 s（Q=2 Ah）：SOC 从 0.600000 降至 0.583333；程序值与 `0.6 - 2×60/3600/2` 的误差为 **3.33e-13**（阈值 1e-8）。
- 容量吞吐：`∫I dt = 2×60/3600 = 0.033333 Ah`。
- 6 个动态工况（含充电脉冲与方向切换）SOC 路径均与解析积分一致（见 `results/stage2/run_stage2_20261126_123044_d2d0af/summary.json`）。
- CALCE DST 电流重放（150 s 片段，151 点，教学初始 SOC=0.6、未辨识参数）：二阶 RC 对实测电压 MAE=0.3331 V、RMSE=0.3333 V、最大误差 0.3649 V，状态标记 `UNCALIBRATED_BASELINE`。

原始证据：

- `results/ecm/run_ecm_20261126_122857_cdbae7/waveform.csv`
- `results/stage2/run_stage2_20261126_123044_d2d0af/calce_replay_comparison.csv`
- `results/calce/run_calce_20261126_120012_8cefbd/processed/calce_inr18650_20r_sp2_25c_dst.csv.gz`

## 10. 为什么理论误差小不代表真实电池拟合误差小

理论误差只验证“代码是否解对了自己设定的方程”，而真实拟合误差取决于：

1. 参数是否由真实电芯实验辨识；
2. 模型结构是否覆盖真实极化过程；
3. 温度、老化、滞回是否建模；
4. 初始 SOC 与容量是否准确。

本阶段 CALCE 重放误差约 0.33 V，远大于理论误差 4.4e-16 V，正好说明二者不是同一件事。

## 11. 常见错误

- 用理论误差宣传电芯模型精度。
- 直接对 SOC<0 或 >1 查表并静默截断。
- 忽略充电效率导致长时间积分偏差。
- 把教学 OCV 曲线写成 CALCE 实测曲线。

## 12. 独立练习

1. 用 1 A 充电 600 s，计算 SOC 变化。
2. 将 OCV 表在 SOC=0.3 处插值，手算并与程序对比。
3. 说明为什么初始 SOC 误差 5% 会导致长时间电压预测偏差。

## 13. 面试题

1. 库仑计数的主要误差来源是什么？
2. 如何用 OCV 静置法修正 SOC？
3. 为什么 OCV-SOC 曲线存在滞回？
4. 参数辨识与模型验证为什么要使用不同数据集？
