# 06 瞬态分析：RC 充放电与 RL 阶跃

> 所有时间序列来自 `.tran` 真实自适应步长解；理论为 `analytical_theory`。
> 瞬态采样点非均匀，误差统计同时给出按点平均与按时间加权两种口径。

## 1. 分析目标

- RC：同一网表内完成充电（0–6 ms）与放电（6–12 ms），验证 \(\tau=RC\)。
- RL：验证电感电流不能突变、时间常数 \(\tau=L/R\) 与稳态电流 \(V/R\)。
- 明确支路电流方向：SPICE 的 `i(Vsource)` 以流入源内部为正，供电电流需显式取反。

## 2. 理论公式

RC 充电与放电（放电初值取实际放电时刻电压 \(V_0\)）：

\[
v_C(t)=V_{in}\left(1-e^{-t/\tau}\right), \qquad
v_C(t)=V_0\,e^{-(t-t_0)/\tau}, \qquad \tau=RC=1\text{ ms}
\]

RL 阶跃电流：

\[
i_L(t)=\frac{V_{in}}{R}\left(1-e^{-t/\tau}\right), \qquad
\tau=\frac{L}{R}=1\text{ ms}, \qquad i(\infty)=0.5\text{ A}
\]

电感储能：

\[
E_L=\frac12 L i^2 = \frac12 \times 0.01 \times 0.5^2 = 1.25\text{ mJ}
\]

## 3. 真实网表

RC（`run_20261125_111917_127bf325/circuit.cir`）：

```spice
.title RC Transient
Vinput vin 0 DC 0V PULSE(0V 5.0V 0s 1e-06s 1e-06s 0.006s 0.012s)
R1 vin out 1000.0
C1 out 0 1e-06
.options TEMP = 25.0C
.options TNOM = 25.0C
.tran 1e-05s 0.012s 0.0s
.end
```

RL（`run_20261125_111918_8eb03f0d/circuit.cir`）：

```spice
.title RL Transient
Vinput vin 0 DC 0V PULSE(0V 5.0V 0s 1e-06s 1e-06s 0.02s 0.04s)
R1 vin inductor_node 10.0
L1 inductor_node 0 0.01
.options TEMP = 25.0C
.options TNOM = 25.0C
.tran 1e-05s 0.006s 0.0s
.end
```

## 4. 代码路径

| 层 | 文件 | 作用 |
| --- | --- | --- |
| 电路 | `circuits/rc_circuit.py` / `circuits/rl_circuit.py` | 脉冲源与 RC/RL 拓扑，校验脉宽小于周期 |
| 执行 | `simulations/runner.py` | `run_transient`，记录 `nonuniform_sampling` |
| 提取 | `simulations/waveform_extractor.py` | 时间轴、节点电压、电感支路电流 |
| 误差 | `analysis/error_metrics.py` | 时间加权 MAE/RMSE、\(\tau\) 附近窗口误差 |
| 理论 | `analysis/theory.py` | `rc_charging_voltage`、`rl_step_current`、储能 |
| 脚本 | `scripts/rc_transient_demo.py` / `scripts/rl_transient_demo.py` | 真实运行、理论对照、保存 |

## 5. 真实结果

RC 充放电（1229 点，12 ms）：

| 时刻 | 仿真 | 理论 | 绝对误差 |
| --- | --- | --- | --- |
| 1τ 充电 | 3.159684 V | 3.160603 V | -0.000919 V |
| 2τ 充电 | 4.322991 V | 4.323324 V | -0.000332 V |
| 3τ 充电 | 4.750944 V | 4.751065 V | -0.000120 V |
| 放电起点 | 4.986372 V | — | — |
| 放电 1τ | 1.834455 V | 1.834384 V | +0.0000717 V |
| 放电 2τ | 0.674853 V | 0.674832 V | +0.0000207 V |

整体 MAE 0.000220 V，时间加权 RMSE 0.000508 V，最大绝对误差 0.002498 V，
末值 0.012381 V。

RL 阶跃（619 点，6 ms）：

| 指标 | 仿真 | 理论 | 误差 |
| --- | --- | --- | --- |
| 1τ 电流 | 0.315968 A | 0.316060 A | -0.0919 mA |
| 末值电流 | 0.498760 A | 0.500000 A | -1.240 mA |
| 电感储能（末值） | 1.243808 mJ | 1.250000 mJ | -6.192 µJ |
| MAE | 0.0000432 A | — | — |
| 时间加权 RMSE | 0.0000716 A | — | — |
| 最大绝对误差 | 0.000250 A | — | — |

供电支路原始电流首个采样点为 -0.0 A，取反后为 +0.0 A；全时段为正值，
说明电流方向判断正确。6 ms 内脉冲仍为高电平（脉宽 20 ms），因此没有下降沿。

## 6. 理论与仿真对比及误差来源

1. **源上升时间**：脉冲源设置 1 µs 上升时间，而理论假设理想阶跃；起始 1 µs 内必然有偏差，
   这是物理模型差异，不是求解错误。
2. **自适应步长**：ngspice 在电压变化剧烈处自动缩小步长，采样点非均匀；
   按点平均会高估陡变段权重，因此必须使用时间加权指标。
3. **放电初值**：理论放电曲线使用实际 \(t_0\) 时刻仿真电压 4.986372 V，
   而不是假设“已充满到 5 V”，避免把充电未完成误算成放电误差。
4. **末值未完全稳态**：6 ms 仅为 6τ，\(e^{-6}=0.00248\)，理论末值应为 0.49876 A；
   仿真 0.498760 A 与之一致，而不是与 0.5 A 强行对齐。
5. **数值积分**：ngspice 默认梯形法/ Gear 法存在截断误差，量级在 \(10^{-4}\)。

## 7. 面试题（5 道）

1. 为什么 RC 放电理论初值要用仿真值而不是 5 V？
   答：放电开始时电容未必已充满；用实际初值才能把“充电未完成”和“放电模型误差”分开。
2. 瞬态误差为什么不能直接按采样点平均？
   答：自适应步长导致采样密度随时间变化，按点平均会改变各时间段的权重；应按时间加权。
3. 电感电流为什么不能突变？
   答：\(v_L=L\,di/dt\)，电流突变需要无穷大电压；真实电路通过续流路径维持连续。
4. `i(Vsource)` 为负说明什么？
   答：SPICE 约定电流流入源内部为正；给负载供电时源支路电流为负，负载电流应取反。
5. 6 ms 时 RL 电流为何不是 0.5 A？
   答：6τ 只衰减到 \(e^{-6}\approx0.25\%\) 的误差，理论值为 0.49876 A；强行要求 0.5 A 才是错的。

## 8. 复现命令

```powershell
conda run -n kaifa_power python -m scripts.rc_transient_demo
conda run -n kaifa_power python -m scripts.rl_transient_demo
conda run -n kaifa_power python -m pytest tests/test_rc_transient.py tests/test_rl_circuit.py -v
```
