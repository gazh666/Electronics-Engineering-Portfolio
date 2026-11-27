# 55 CC-CV 控制理论与数值可靠性

## 1. 控制结构

```text
Vpack ──► e_v = Vset − Vpack ──► 电压 PI ──► Iref = clamp(0, Isoft) ──┐
                                                                     ▼
IL ──────────────────────────────► e_i = Iref − IL ──► 电流 PI ──► D ──► PWM
                                          ▲
                          D_ff = (Vout,filt + Vd) / (Vin + Vd)
```

- 电压环输出是电流指令，恒流段由 `Isoft`（软启动或恒流限值）限幅；
- 电流环输出是占空比，带滤波前馈；
- 两个环都使用同一套 PI 实现：`charging/pi_controller.py`（Python）与
  `circuits/charger_spice_controller.py`（网表行为源），参数完全一致。

## 2. PI 与抗饱和

离散实现：

```text
u_raw = feedforward + Kp·e + x
u     = clamp(u_raw, lower, upper)
冻结条件：饱和方向与误差方向相同
dx/dt = 0                                    （冻结）
dx/dt = Ki·e + Kaw·(u − u_raw)               （未冻结，含反计算）
```

为什么必须"冻结 + 反计算"而不是只用反计算：

- 恒流段电压环长期饱和，误差为负（电池电压低于目标）；
- 纯反计算会产生稳定修正量 `Kaw·(u−u_raw)`，把积分拉到 `(Ki/Kaw)·e`；
- 实测 C01 的电流指令被拉低约 25 mA（1 A 的 2.5%），且不随时间消失；
- 冻结判据在"继续积分只会加深饱和"时切断积分输入，误差反向时仍保留反计算，
  既能退出饱和，又不会在饱和平台产生稳态偏差。

冻结判据实现见 `charging/anti_windup.py::is_frozen`，测试见
`tests/test_stage6_pi_antiwindup.py`（7 项）。

## 3. 软启动与前馈

- 软启动：`Isoft = min(t/TSOFT, 1) · Icc`。TSOFT 取 1 ms。
  - 原设计 5 ms 会让 CC 指标落在 8–12 ms 窗口的瞬态上，且 4 ms 的输入/指令
    阶跃发生在软启动未完成时（C08 的 0.5→1.0 A 阶跃会失真）。
  - 这是**实验设计修正**，发生在最终验收之前；13 项预登记限值未改。
- 前馈：`D_ff = (Vout,filt + Vd)/(Vin + Vd)`，其中 `Vout,filt` 经 1 ms RC 滤波。
  - 必须用滤波后的输出电压；
  - 前馈**不乘软启动**（软启动只限制电流指令）。

## 4. 两条必须写进结论的数值经验

### 4.1 PWM 闭环时间步 ≤ 20 ns

| 步长 | 现象 |
| --- | --- |
| 10 ns | ngspice `timestep too small`，无法完成 8 ms 求解 |
| 20 ns | 正常；C01–C03 与全部瞬态工况可复现 |
| 50 ns | PWM 边沿量化产生 0.1–0.4 A 伪极限环，看似"控制失稳" |

因此在 `circuits/charger_spice_controller.py` 中定义
`MINIMUM_RELIABLE_STEP_S = 2e-8`，`run_cascade_buck` 在步长大于该值时直接抛错，
不允许"先跑出来再解释"。验证脚本的 12 个开关级工况全部使用 20 ns。

### 4.2 前馈必须滤波且不乘软启动

- 用瞬时 `V(out)` 做前馈会形成 `D=(Vout+Vd)/Vin` 的代数正反馈：输出一升高，
  占空比立刻升高，环路等效增益变大，轻载时出现持续振荡。
- 前馈乘软启动会在软启动结束瞬间把占空比从 0 跳到稳态值，DCM 下电感电流
  追赶造成大过冲。
- 现在网表中为 `RFF out ff_in 1e3` + `CFF ff_in 0 1u`（τ=1 ms），且软启动只作用于
  `Iref`。C01–C03 的电压过冲分别为 0 / 0 / 2.07 mV。

### 4.3 抗饱和：条件积分冻结 + 反计算

见第 2 节。C01 恒流稳态误差 1.09 mA，若用纯反计算会变成约 25 mA 的单向偏差。

## 5. 平均模型

`simulations/averaged_charger.py` 用同一组增益、同一软启动与抗饱和，状态方程为：

```text
diL/dt = [D·(Vin − Ron·iL) − (1−D)·Vd − vout − DCR·iL] / L
dvC/dt = (iL − ibat) / C
vout   = vC + ESR·(iL − ibat)
ibat   = (vC + ESR·iL − OCV_pack − Vp) / (R0_pack + Rpath + ESR)
dSOC/dt = ibat / (3600·Q)
dVp/dt  = −Vp/τ + ibat·R1_pack/τ,  τ = R1·C1
```

平均模型用途与限制：

| 用途 | 允许 | 不允许 |
| --- | --- | --- |
| PI 整定趋势 | 是 | 宣称开关纹波达标 |
| 长时间趋势预演 | 是 | 替代开关级 DCM/限流验证 |
| 与开关级同向对照 | 是 | 逐点重合比较 |

C01 对照：开关级末电流 0.978 A（最后一点）、周期平均 1.001 A；平均模型末电流
0.999 A。两者相差 < 25 mA，说明控制律一致；差异来自开关纹波与夹具差异。

## 6. 电流环被控对象必须用电池内阻

线性化时若把负载当成 `Vout/Iout = 12.15 Ω`，电流环穿越频率会被低估到 12 Hz；
真实充电负载是刚性电池，等效负载应为 `R0_pack + Rpath ≈ 0.26 Ω`，此时穿越
频率 728 Hz。两种取法的差异约 40 倍，属于建模错误而不是调参差异。
`scripts/stage6_loop_analysis_demo.py` 与 `docs/58` 使用后者。
