# 04 直流工作点与直流扫描分析

> 本文所有仿真值来自本机 ngspice-34 真实求解（`data_source = spice_simulation`），
> 理论值单独标记为 `analytical_theory`。运行日期：2026-11-25。

## 1. 分析目标

- 工作点分析（`.op`）：把电容视为开路、电感视为短路，求直流稳态节点电压与源支路电流。
- 直流扫描（`.dc`）：让独立电压源从 0 V 扫到 12 V，验证分压传递关系的线性度。

## 2. 理论公式

欧姆定律与串联分压：

\[
I = \frac{V_{in}}{R_1 + R_2}, \qquad
V_{out} = V_{in}\frac{R_2}{R_1 + R_2}
\]

传递斜率：

\[
\frac{dV_{out}}{dV_{in}} = \frac{R_2}{R_1 + R_2} = \frac{1000}{2000} = 0.5
\]

代入 \(V_{in}=12\text{ V}\)：\(V_{out}=6\text{ V}\)，\(I=6\text{ mA}\)。

## 3. 真实网表

工作点（`results/basic_circuits/run_20261125_111917_82b8808a/circuit.cir`）：

```spice
.title Voltage Divider
Vinput vin 0 12.0V
R1 vin out 1000.0Ohm
R2 out 0 1000.0Ohm
.options TEMP = 25.0C
.options TNOM = 25.0C
.op
.end
```

直流扫描（`run_20261125_111917_7619098e/circuit.cir`）仅最后一条分析指令不同：

```spice
.dc Vinput 0.0 12.0 0.5
```

注意：PySpice 的 DC 扫描参数键必须写成 `Vinput`（源名首字母大写并带 `V` 前缀），
直接写 `input` 会被 ngspice 拒绝；本项目由 `simulations/backend.py` 的
`dc_source_key()` 统一转换。

## 4. 代码路径

| 层 | 文件 | 作用 |
| --- | --- | --- |
| 电路 | `circuits/voltage_divider.py` | 复用第一阶段分压器，补充 `divider_transfer_slope` |
| 执行 | `simulations/runner.py` | `run_operating_point` / `run_dc`，质量检查与元数据 |
| 提取 | `simulations/waveform_extractor.py` | 节点、支路、扫描轴提取 |
| 误差 | `analysis/error_metrics.py` | MAE / RMSE / 最大绝对误差 |
| 脚本 | `scripts/dc_analysis_demo.py` | 两次真实运行并保存结果 |

## 5. 真实结果

工作点：

| 量 | 仿真值 | 理论值 | 绝对误差 |
| --- | --- | --- | --- |
| `out` 节点电压 | 6.000000 V | 6.000000 V | 0 V |
| 供电电流（显式取反） | 0.006000 A | 0.006000 A | 0 A |
| KCL 残差 | 0 A | 0 A | — |
| KVL 残差 | 0 V | 0 V | — |

直流扫描（25 点，0–12 V，步长 0.5 V）：

| 指标 | 实际值 |
| --- | --- |
| 拟合斜率 \(\Delta V_{out}/\Delta V_{in}\) | 0.5 |
| 最大绝对误差 | \(8.88\times10^{-16}\) V |
| MAE | \(7.11\times10^{-17}\) V |
| RMSE | \(2.18\times10^{-16}\) V |
| KCL 最大残差 | \(1.73\times10^{-18}\) A |
| KVL 最大残差 | \(8.88\times10^{-16}\) V |

这些残差处于双精度浮点噪声量级，说明求解器收敛到线性方程组的机器精度解。

## 6. 理论与仿真对比及误差来源

- 分压器是纯线性电阻网络，SPICE 直接求解线性方程组，因此误差只剩浮点舍入。
- 理论没有考虑导线电阻、寄生参数与源内阻；本实验网表同样没有这些元素，二者模型一致。
- 判断仿真正确性不能只看“看起来接近”，还应检查 KCL/KVL 残差与拟合斜率。
- 当输入为 0 V 时理论输出也为 0 V，相对误差不可定义；本模块的
  `zero_reference_count` 明确统计此类点（本实验 25 点中有 1 个），不会伪造 0 误差。

## 7. 面试题（5 道）

1. 工作点分析为什么把电容当开路、电感当短路？
   答：直流稳态下电容电流 \(C\,dV/dt=0\)，电感电压 \(L\,di/dt=0\)。
2. 为什么 DC 扫描的源名要写成 `Vinput` 而不是 `input`？
   答：ngspice 的 `.dc` 语法要求扫描对象是器件名（电压源为 `V...`），
   PySpice 只是传递字符串，不会自动补前缀。
3. KCL 残差 \(10^{-18}\) A 是否说明仿真“完全正确”？
   答：只说明线性方程组在同一模型内被高精度求解；模型本身仍可能缺少寄生参数。
4. 为什么相对误差在 0 V 点不可定义？
   答：分母为 0；应改用绝对误差或单独统计零参考点。
5. 分压器适合用来验证求解器吗？
   答：适合验证线性求解、单位与网表生成；不适合验证非线性、动态与收敛鲁棒性。

## 8. 复现命令

```powershell
conda run -n kaifa_power python -m scripts.dc_analysis_demo
conda run -n kaifa_power python -m pytest tests/test_runner.py tests/test_error_metrics.py -v
```
