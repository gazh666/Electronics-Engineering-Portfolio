# 第六阶段工程证据：3S 电池组 CC-CV 充电

日期：2026-11-26
最终验收：`results/stage6/run_stage6_20261126_155147_64c696`
结论：20/20 工况 PASS，13/13 预登记限值 PASS，56/56 检查 PASS，12 次真实 ngspice 求解。

## 1. 交付内容

| 类别 | 文件 | 说明 |
| --- | --- | --- |
| 配置 | `configs/charger_config.yaml` | 18 V / 12.15 V / 1 A / 100 kHz / 1 ms 软启动 |
| 配置 | `configs/charge_controller.yaml` | 电压 2.0/2000/50，电流 0.025/50/1000 |
| 配置 | `configs/charging_cases.yaml` | 20 个工况，逐条标注仿真层次 |
| 配置 | `configs/stage6_validation.yaml` | 13 项预登记限值 |
| 电路 | `circuits/charger_buck.py` | 功率级 + 3S 夹具网表 |
| 电路 | `circuits/charger_current_feedback.py` | 电流内环网表 |
| 电路 | `circuits/charger_spice_controller.py` | 网表内双闭环 + PWM，20 ns 守卫 |
| 电路 | `circuits/charger_switch_models.py` | 开关/二极管模型 |
| 模型 | `simulations/averaged_charger.py` | 平均模型（整定对照） |
| 模型 | `simulations/long_duration_charge.py` | ECM 长时包络 + 保护联锁 |
| 调度 | `simulations/charger_spice_runner.py` | 12 个开关级工况与 BMS 核查 |
| 调度 | `simulations/charging_experiments.py` | 20 工况分流与汇总 |
| 分析 | `analysis/charging_metrics.py` 等 6 个模块 | 指标、能量、效率、环路、切换、验收 |
| 脚本 | `scripts/stage6_*.py`（11 个 + common） | 可复现实验 |
| 测试 | `tests/test_stage6_*.py`（9 个文件，50 项） | 单元与集成 |
| 硬件 | `hardware/charger/`（5 个文件） | BQ24610 参考研究 |
| 文档 | `docs/53`–`docs/64` | 架构、设计、控制、仿真、瞬态、环路、效率、长时、保护、硬件、测试、验收 |

## 2. 最有说服力的证据

1. **网表内闭环，不是 Python 造波形**
   `run_cascade_buck` 的网表包含 `BEV/BVRAW/BIREF/BIV`（电压环）、
   `BEI/BDRAW/BDUTY/BII`（电流环）、`BRAMP/BGATE`（PWM）。
   12 个开关级工况的 `circuit.cir` 均可人工检查；验收检查项
   `no_python_generated_waveform` 逐例验证网表含 `BII 0 xi I=`。

2. **控制性能**
   - C01：周期平均 1.0011 A，启动过冲 8.34%；
   - C02：0.600 ms 进入恒压，CV 误差 −13.5 mV；
   - C03：6.790 ms 完成切换，电压过冲 2.07 mV；
   - 输入 ±2 V 阶跃后稳态误差 ≤ 1 mA。

3. **保护真实联锁**
   运行前拒绝无许可工况，运行后逐 20 点回灌第五阶段真实控制器。
   C11 在 293.5 s、单体 4.2503 V、组压 11.9655 V 时锁存 OV；C12/C13/C15/C17
   分别验证温度、测量失效、终止抖动与禁止自动重启。

4. **数值可靠性可复现**
   - 50 ns 会出 0.1–0.4 A 伪极限环，20 ns 才可靠，10 ns 报 timestep too small；
   - 前馈必须滤波（τ=1 ms）且不乘软启动；
   - 抗饱和必须"冻结 + 反计算"，纯反计算造成约 25 mA 单向偏差。

## 3. 工程判断与取舍

| 决策 | 取舍 |
| --- | --- |
| 100 kHz 而非 600 kHz | 20 ns 步长下能分辨 PWM；600 kHz 需 ≤4 ns，本机不稳定 |
| 异步整流 | 简化器件模型；效率 98% 不可外推 |
| 短窗夹具固定 OCV | 8–12 ms 不积分 SOC，换来可读的开关级波形 |
| 长时用准静态 CV | 73–95 Hz 环无法在秒级离散；明确标注与网表 PI 不同层 |
| 恒压 12.15 V | 低于 OV 释放 4.15 V/节；但导致"不一致不会触发 OV"的负结果 |
| 断点伪影用周期平均判定 | 等效 AFE 采样；瞬时值仍完整保留 |

## 4. 发现的真实问题（不是包装成成功）

1. **5 ms 软启动与 8–12 ms 工况窗口冲突**：CC 指标会测在瞬态上，4 ms 阶跃也
   落在软启动内。改为 1 ms，并保留限值不变。
2. **纯反计算抗饱和有稳态偏差**：C01 曾出现 −25 mA 指令偏移，改为条件积分冻结。
3. **平均模型/线性化的负载建模错误**：用 `Vout/Iout` 会把电流环穿越低估 40 倍。
4. **恒压目标下不一致不会触发过压**：C18 最高单体 4.1844 V < 4.25 V；
   C11 必须用 CC-only 故障注入才能演示，且已作为负结果记录。
5. **短窗不能证明保护不会动作**：确认延时大于窗口，文档明确区分锁存与原始限值。
6. **开关断点的单体电压数值伪影**：fs 级步长 + 788 F 极化电容导致条件数爆炸；
   用 PWM 周期平均判定并公开瞬时值与断点数。

## 5. 可复现命令

```bash
conda run -n kaifa_battery python -m scripts.stage6_theory_demo
conda run -n kaifa_battery python -m scripts.stage6_open_loop_demo
conda run -n kaifa_battery python -m scripts.stage6_current_loop_demo
conda run -n kaifa_battery python -m scripts.stage6_cascade_cccv_demo
conda run -n kaifa_battery python -m scripts.stage6_input_transient_demo
conda run -n kaifa_battery python -m scripts.stage6_reference_transient_demo
conda run -n kaifa_battery python -m scripts.stage6_loop_analysis_demo
conda run -n kaifa_battery python -m scripts.stage6_efficiency_demo
conda run -n kaifa_battery python -m scripts.stage6_long_charge_demo
conda run -n kaifa_battery python -m scripts.stage6_protection_gating_demo
conda run -n kaifa_battery python -m scripts.stage6_validation_demo
conda run -n kaifa_battery python -m pytest tests -q
conda run -n kaifa_battery pip check
```

## 6. 明确未验证

- 保护 FET 断开后的电气重分布；
- 真实 BQ24610 的 ACFET/BATDRV、同步整流、开关损耗；
- 硬件效率、温升、保护响应时间；
- NTC 开路/短路；
- 5 s 故障全清的长时行为；
- 绝对 SOC 与充电进度（终止 SOC 超出辨识区间，属外推）；
- DCM 下的小信号稳定性。

以上均标为 NOT_VERIFIED，未计入 56 项通过检查。
