# 27 温度特性分析（真实数据缺失时如实标记）

## 1. 专业原理

温度同时影响可用容量、内阻与极化时间常数。工程上常用 Arrhenius 型关系近似：

```text
R(T) = R_ref · exp[ Ea/R_g · (1/T − 1/T_ref) ]
```

温度降低 → 电解液黏度上升、电荷转移变慢 → 内阻增大、可用容量下降。

## 2. 公式推导

跨温度预测（实验 A）：直接用 25 ℃ 冻结参数预测 0/45 ℃ 实验，误差变化即温度失配代价。
分温度辨识（实验 B）：每个温度独立完成容量、OCV 与 ECM 辨识，记录

```text
Q(T), R0(T), R1(T), τ1(T), C1(T), R2(T), τ2(T), C2(T)
```

若不同温度来自不同电芯或协议不同，参数差异不能全部归因于温度。

## 3. 参数物理意义与单位

| 量 | 含义 | 单位 |
| --- | --- | --- |
| `T` | 环境温度 | ℃（绝对温度 K 用于 Arrhenius） |
| `Ea` | 活化能 | J/mol |
| `R_g` | 气体常数 8.314 | J/(mol·K) |
| `Q(T)` | 可用容量 | Ah |
| `R0(T)` | 内阻 | Ω |

## 4. 实际文件路径

- `validation/temperature_validation.py`
- `scripts/temperature_analysis_demo.py`
- `results/temperature/run_temperature_20261126_125907_51b9d9/temperature_report.json`

## 5. 实际类与函数

| 名称 | 作用 |
| --- | --- |
| `cross_temperature_validation(...)` | 实验 A：跨温度预测 |
| `per_temperature_identification(...)` | 实验 B：分温度辨识 |
| `temperature_parameter_table(...)` | 温度-参数表 |
| `temperature_analysis_status(...)` | 汇总可用/缺失温度与状态 |

## 6. 关键源码逐行解释

```python
available = sorted(frame["temperature_c"].unique())
missing = [value for value in (0, 25, 45) if value not in available]
if missing and any(value != 25 for value in missing):
    return {"status": "NOT_VERIFIED", "reason": "缺少目标温度的真实公开实验数据"}
```

- 第 1 行统计真实存在的温度；
- 第 2 行列出缺失目标温度；
- 第 3–4 行：只要缺非参考温度就不做温度结论，明确 `NOT_VERIFIED`，不构造替代数据。

## 7. 运行命令

```powershell
conda run -n kaifa_battery python -m scripts.temperature_analysis_demo
```

## 8. 实际结果

| 项目 | 结果 |
| --- | --- |
| 可用温度 | 仅 25 ℃ |
| 缺失温度 | 0 ℃、45 ℃ |
| 实验 A 跨温度验证 | `NOT_VERIFIED` |
| 实验 B 分温度辨识 | `NOT_VERIFIED` |
| 25 ℃ 参数表 | Q=2.028083 Ah、R0=75.86 mΩ、R1=18.25 mΩ、τ1=11.64 s、R2=7.38 mΩ、τ2=100.0 s |

温度特性缺失**不阻断** 25 ℃ 主流程；所有温度相关结论都保留 `NOT_VERIFIED`。

## 9. 已知局限

1. 没有 0/45 ℃ 真实文件，无法给出任何温度系数；
2. 即使后续补齐数据，若来自不同电芯，也不能把差异全部归因于温度；
3. 未开发电化学热模型，不宣称电芯内部温度。

## 10. 独立学习练习

1. 用 Arrhenius 公式反推：若 R0 在 0 ℃ 增大 2 倍，`Ea` 约为多少？
2. 设计一个最小实验矩阵，用 3 个温度完成参数标定；
3. 说明为什么不能用 25 ℃ 参数外推 45 ℃ 的保护阈值。

## 11. 相关面试题

1. 低温下 BMS 为什么要降额充电？
2. 温度对 OCV-SOC 曲线的影响主要体现在哪些区间？
3. 跨温度验证与分温度辨识的区别与各自局限？
