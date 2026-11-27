# 50 第七阶段验收报告：Buck 闭环、瞬态与软启动

> 本文件只记录真实运行结果。所有数值都能在 `results/stage7/` 下的 JSON/CSV 与
> 对应 `run_*` 目录（含 `circuit.cir`、`metadata.json`、`waveform.csv`）中追溯。
> 未通过项、未解析项和缺失的前置阶段都按原样保留，不做“通过率”包装。

## 1. 验收结论

| 项目 | 实际值 | 来源 |
| --- | --- | --- |
| 验收检查总数 | 31 | `results/stage7/stage7_acceptance_checks.csv` |
| PASS | 22 | 同上 |
| FAIL | 8 | 同上 |
| NOT_RESOLVED | 1（相位裕度可算、增益裕度不可用） | 同上 |
| 总体状态 | `PARTIAL_FAILURE` | `results/stage7/stage7_acceptance.json` |
| SPICE 运行次数 | 28 | 同上 `budget.spice_runs` |
| 平均模型运行次数 | 11 | 同上 `budget.averaged_runs` |
| 验收总耗时 | 397.9 s（standard profile，随机器负载波动） | 同上 `budget.wall_clock_s` |

结论：闭环在额定工况下能稳定调节（E 稳态 4.99842 V，SW 稳态 5.00043 V），
但**负载阶跃超调超过 0.30 V 限值**（最差 0.84122 V），**开环 E 变体在 12 V
输入下稳态偏差 50.65 mV 超过 ±50 mV 限值**，**无软启动启动超调 61.72%**。
这 8 个 FAIL 是真实结果，未通过放宽限值或事后修波形来消除。

## 2. 交付文件

### 2.1 新增模块

| 文件 | 关键类/函数 |
| --- | --- |
| `control/averaged_buck.py` | `AveragedBuckParameters`、`operating_point`、`linearize`、`buck_derivatives`、`nonideal_derivatives` |
| `control/transfer_functions.py` | `TransferFunction`、`from_state_space`、`nonideal_buck_control_to_output`、`natural_frequency_hz`、`esr_zero_hz` |
| `control/pi_controller.py` | `PIController`（`update`、`reset`） |
| `control/anti_windup.py` | `clamp_duty`、`back_calculation_correction`、`conditional_integral_weight`、`integral_increment` |
| `control/pwm_modulator.py` | `sine_carrier`、`effective_duty_sine`、`sine_carrier_gain`、`analyze_pwm_pulses`、`PWMPulseStatistics` |
| `control/soft_start.py` | `soft_start_reference`、`soft_start_points`、`ramp_rate_v_per_s` |
| `control/loop_analysis.py` | `loop_gain`、`analyze_loop`、`closed_loop_poles`、`classify_poles`、`summarize_loop` |
| `control/controller_tuning.py` | `design_pi`、`evaluate_candidate`、`tuning_matrix`、`select_candidates` |
| `control/spice_controller.py` | `SpiceControllerLayout`、`add_behavioral_pi_controller` |
| `control/models.py` | `ControllerConfig`、`SoftStartConfig`、`CarrierConfig`、`ControlSample` |
| `circuits/closed_loop_config.py` | `ClosedLoopConfig`、`load_closed_loop_config`、`with_named_load`、`with_open_loop_duty` |
| `circuits/closed_loop_buck.py` | `ClosedLoopBuck`、`build_closed_loop_buck`、`closed_loop_features` |
| `circuits/dynamic_load.py` | `CurrentStepLoad`、`CurrentStep`、`ResistiveStepLoad`、`pwl_points`、`current_at` |
| `circuits/input_disturbance.py` | `VinStep`、`step_points` |
| `simulations/averaged_model_runner.py` | `run_averaged_closed_loop`、`averaged_metrics` |
| `simulations/closed_loop_runner.py` | `ClosedLoopRun`、`run_closed_loop`、`run_closed_loop_with_fallback`、`save_closed_loop_run`、`calibrated_open_loop_duty`、`STEP_FALLBACK_CANDIDATES_S` |
| `analysis/transient_metrics.py` | `DisturbanceEvent`、`analyze_event`、`analyze_events`、`find_recovery_time`、`cycle_mean_waveform` |
| `analysis/startup_analysis.py` | `analyze_startup`、`StartupMetrics` |
| `analysis/control_comparison.py` | `compare_event_metrics`、`compare_startup`、`comparison_row`、`evaluate_limits` |
| `reports/transient_report.py` | `render_transient_report`、`write_transient_report` |

### 2.2 实验与脚本

- `experiments/load_step.py`（4 个负载工况 × 闭环/开环 + 平均模型）
- `experiments/line_step.py`（4 个输入阶跃工况）
- `experiments/soft_start.py`（0/2/5/10 ms 四档）
- `experiments/controller_tuning.py`（3×3 增益矩阵 + SPICE 复核）
- `experiments/closed_loop_validation.py`（E 平均开关 + SW 开关级验收）
- `scripts/load_step_demo.py`、`line_step_demo.py`、`soft_start_demo.py`、
  `controller_tuning_demo.py`、`closed_loop_buck_demo.py`、`buck_stage7_demo.py`、
  `feedforward_comparison_demo.py`

### 2.3 配置

- `configs/closed_loop_config.yaml`：Kp=0.0585、Ki=117.66、duty 0.02–0.90、
  tracking_gain=2000、soft_start 2 ms、正弦载波 100 kHz、阈值 0.5、宽度 0.02。
- `configs/transient_limits.yaml`：恢复容差 0.05 V；负载阶跃最差偏差限值 0.30 V；
  线阶跃 0.50 V；软启动超调 10%/峰值电流 4 A。

### 2.4 文档与测试

`docs/42_averaged_buck_model.md` 至 `docs/49_closed_loop_spice_netlist.md` 八份
（每份含公式、源码位置、真实结果、局限与 ≥5 道面试题）与本文件。新增 17 个
测试文件，见第 9 节。

## 3. 复用与缺口

- 复用第四/五阶段：非理想 Buck 功率级（`circuits/nonideal_buck.py`、
  `circuits/nonideal_config.py`）、器件模型、仿真运行器、限值判定与报告框架。
- **仓库中不存在第六阶段交付物**（无 `docs/34`–`41`、无对应模块），因此本阶段
  的开环基线取自第四/五阶段的真实功率级，并在验收记录中标注
  `known_gaps: stage6_missing`。没有伪造“第六阶段闭环基线”。
- 保留固定占空比开环 Buck 作为公平基线：同一功率级、同一负载、同一输入，
  开环占空比由平均模型离线校准（`calibrated_open_loop_duty`），每个工况单独
  取工作点（例如 1 A→2 A 工况为 0.440253）。

## 4. 环境与运行命令

```powershell
conda run -n kaifa_power python -m scripts.buck_stage7_demo --profile standard
conda run -n kaifa_power python -m reports.transient_report
conda run -n kaifa_power python -m pytest tests -q
```

环境：Windows + conda `kaifa_power`，Python 3.11，PySpice 1.5 + ngspice-34，
numpy/pandas/scipy/PyYAML/matplotlib。未修改 TestLab、kaifa、PySpice/ngspice 源码。

## 5. 功率级与开关模型

| 参数 | 值 |
| --- | --- |
| Vin / Vout / 负载 | 12 V / 5 V / 2.5 Ω |
| L / DCR | 47 µH / 0.05 Ω |
| C / ESR | 100 µF / 0.03 Ω |
| fs / T | 100 kHz / 10 µs |
| NMOS（Level-1） | VTO=3 V、KP=0.01、W/L=1000、RD=0.005 Ω、RS=0.002 Ω、Cgs=1 nF、Cgd=0.2 nF、Cds=0.3 nF |
| 二极管 | IS=1 µA、RS=0.015 Ω、CJO=200 pF |
| E 变体 | 理想受控源驱动栅极（`ECDRV`），保留全部无源非理想 |
| SW 变体 | 受控开关 `S1` + `ctrl=5*V(pwm)`，VH=0.02 V |

## 6. 平均模型、工作点与传递函数

状态方程（CCM）：

```
dIL/dt = (D*Vin - Vout - IL*(DCR + D*Rds_on) - (1-D)*Vd) / L
dVout/dt = (IL - Vout/R) / C
```

非理想平均模型还包含 ESR 零点与二极管压降。工作点与线性化：

- LC 自然频率 `f0 = 1/(2π√(LC)) = 2.322 kHz`；
- 额定工作点 D = 0.44480，正弦载波小信号增益 `(2/π)/√(1-(2d-1)²) = 0.6463`；
- 闭环特征根：`-637.30`、`-2720.09 ± j17409.56`（对应 2804.4 Hz、ζ=0.1544）；
- 环路 0 dB 穿越：165.7 Hz、1903 Hz、2528 Hz；相位裕度 63.49°，增益裕度
  **不可用（NaN）**——反相穿越点没有进入计算频段，标记为 NOT_RESOLVED。

平均模型运行结果与开关级明确区分（`data_source=averaged_model`、
`not_a_switching_waveform=true`）：闭环平均模型 Vout=4.99963 V、峰值 iL=2.124 A；
同一占空比开环平均模型 Vout=4.99999 V、峰值 iL=7.239 A。平均模型只用于设计
与对照，不作为开关波形证据。

## 7. 闭环 SPICE 实现

`control/spice_controller.py` 把 PI 写成 ngspice 行为源（B 源），在瞬态仿真中
**真实读取反馈并改变占空比**：

```
BERR  err  0  V = V(ref) - V(out)
BFF   ff   0  V = V(ref)/max(V(vin),2)              ; 输入前馈
BPROP prop 0  V = kp*V(err)
BCRAW raw  0  V = V(ff) + V(prop) + V(integ)
BCLIM duty 0  V = min(max(V(raw),0.02),0.90)
CCINT integ 0 1 ic=0
BCIINT 0 integ I = ki*V(err) + kaw*(V(duty)-V(raw)) ; 反算抗饱和
BCRAMP ramp 0 V = 0.5*(1+sin(2π*fs*time))           ; 正弦载波
BCPWM  pwm  0 V = clamp((duty-ramp)/0.02+0.5,0,1)   ; 平滑比较器
ECDRV  drv sw pwm 0 10
```

正弦载波对应有效占空比 `D = 0.5 + asin(2d-1)/π`，额定 d=0.4137 时 D=0.4448。
这不是“离线搜索占空比”：占空比每个时间步由反馈误差积分决定。开环基线则固定
占空比、无反馈，二者在同一网表结构下对比。

仿真步长：E/SW 验收 25 ns；线阶跃与软启动 50 ns。开环在 25 ns 出现
`Timestep too small`，由 `run_closed_loop_with_fallback` 显式回退到 50 ns，并把
`step_fallback={requested,used,attempts}` 写入运行元数据，不隐藏。

## 8. 实验结果

### 8.1 负载阶跃（SPICE，闭环 vs 固定占空比开环）

| 工况 | 方案 | 跌落 (V) | 超调 (V) | 最差偏差 (V) | 恢复 (ms) | 稳态误差 (mV) | IAE (V·s) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1→2 A | 闭环 | 0.5493 | 0.4290 | 0.5493 | 7.29 | -1.10 | 3.90e-4 |
| 1→2 A | 开环 | 0.6934 | 0.4003 | 0.6934 | 6.95 | -50.66 | 6.08e-4 |
| 2→1 A | 闭环 | 0.3221 | 0.5577 | 0.5577 | 7.25 | -1.23 | 3.04e-4 |
| 2→1 A | 开环 | 0.3345 | 0.6969 | 0.6969 | 未恢复 | +85.99 | 7.72e-4 |
| 0.5→2 A | 闭环 | 0.8412 | 0.6173 | 0.8412 | 7.65 | -0.79 | 5.81e-4 |
| 0.5→2 A | 开环 | 1.0362 | 0.5856 | 1.0362 | 未恢复 | -77.89 | 9.20e-4 |
| 10→2.5 Ω | 闭环 | 0.7031 | 0.3392 | 0.7031 | 6.24 | -10.65 | 2.42e-4 |
| 10→2.5 Ω | 开环 | 0.8537 | 0.2500 | 0.8537 | 未恢复 | -75.18 | 4.38e-4 |

闭环把最差偏差从 1.0362 V 降到 0.8412 V，但**仍高于 0.30 V 验收限值**，因此
负载阶跃相关检查为 FAIL。平均模型的同工况结果单独记录（如 1→2 A：0.5445 V），
仅作对照。

### 8.2 输入阶跃（12→9、9→12、12→16、16→12 V）

| 工况 | 方案 | 跌落 (V) | 超调 (V) | 最差偏差 (V) | 恢复 (ms) | 终值 (V) |
| --- | --- | --- | --- | --- | --- | --- |
| 12→9 | 闭环 | 0.5459 | 0.0641 | 0.5459 | 8.70 | 4.9975 |
| 12→9 | 开环 | 1.9143 | 0 | 1.9143 | 未恢复 | 3.7091 |
| 9→12 | 闭环 | 0 | 0.6743 | 0.6743 | 8.48 | 5.0001 |
| 9→12 | 开环 | 0 | 2.5972 | 2.5972 | 未恢复 | 6.7137 |
| 12→16 | 闭环 | 0 | 0.5885 | 0.5885 | 7.39 | 5.0000 |
| 12→16 | 开环 | 0 | 2.6258 | 2.6258 | 未恢复 | 6.7364 |
| 16→12 | 闭环 | 0.4507 | 0.0366 | 0.4507 | 8.13 | 5.0000 |
| 16→12 | 开环 | 1.8561 | 0 | 1.8561 | 未恢复 | 3.7044 |

闭环终值全部回到 5.000 V ±1 mV；最差偏差 0.6743 V 超过 0.50 V 限值，为 FAIL。
开环无反馈，输入变化直接改变输出，属于预期行为。

### 8.3 输入前馈开/关对照（12 V→9 V，同一 PI 与功率级）

| 前馈 | 跌落 (V) | 超调 (V) | 终值 (V) | 恢复 (ms) |
| --- | --- | --- | --- | --- |
| 开 | 0.5459 | 0.0641 | 4.99753 | 8.705 |
| 关 | 1.3053 | 0.2790 | 4.99314 | 10.735 |

一次真实的 SPICE 对照：去掉 `Vref/Vin` 前馈后跌落增加到 2.4 倍，恢复变慢。
数据：`results/stage7/experiments/feedforward_comparison.json`，脚本
`scripts/feedforward_comparison_demo.py`。该实验同时暴露并修复了一个缺陷：
`feedforward_enabled=false` 之前只作用于离散/平均控制器，SPICE 网表仍然写
`V(ref)/max(V(vin),2)`；修复后 BFF 源写为 `0`，默认配置（前馈开）的其它结果不变。

### 8.4 软启动（12 V→5 V，reference 斜坡）

| 斜坡 | 超调 | 峰值 iL | 峰值 iin | 判定 |
| --- | --- | --- | --- | --- |
| 0 ms | 61.72% | 9.164 A | 9.232 A | FAIL |
| 2 ms | 0.458% | 2.445 A | 3.831 A | PASS |
| 5 ms | 0.175% | 2.360 A | 3.783 A | PASS |
| 10 ms | 0.534% | 2.359 A | 3.640 A | PASS |

无软启动时参考电压阶跃导致占空比饱和、电感电流冲到 9.16 A；2 ms 斜坡已把
超调压到 0.46%。这是真实对比，不是模型拟合。

### 8.5 增益整定（3×3 矩阵 + SPICE 复核）

| Kp× | Ki× | PM (°) | 带宽 (Hz) | 评分 |
| --- | --- | --- | --- | --- |
| 0.5 | 2 | 100.76 | 258.0 | 2.99 |
| 0.5 | 1 | 101.98 | 125.9 | 5.98 |
| 1 | 1 | 63.49 | 113.9 | 6.64 |
| 1 | 2 | 54.79 | 232.3 | 8.49 |
| 0.5 | 0.5 | 102.59 | 62.3 | 12.01 |
| 1 | 0.5 | 67.56 | 56.5 | 13.32 |
| 2 | 2 | 32.08 | 214.0 | 31.82 |
| 2 | 1 | 35.12 | 105.1 | 32.70 |
| 2 | 0.5 | 36.63 | 52.2 | 39.08 |

默认参数（Kp=0.0585、Ki=117.66）即 1×/1× 行，PM 63.49°、带宽 113.9 Hz，是
“评分与相位裕度折中”的选择。SPICE 复核：selected 工况负载跌落 0.5493 V
（相对 11.05%），aggressive（2×/2×）反而为 0.4799 V（9.62%）。**未因此替换默认
参数**——单工况、单负载下的偏差不足以否定整定矩阵的综合评分，这一点在
`docs/48_controller_tuning.md` 中如实说明。

### 8.6 闭环验证（E 变体 / SW 变体）

| 指标 | E | SW |
| --- | --- | --- |
| 稳态均值 | 4.99842 V | 5.00043 V |
| 纹波（峰峰） | 0.03424 V | 0.04066 V |
| CCM 占比 | 1.000 | 1.000 |
| 缺失脉冲 / 多次脉冲 | 0 / 0 | 0 / 0 |
| 负载阶跃跌落 | 0.5493 V | 0.5546 V |
| 恢复时间（strict） | 7.285 ms | 8.335 ms |
| 启动超调 | 7.98% | 8.81% |

E 变体稳态偏差 -1.87 mV 但**开环 E 变体稳态 4.94935 V（偏差 -50.65 mV）超限**，
对应 FAIL。SW 变体负载跌落 0.5546 V 超过 0.30 V 限值，同样保留 FAIL。

### 8.7 调整率、一致性、CCM 与积分状态

- **闭环负载调整率**：用 load_step 的 1 A 与 2 A 阶跃终值（5.00123 V / 4.99890 V）
  计算为 -2.33 mV/A（0.047 %/A）；开环同口径为 -136.6 mV/A（2.73 %/A）。
  这两个数来自阶跃后的稳态窗口，不是独立的负载扫描。
- **闭环线调整率**：9/12/16 V 三个终值 4.99753/5.00007/4.99999 V，最差 0.85 mV/V。
- **平均模型与开关级一致性**：稳态 Vout 差 1.2 mV（4.99963 vs 4.99842 V），
  稳态 iL 差约 1 mA（1.996 vs 1.995 A）；平均模型不用于纹波/瞬态证据。
- **CCM**：12 V/2 A 的 E 与 SW 验证运行 `ccm_fraction=1.0`，无 DCM；轻载
  0.5 A 开环运行的瞬时 iL 最低 -32 mA，`ccm_fraction=0.845`（进入 DCM），
  闭环同工况 0.943。轻载开环的启动栅极振铃持续到约 1.23 ms，使
  `pwm_statistics_after_startup` 在 1.0–1.23 ms 报 22 个“多次脉冲”周期，
  `pwm_valid=false` 如实保留；稳态占空比仍为 0.4394。
- **积分状态变化**：12→9 V 线阶跃中积分节点从 -0.0107 变到 +0.0780（Δ=0.0887，
  占空比单位），对应前馈承担主通道、积分消除剩余误差。

## 9. 31 项验收检查（摘要）

| 检查 | 实际值 | 限值 | 状态 |
| --- | --- | --- | --- |
| SW 稳态均值 | 5.00043 V | 4.95–5.05 V | PASS |
| SW 纹波 | 0.040657 V | ≤0.05 V | PASS |
| SW CCM | 1.000 | ≥0.95 | PASS |
| SW PWM 缺失脉冲 | 0 | 0 | PASS |
| SW PWM 多次脉冲 | 0 | 0 | PASS |
| SW 负载跌落 | 0.55455 V | ≤0.30 V | FAIL |
| SW 恢复时间 | 8.335 ms | ≤10 ms | PASS |
| E 稳态均值 | 4.99842 V | 4.95–5.05 V | PASS |
| E 纹波 | 0.034236 V | ≤0.05 V | PASS |
| E CCM | 1.000 | ≥0.95 | PASS |
| E PWM 缺失脉冲 | 0 | 0 | PASS |
| E PWM 多次脉冲 | 0 | 0 | PASS |
| E 负载跌落 | 0.54928 V | ≤0.30 V | FAIL |
| E 恢复时间 | 7.285 ms | ≤10 ms | PASS |
| 开环 SW 稳态 | 4.97230 V | 4.95–5.05 V | PASS |
| 开环 E 稳态 | 4.94935 V | ≥4.95 V | FAIL（低 0.65 mV） |
| 平均模型负载跌落 | 0.544497 V | 仅参考 | PASS |
| 负载阶跃最差偏差 | 0.84122 V | ≤0.30 V | FAIL |
| 负载阶跃最差恢复 | 7.645 ms | ≤10 ms | PASS |
| 线阶跃最差偏差 | 0.67429 V | ≤0.50 V | FAIL |
| 无软启动超调 | 61.719% | ≤10% | FAIL |
| 无软启动峰值 iL | 9.1636 A | ≤4 A | FAIL |
| 软启动 2 ms 超调 | 0.45798% | ≤10% | PASS |
| 软启动 2 ms 峰值 iL | 2.44466 A | ≤4 A | PASS |
| 软启动 5 ms 超调 | 0.17489% | ≤10% | PASS |
| 软启动 5 ms 峰值 iL | 2.35977 A | ≤4 A | PASS |
| 软启动 10 ms 超调 | 0.53368% | ≤10% | PASS |
| 软启动 10 ms 峰值 iL | 2.35893 A | ≤4 A | PASS |
| 环路相位裕度 | 63.494° | ≥45° | PASS |
| 环路增益裕度 | NaN | ≥6 dB | NOT_RESOLVED |
| 整定选中方案跌落 | 0.54928 V | ≤0.30 V | FAIL |

共 31 项：22 PASS、8 FAIL、1 NOT_RESOLVED，与
`results/stage7/stage7_acceptance.json` 的 `overall_status=PARTIAL_FAILURE` 一致。
表中“SW/E 负载跌落”“负载阶跃最差偏差”“整定选中方案”指向同一 1 A→2 A
物理现象，但检查项不同，均按 0.30 V 限值记录 FAIL。


## 10. 测试

新增 17 个测试文件：

`test_control_models.py`、`test_pi_controller.py`、`test_anti_windup.py`、
`test_pwm_modulator.py`、`test_soft_start_module.py`、`test_averaged_buck_model.py`、
`test_transfer_functions.py`、`test_loop_analysis.py`、`test_controller_tuning.py`、
`test_spice_controller.py`、`test_closed_loop_config.py`、`test_dynamic_load.py`、
`test_input_disturbance.py`、`test_closed_loop_buck_builder.py`、
`test_transient_metrics.py`、`test_startup_analysis.py`、`test_stage7_experiments.py`。

全量结果：`532 passed`（含第四/五阶段既有测试与第七阶段新增测试），无跳过、
无 xfail。此前发现的 10 个失败中，6 个是测试假设与物理定义不符（PWL 过渡段、
PI 低频幅值、周期中点归属、恢复时间定义等）或限值文件命名不符，已按真实语义
修正测试；4 个是实现缺陷，已修复：

1. `classify_poles` 的 MARGINAL 分支在默认裕度下不可达（`>` 改为 `>=`）；
2. PWM 统计把跨周期边界的同一脉冲重复计数（改为按区间中点归属，并排除数据
   首尾截断的极窄片段）；
3. `ramp_rate_v_per_s` 对负斜坡时间返回 inf 而非报错（改为 `ValueError`）；
4. `BudgetCounter` 先自增后检查，超额时计数被污染（改为先检查后自增）。

其中第 2 项修复前，线阶跃运行被误报 1098 个“多次脉冲周期”（`valid=false`）。
修复后线阶跃与软启动的 PWM 统计均为 `multiple=0 / missing=0`，且不改变任何
已记录的电压、电流指标。

另有一个在前馈对照实验中发现的缺陷：`feedforward_enabled=false` 未传入 SPICE
网表（BFF 仍计算 `Vref/Vin`），修复后新增
`test_feedforward_can_be_disabled_in_netlist`，默认前馈开启的结果不受影响。

## 11. 产物路径

- 验收：`results/stage7/stage7_acceptance.json`、
  `results/stage7/stage7_acceptance_checks.csv`
- 实验：`results/stage7/experiments/{load_step,line_step,soft_start,
  controller_tuning,closed_loop_validation,feedforward_comparison}.json` 与
  `controller_tuning_matrix.csv`、`selected_closed_loop_poles.csv`、
  `selected_loop_bode.csv`
- 每次仿真：`results/stage7/runs/run_<时间>_<哈希>/`（网表、metadata、波形、指标）
- 报告：`results/stage7/stage7_transient_report.html` 与
  `results/stage7/figures/{startup_closed_vs_open,load_step_comparison,
  soft_start_summary,loop_gain_bode,tuning_matrix}.png`

## 12. 限制与未解决问题

1. **第六阶段缺失**：没有“第六阶段开环/闭环基线”可供复用，开环基线来自第四/
   五阶段真实功率级；验收 JSON 中记录 `stage6_missing`。
2. **正弦载波近似**：开关级用正弦载波 + 平滑比较器实现 PWM，`VH=0.02`；它不
   等价于真实三角波比较器的边沿时序，只用于教学验证。
3. **平均模型不等于开关波形**：平均模型的 Vout/iL 不能当作纹波或瞬态波形证据，
   所有标 `averaged_model` 的记录都带 `not_a_switching_waveform` 标记。
4. **增益裕度 NOT_RESOLVED**：计算频段内没有反相穿越，GM 记为 NaN，未用其他
   频段“补算”。
5. **负载阶跃 0.30 V 限值未放宽**：闭环最差 0.8412 V，属真实 FAIL；若要改善，
   需要更大带宽或前馈/电流环，属于后续阶段内容。
6. **开环步长回退**：25 ns 下开环 `Timestep too small`，50 ns 成功、100 ns 失败、
   200 ns 成功；回退记录写入每个运行目录，不隐瞒数值精度差异。
7. **整定矩阵的 aggressive 方案在 SPICE 单工况更优**（0.4799 V vs 0.5493 V），
   但未替换默认参数，原因见第 8.5 节。
8. 恢复时间采用“连续 20 个周期（200 µs）落在 ±50 mV 内”的定义；该定义对
   单调恢复的负载阶跃有效，对缓慢漂移信号可能提前判定，已在
   `analysis/transient_metrics.py` 文档字符串与本文件中说明。

## 13. 面试题索引

`docs/42`–`docs/49` 每份至少 5 道（共 40+ 道），覆盖：CCM 平均模型推导、
状态空间线性化、PI 零点/带宽/相位裕度、抗饱和反算、正弦载波有效占空比、
软启动斜坡与浪涌、负载/线阶跃指标定义、开环与闭环公平对比。本文件不重复列出。
