# 53 充电系统架构

本阶段在第三阶段冻结电池模型、第四阶段采集链、第五阶段保护之上，实现
3S 锂离子电池组的 CC-CV 充电：Buck 功率级、双闭环控制、充电状态与保护联锁。

## 1. 分层结构

```text
18 V 适配器（理想源 / PWL 输入扰动）
   │
   ├─ Buck 功率级：SMAIN、DFREE、L=100 µH、DCR=50 mΩ、C=220 µF、ESR=30 mΩ
   │      └─ 真实 ngspice 网表：circuits/charger_buck.py
   │
   ├─ 控制器（SPICE 行为源，位于网表内）
   │      ├─ 电压外环 PI：kp=2.0，ki=2000，kaw=50
   │      ├─ 电流内环 PI：kp=0.025，ki=50，kaw=1000
   │      ├─ 软启动 1 ms、滤波前馈 τ=1 ms
   │      └─ 条件积分冻结 + 反计算抗饱和
   │
   ├─ 电池夹具：3 节独立 OCV + R0 + R1‖C1（第三阶段冻结参数）
   │      └─ 仅在短窗（8–12 ms）内求解，不积分 SOC
   │
   └─ BMS 许可：第五阶段真实 ProtectionController
          ├─ 运行前：初始单体电压 → charge_allowed 必须为 True
          └─ 运行后：真实波形逐点回灌，记录许可/故障/限值
```

## 2. 模块边界

| 层 | 模块 | 职责 | 不允许做的事 |
| --- | --- | --- | --- |
| 电路 | `circuits/charger_buck.py` | 功率级与 3S 夹具网表 | 生成波形、做控制决策 |
| 电路 | `circuits/charger_current_feedback.py` | 只闭合电流内环 | 宣称 CC-CV 达标 |
| 电路 | `circuits/charger_spice_controller.py` | 网表内级联 PI + PWM | 在 Python 侧预生成波形 |
| 模型 | `simulations/averaged_charger.py` | 平均模型整定与趋势 | 宣称开关级纹波/限流验证 |
| 模型 | `simulations/long_duration_charge.py` | 秒级 ECM 长时包络 | 宣称开关级动态 |
| 调度 | `simulations/charger_spice_runner.py` | 12 个开关级工况、BMS 核查、落盘 | 伪造许可或波形 |
| 调度 | `simulations/charging_experiments.py` | 20 工况分流与汇总 | 混合不同层次的结论 |
| 分析 | `analysis/charging_*.py` | 指标、能量、环路、切换识别 | 修改实测数据 |
| 硬件 | `hardware/charger/` | BQ24610 参考研究 | 把数据手册值当实测 |

## 3. 电流符号约定

| 位置 | 正方向 | 说明 |
| --- | --- | --- |
| ECM 电池模型 | 放电为正 | 第三阶段冻结约定 |
| 充电控制器 | 充入电池为正 | `Ichg > 0` |
| 适配器 | `Iecm = -Ichg` | `charging/battery_adapter.py` |
| 保护控制器 | 放电为正 | 因此回灌时传入 `-Ichg` |

两个约定在 `charging/battery_adapter.py` 与 `simulations/charger_spice_runner.py`
中显式转换；任何新增模块必须复用这两个转换函数，不得自行改变符号。

## 4. 电芯夹具的边界

短窗开关实验使用 `PackFixture.from_equivalent_voltage`：给定电池组等效开路电压
（如 11.4 / 11.95 / 12.10 V），内阻与极化仍取冻结参数，SOC 只由 OCV 表反查，
**不参与积分**。因此：

- 开关级结果只说明 8–12 ms 内的电气与控制行为；
- 充电进度、终止判定、SOC 一致性必须由 `long_duration_charge.py` 回答；
- 两类结果不得拼接成一条充电曲线。

## 5. 保护联锁的数据流

```text
fixture 初始单体电压 ──► ProtectionController.update(t=0, I=0) ──► charge_allowed?
        │ False：拒绝运行（不伪造许可）
        ▼ True
ngspice 求解 ──► 每 N 点回灌 ProtectionController ──► 首次禁止时间 / 锁存故障
        │
        └─ 同时做逐点原始限值核查（PWM 周期平均，等效 AFE 采样）
```

短窗（8–12 ms）短于多数确认延时，因此"未锁存"不能解释为"保护不会动作"；
文档中同时给出锁存结论与原始限值结论。

## 6. 文件与结果

| 内容 | 路径 |
| --- | --- |
| 充电器配置 | `configs/charger_config.yaml` |
| 控制器配置 | `configs/charge_controller.yaml` |
| 20 个工况 | `configs/charging_cases.yaml` |
| 预登记限值 | `configs/stage6_validation.yaml` |
| 开关级网表/波形/汇总 | `results/stage6/run_stage6_*` |
| 硬件参考 | `hardware/charger/` |
