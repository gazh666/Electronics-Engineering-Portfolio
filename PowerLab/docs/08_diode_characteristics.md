# 08 二极管伏安特性（Shockley 模型）

> 真实数据来自 `.dc` 扫描（181 点，-1.0 V–0.8 V，步长 0.01 V）。
> 理论曲线由 Shockley 方程计算，标记为 `analytical_theory`。

## 1. 分析目标

- 测量真实二极管模型的整流特性：反偏漏电、正偏指数上升、导通电压。
- 对比“理想 Shockley（无串联电阻）”与“含 \(R_S\) 的 SPICE 模型”，说明差异来源。
- 提取 1 mA / 10 mA 对应的正向压降。

## 2. 理论公式

Shockley 方程：

\[
I_D=I_S\left[\exp\left(\frac{V_D}{N V_T}\right)-1\right], \qquad
V_T=\frac{kT}{q}
\]

在 \(T=25^\circ\text{C}\) 时：

\[
V_T=\frac{1.380649\times10^{-23}\times298.15}{1.602177\times10^{-19}}
=25.6926\text{ mV}
\]

SPICE 模型参数：\(I_S=1\times10^{-9}\text{ A}\)、\(N=1.8\)、\(R_S=0.5\ \Omega\)。
含串联电阻时，外部端电压 \(V=V_D+I_D R_S\)，因此同样端电压下真实电流小于理想值：

\[
I_D=I_S\left[\exp\left(\frac{V-I_D R_S}{N V_T}\right)-1\right]
\]

## 3. 真实网表

`results/basic_circuits/run_20261125_111922_6b587bf2/circuit.cir`：

```spice
.title Diode IV Curve
Vbias anode 0 0.0
D1 anode 0 DTEST
.model DTEST D (IS=1e-09 N=1.8 RS=0.5)
.options TEMP = 25.0C
.options TNOM = 25.0C
.dc Vbias -1.0 0.8 0.01
.end
```

二极管电流由源支路电流取反得到：`-i(Vbias)`，不能用 `abs()` 掩盖方向。

## 4. 代码路径

| 层 | 文件 | 作用 |
| --- | --- | --- |
| 电路 | `circuits/diode_circuit.py` | `add_diode_model`、`build_diode_iv_circuit` |
| 参数 | `circuits/models.py` | `DiodeParameters` 校验 IS/N/RS/温度 |
| 执行 | `simulations/runner.py` | `run_dc`，扫描键 `Vbias` |
| 理论 | `analysis/theory.py` | `diode_thermal_voltage`、`diode_ideal_current` |
| 误差 | `analysis/error_metrics.py` | 与理想 Shockley 的 MAE/RMSE |
| 脚本 | `scripts/diode_iv_demo.py` | 真实扫描、工作点提取、保存 |

## 5. 真实结果

| 指标 | 仿真值 | 理论值 | 差异 |
| --- | --- | --- | --- |
| 热电压 \(V_T\) | — | 25.6926 mV | — |
| -1 V 反偏电流 | -1.000867 nA | \(-I_S\) | 约 +0.087% |
| 0.8 V 正偏电流 | 24.8795 mA | 32.5586 mA（无 \(R_S\)） | 理想值高 30.87% |
| 1 mA 对应电压 | 0.639361 V | 0.638814 V | +0.547 mV |
| 10 mA 对应电压 | 0.750375 V | 0.745139 V | +5.236 mV |
| 全扫描最大绝对差 | — | — | 7.679 mA |
| MAE | 0.133205 mA | — | — |
| RMSE | 0.785214 mA | — | — |

反偏电流的量级由 \(I_S\) 决定（约 -1 nA），而不是理想开关的“绝对 0”。
正偏时电流单调上升；0.8 V 时已明显进入大电流区。

## 6. 理论与仿真对比及误差来源

1. **串联电阻 \(R_S\)**：大电流时 \(I R_S\) 压降不可忽略，端电压 0.8 V 下理想公式高估约 31%。
   这是本实验最主要的“理论 vs 仿真”差异来源。
2. **理想因子 \(N=1.8\)**：非 1，说明模型不是理想肖克利二极管；理论使用同一 \(N\) 仍无法消除 \(R_S\) 影响。
3. **温度**：\(V_T\) 随温度线性变化；本实验固定在 25 °C。温度漂移约 -2 mV/°C（工程经验值）。
4. **模型性质**：参数为教学用，不是某个真实商用器件的实测拟合；不能据此声称“测量了真实硬件”。
5. **扫描步长**：0.01 V 步长在 0.6 V 附近电流变化数个数量级，峰值误差对步长敏感；
   工作点电压用线性插值提取，存在半个步长的量化误差。

## 7. 面试题（5 道）

1. 二极管反偏时电流为什么不是严格 0？
   答：Shockley 方程给出 \(-I_S\) 的漏电流；SPICE 模型也保留该反向饱和电流。
2. 为什么理想 Shockley 公式在 0.8 V 时明显高估电流？
   答：忽略了串联电阻与接触电阻；实际 \(V_D=V-I R_S\) 小于端电压。
3. 热电压 \(V_T\) 的物理意义是什么？
   答：\(kT/q\)，描述温度对指数特性的影响；室温约 25.7 mV。
4. 如何从 IV 曲线提取导通电压？
   答：给定电流阈值（如 1 mA/10 mA），在单调曲线上插值对应电压，而不是目测拐点。
5. 这个模型能直接用于电源设计吗？
   答：不能直接用于定量设计；需要器件厂商提供的实测模型或数据手册曲线。

## 8. 复现命令

```powershell
conda run -n kaifa_power python -m scripts.diode_iv_demo
conda run -n kaifa_power python -m pytest tests/test_diode_circuit.py -v
```
