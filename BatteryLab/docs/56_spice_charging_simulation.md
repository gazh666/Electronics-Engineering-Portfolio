# 56 开关级充电仿真（真实 ngspice）

## 1. 网表结构

`circuits/charger_spice_controller.py::build_cascade_circuit` 生成完整网表，
控制器全部是 SPICE 行为源：

| 节点 | 作用 | 行为源 |
| --- | --- | --- |
| `vset` / `iset` / `en` | 恒压/恒流/使能 | 独立源，支持 DC 或 PWL |
| `ss` | 软启动 | `BSS ss 0 V={min(time/TSOFT,1)*u(V(en)-0.5)}` |
| `ilim` | 电流指令上限 | `BILIM ilim 0 V={V(iset)*V(ss)}` |
| `ev` / `xv` / `vraw` / `iref` | 电压 PI | `BEV`、`CXV`、`RXV`、`BVRAW`、`BIREF` |
| `vfrz` | 电压环冻结 | `BVFRZ` |
| `ei` / `xi` / `draw` / `duty` | 电流 PI | `BEI`、`CXI`、`RXI`、`BDRAW`、`BDUTY` |
| `ff_in` / `ff` | 滤波前馈 | `RFF`、`CFF`、`BFF` |
| `ifrz` | 电流环冻结 | `BIFRZ` |
| `ramp` / `graw` / `gate` | PWM 与驱动 | `BRAMP`、`BGATE`、`RG`、`CG` |

要点：

1. **没有 Python 预生成波形**。所有积分、限幅、PWM 比较都由 ngspice 求解；
   Python 只负责构建网表、读取结果、计算指标。
2. 积分节点用 1 kΩ 泄漏 + `u(time-1e-9)` 门控，保证 DC 工作点唯一、t=0 时积分从 0 开始。
3. PWM 比较器带 1 mV 偏置，避免占空比恰好等于 ramp 时出现零宽度脉冲。
4. 时间步 20 ns；大于 20 ns 直接拒绝求解（见 docs/55 §4.1）。

## 2. 电池夹具与保护接口

- 3 节独立 `OCV + R0 + R1‖C1`，参数来自 `calce_sp2_25c_inr18650_20r_first_order_v1`；
- 节间节点 `t1/t2` 可直接读出每节端电压，供保护回灌；
- 保护许可：运行前用第五阶段真实 `ProtectionController` 校验初始单体电压，
  不允许充电时拒绝运行；运行后逐 20 点回灌真实波形，记录首次禁止时间与锁存故障。

## 3. 开关断点处的数值伪影与处理

现象：ngspice 在 PWM 跳变处会取 fs 级时间步（实测最小 `dt ≈ 4e-13 s`）。
此时 788 F 极化电容的 `C/dt ≈ 2e21 S` 与 77 mΩ 内阻形成极端条件数，
单体电压的**分配**出现 bt–ps 级伪影（总和仍守恒，pack 电压正常）。

| 量 | 处理 |
| --- | --- |
| 单体电压限值判定 | 使用 PWM 周期平均（等效 AFE 的 ms 级采样） |
| 瞬时极值 | 如实写入 `raw_limits.instantaneous_*`，不隐藏 |
| 断点样本数 | 写入 `raw_limits.switching_breakpoint_steps` |
| 判定依据 | 写入 `raw_limits.voltage_check_basis` |

这不是"清洗数据"：判定依据被显式记录，任何读者都能看到瞬时值与判定值的差别。

## 4. C01–C03 实测

步长 20 ns，真实 ngspice；工况目录见 `results/stage6/run_stage6_*`。

| 工况 | 稳态电流 | 稳态电压 | CV | 切换时刻 | 电压过冲 | CC 误差 | CV 误差 | 判定 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C01 | 1.0011 A（周期均值） | 11.631 V | 否 | — | — | 1.09 mA | — | PASS |
| C02 | 0.1579 A | 12.136 V | 是 | 0.600 ms | 0 mV | — | −13.50 mV | PASS |
| C03 | 0.8457 A | 12.146 V | 是 | 6.790 ms | 2.07 mV | — | −4.45 mV | PASS |

C01 启动峰值 1.0834 A，启动过冲 8.34%（限值 10%）。C02 初始等效电压 12.10 V，
一进入就接近恒压点，因此 0.6 ms 即进入 CV；C03 初始 11.95 V，6.79 ms 完成切换。

## 5. 复现

```bash
conda run -n kaifa_battery python -m scripts.stage6_cascade_cccv_demo
conda run -n kaifa_battery python -m scripts.stage6_validation_demo
```

每个工况保存：

- `circuit.cir`（完整网表，可人工检查行为源）
- `waveform.csv`（抽稀到 ≤ 20000 行，`summary.json` 记录抽稀比）
- `summary.json`（指标、检查项、保护回灌、限值核查）
- `config_snapshot.json`（充电器/控制器/级联参数/夹具）

## 6. 不适用范围

- 8–12 ms 短窗不积分 SOC，不能给出充电进度；
- 保护确认延时多数大于短窗，因此"未锁存"不等于"不会动作"；
- 未建模输入 ACFET、电池侧隔离 FET、同步整流管与开关损耗；
- 不能把本网表的效率、纹波、补偿参数直接外推到 BQ24610 硬件。
