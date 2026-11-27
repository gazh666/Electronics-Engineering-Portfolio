# BatteryLab 真实量化工程成果总表

- 审计运行：`run_20261126_175610`
- 审计脚本：[audit_resume_metrics.py](file:///BatteryLab/scripts/audit_resume_metrics.py)
- 完整 16 字段证据表（80 行）：[BatteryLab_resume_metrics.csv](file:///BatteryLab/portfolio/BatteryLab_resume_metrics.csv)
- 全量回归：`550 passed`（2026-11-26，`kaifa_battery` 环境）
- 验证状态统计：VERIFIED 74 项、NOT_VERIFIED 5 项、VERIFIED（合成）1 项

> 本表只收录能从原始结果文件复算或直接从原始运行 JSON 读取的指标。凡缺少原始证据、或原始证据本身为行为模型/合成数据的，均在“验证状态/局限”中明示，不用配置值替代输出值。

---

## 一、各阶段实际完成状态

| 阶段 | 实际完成内容 | 状态 | 主要证据 |
|---|---|---|---|
| 1 公开数据与 PyBaMM | CALCE INR18650-20R 数据加载、OCV 提取、PyBaMM SPM 交叉 | 完成 | `results/stage1/` |
| 2 ECM 与 3S 建模 | Rint / 一阶 RC / 二阶 RC、3S 串并联、SPICE 对照 | 完成 | `results/stage2/run_stage2_20261126_123052_b15f65` |
| 3 OCV-SOC 与辨识 | OCV 查表、R0/R1/C1/R2/C2 辨识、6 个独立动态工况验证 | 完成（含 1 项 FAIL） | `results/ocv/`、`results/identification/`、`results/dynamic_validation/` |
| 4 AFE 模拟采集 | 分压+差分放大、双向电流、NTC、RC 滤波、12 位 ADC、1000 组容差统计 | 完成（最坏预算 RISK） | `results/sensing/` |
| 5 MOSFET 保护/状态机/均衡 | 背靠背 MOSFET、比较器+确认延时、10 类故障、被动均衡 12 h | 完成 | `results/protection/`、`results/stage5_validation/` |
| 6 CC-CV 充电与闭环 | 开关级 Buck、CC/CV 双环、软启动、抗积分饱和、平均模型稳定裕度 | 完成（软启动/PI/抗饱和无前后对照） | `results/stage6/` |
| 7 SOC 与 SOH | 安时积分、OCV、EKF 观测器、静置校正、容量/内阻 | 完成（真实老化 NOT_VERIFIED） | `results/stage7/`、`results/soc_estimation/`、`results/battery_health/` |
| 8 真实器件与 KiCad | 引脚映射、BOM、降额、MOSFET 候选、设计评审 | 部分完成（KiCad 未安装） | `results/eda/run_stage8_20261126_165159_f06bd0` |
| 9 三项目联合仿真 | 同网表联合 SPICE、功率映射、保护注入、长期放电、老化、能量、TestLab | 工程执行完成，文档未闭合 | `results/system_spice/`、`results/stage9/`、`results/converter_power_map/` |
| 10 最终工程交付 | orchestrator standard、docs/100–104、portfolio 第九阶段三篇 | 未执行 | — |

阶段 8 的 KiCad 原理图/PCB/ERC/DRC/Gerber/STEP 均为 BLOCKED；阶段 9 的 `docs/100–104` 与 `portfolio` 第九阶段三篇尚未生成，因此“最终工程交付”不能宣称完成。

---

## 二、核心量化指标（按研发模块）

### 2.1 电池等效电路与参数辨识

| 编号 | 指标 | 数值 | 单位 | 验证 | 证据 |
|---|---|---|---|---|---|
| M01 | Rint 模型独立验证 RMSE（FUDS 50/80 平均） | 26.705 | mV | VERIFIED | `residuals.csv.gz` |
| M02 | 一阶 RC 独立验证 RMSE（FUDS 50/80 平均） | 22.385 | mV | VERIFIED | 同上 |
| M03 | 二阶 RC 独立验证 RMSE（FUDS 50/80 平均） | 22.175 | mV | VERIFIED | 同上 |
| M04 | Rint→一阶 RC 误差降低 | 16.18 | % | VERIFIED | 同数据集同区间 |
| M05 | 一阶→二阶 RC 误差降低 | 0.93 | % | VERIFIED | tau2 触下界 |
| M06 | FUDS 80% 最大瞬时误差 | 375.836 | mV | VERIFIED / FAIL | 空电区 4 A |
| M07 | R0 欧姆内阻 | 77.068 | mΩ | VERIFIED | `identified_parameters.csv` |
| M08 | R1 / C1 / tau1 | 22.845 mΩ / 788.6 F / 18.02 s | — | VERIFIED | 同上 |
| M09 | R2 / C2 / tau2 | 7.377 mΩ / 13555.6 F / 100.0 s | — | VERIFIED（边界） | tau2 下界 |
| M11 | 充放电 OCV 最大迟滞 | 129.0 | mV | VERIFIED | `ocv/summary.json` |
| M12 | 3 只电芯 OCV 最大差 | 23.234 | mV | VERIFIED | 原始字段单位已纠正 |
| M13 | 线性 vs PCHIP 插值最大差 | 11.610 | mV | VERIFIED | `ocv_interpolation_comparison.csv` |

数据规模：8 个公开动态工况；其中 7 个进入独立/开发验证汇总，共 64,407 个动态验证点；OCV 实测 147,659 点压缩为 201 点查表。

**适用范围必须说清**：22.385 / 22.175 mV 与 16.18% / 0.93% 只对应 **FUDS 50%/80% 两个工况**。同一次验证中，US06/BJDST 四个工况的一阶 RC RMSE 为 **40.652–53.599 mV**，部分工况并不优于 Rint。不得把这四个工况并入“22 mV / 16.18%”的表述，也不得用 FUDS 的最好结果代表全工况。

### 2.2 AFE 模拟采集与校准

| 编号 | 指标 | 校准前 | 校准后 | 单位 | 改善 | 验证 |
|---|---|---|---|---|---|---|
| A01 | 单体电压最大误差（1000 组容差） | 23.657 | 3.226 | mV | 86.36% | VERIFIED（统计） |
| A02 | 单体电压 RMSE | 7.5848 | 0.8730 | mV | 88.49% | VERIFIED（统计） |
| A03 | 电流最大误差 | 24.146 | 3.004 | mA | 87.56% | VERIFIED（统计） |
| A04 | 电流 RMSE | 6.5249 | 0.8396 | mA | 87.13% | VERIFIED（统计） |
| A05 | 仅零点校准后电流最大误差 | — | 20.166 | mA | — | VERIFIED |
| A06 | NTC 温度 RMSE | 0.1596 | 0.0199 | ℃ | 87.51% | VERIFIED |
| A07 | RC 截止频率（SPICE / 理论） | 7695.23 / 7696.08 | — | Hz | 误差 0.011% | VERIFIED |
| A08 | 100 kHz 干扰衰减 | 0.14141 V RMS → 0.01085 V RMS | −22.301 | dB | — | VERIFIED |
| A09 | RC 阶跃上升时间（SPICE / 理论） | 45.427 / 45.434 | — | µs | 误差 0.015% | VERIFIED |
| A09B | RC 建立时间（SPICE / 理论） | 95.333 / 95.231 | — | µs | 误差 0.107% | VERIFIED |
| A10 | ADC 分辨率 / LSB | 12 bit / 0.8057（前端增益 0.5 时输入折算 1.611 mV/LSB） | — | bit / mV | — | VERIFIED |
| A11 | 双向电流跨导 | 0.50000006（输入折算 1.611 mA/LSB） | — | V/A | — | VERIFIED |
| A12 | 差分增益 / CMRR 下界 | 0.49999925 / 133.98 | — | V/V / dB | — | VERIFIED |
| A13 | 最坏情况误差预算 | 30.887 mV / 37.736 mA | — | — | RISK | VERIFIED |
| A14 | NTC 测温范围 / 最大温度误差 | 0–60℃ / 0.00085（SPICE vs 理论） | — | ℃ | — | VERIFIED |
| A15 | NTC 含 12 位 ADC 最大温度误差 | 0.01290 | — | ℃ | — | VERIFIED |
| A16 | NTC 自热温升 | — | — | ℃ | — | **NOT_VERIFIED**（缺耗散系数） |

> 注：A09B、A14–A16 直接取自 `results/sensing/run_sensing_20261126_135324_f7f014` 与 `.../135306_def360` 的 summary；未单独进入简历 CSV，简历未引用这三项。全程 `waveform.csv` 为 484,142 数据点、25 ns 步长。

关键区分：12 位 ADC 的 0.8057 mV/LSB 是**理论量化步长**；A01/A02 的 3.226 mV / 0.873 mV 是**含容差统计误差**；两者不是同一概念，最坏情况预算仍是 RISK。

### 2.3 MOSFET 保护与故障状态机

| 编号 | 指标 | 数值 | 单位 | 验证 / 验收 |
|---|---|---|---|---|
| P01 | 保护阈值组 OV/UV/充电OC/放电OC/短路/过温 | 4.25 / 2.80 / 1.50 / 4.00 / 8.00 / 65 | V,A,V,A,A,℃ | VERIFIED / PASS（工程配置值） |
| P02 | 故障注入工况通过数 | 10/10 | 个 | VERIFIED / PASS |
| P03 | 关断后电池电流抑制比 | 0.00123（约 0.123%） | — | VERIFIED / 记录（行为源钳位） |
| P04 | “电流抑制时刻” | 2.5 | ns | **NOT_VERIFIED / ARTIFACT** |
| P04B | 栅极关断指令相对故障 | 10.0 | µs | VERIFIED / PASS |
| P05 | 保护后输入电压衰减 | 199.0 | µs | VERIFIED |
| P06 | 保护后输出维持 | 460.1 | µs | VERIFIED / PASS |
| P07 | 背靠背 MOSFET 1 A 压降 / 单管 Rds(on) | 37.584 mV / 18.666 mΩ | — | VERIFIED |
| P08 | 双向阻断残余电流（12.6 V） | 1.00 | nA | VERIFIED |
| P09 | 比较器跳闸误差 / 迟滞误差 | 46 µV / 0.31 mV | — | VERIFIED |
| P10 | 确认延时误差 | 0.074 | % | VERIFIED |
| P11 | 第五阶段验收检查 | 41/41 | 项 | VERIFIED |

**重要更正**：P04 的 2.5 ns 早于 12.010 ms 的栅极关断指令 10 µs，属行为电流源在故障时刻的钳位伪迹，不能当作物理保护响应时间。真实可报告的保护时序为“故障→栅极指令 10 µs；指令→输入衰减 199 µs；输出维持 460 µs”。

### 2.4 被动均衡

| 编号 | 指标 | 均衡前 | 均衡后 | 单位 | 改善 | 验证 |
|---|---|---|---|---|---|---|
| B01 | 3S 单体最大压差 | 130.000 | 10.470 | mV | 91.95% | VERIFIED |
| B02 | 无均衡同条件对照（12 h） | 130.000 | 130.000 | mV | 0.00% | VERIFIED（对照） |
| B03 | 均衡支路电流 / 峰值功耗 | — | 41.783 mA / 174.65 mW | — | — | VERIFIED |
| B03B | 均衡 MOSFET 导通损耗（峰值） | — | 0.0698 | mW | — | VERIFIED |
| B04 | 12 h 累计耗散能量 | — | 1.3393 | Wh | — | VERIFIED |
| B04B | 12 h 累计消耗容量 | — | — | Ah | — | **NOT_VERIFIED**（未单独记录） |
| B05 | 电池组 SOC 估计误差（忽略→计入均衡） | 1.970 | 0.000 | pp | 100% | VERIFIED |
| B06 | 3S 单体 SOC 最大差异 | 11.818 | 0.952 | pp | 91.95% | VERIFIED |

B02 为本次审计新增的同条件对照：同一初始 SOC、同一 12 h、同一 ECM，仅关闭均衡许可，压差保持 130 mV，证明 B01 的压差缩小来自均衡而非静置恢复。B05 是 SOC 估计误差，不是真实均衡硬件效果。

### 2.5 CC-CV 充电与闭环控制

| 编号 | 指标 | 数值 | 单位 | 验证 |
|---|---|---|---|---|
| C01 | 恒流稳态电流误差 | 0.00109 | A | VERIFIED / PASS |
| C02 | 恒压稳态电压误差 | 0.01350 | V | VERIFIED / PASS |
| C03 | CC→CV 切换过冲 | 2.07 | mV | VERIFIED / PASS |
| C04 | 功率级效率 | 98.01 | % | VERIFIED / PASS |
| C05 | 电压环相位裕度 | 107.22 | deg | VERIFIED / PASS |
| C06 | 软启动启动过冲 | 8.34 | % | **NOT_VERIFIED（无前后对照）** |
| C07 | PI 优化前后动态性能 | — | — | **NOT_VERIFIED** |
| C08 | 抗积分饱和前后恢复时间 | — | — | **NOT_VERIFIED** |

C06 的 8.34% 是“有软启动”的实测启动过冲，但历史结果没有保留“无软启动”的同条件波形，无法给出改善比例；C07/C08 同理，不能编造前后数字。

**CC-CV 其余要求项的真实状态**：

| 要求项 | 状态 | 说明 |
|---|---|---|
| 充电输入/输出电压 | 18 V / 12.15 V | 配置与 SPICE 工况 |
| 总充电时间 / 充电容量 / 充电能量 | NOT_VERIFIED | 只有开关级短窗，无完整充电过程 |
| 含辅助电源的系统效率 | NOT_VERIFIED | 未建辅助电源损耗 |
| 电感峰值电流 / 铜损 / 电容 ESR 损耗 | 部分 | IL 峰 2.2995 A（第九阶段）；铜损/ESR 未分离 |
| 控制器 Kp / Ki | 2 / 2000 | 冻结值 |
| 带宽 | NOT_VERIFIED | 仅给相位裕度 107.22° |
| 负载/输入扰动最大偏差与恢复时间 | NOT_VERIFIED | 未保留该工况 |
| 软启动前后峰值电流 | NOT_VERIFIED | 无前后对照 |
| BMS 保护联动切断 | 10 µs / 199 µs / 460 µs | 故障→指令 / 指令→输入衰减 / 输出维持 |

### 2.6 SOC 与 SOH

| 编号 | 指标 | 数值 | 单位 | 验证 |
|---|---|---|---|---|
| E01 | ECM 观测器 SOC RMSE（4 工况平均） | 1.8247 | pp | VERIFIED / PASS |
| E02 | 端电压查表 → 观测器 RMSE 降低 | 12.5433 → 1.8247 | pp | 85.45% / VERIFIED |
| E03 | SOC 最大误差 | 3.087 | pp | VERIFIED / PASS |
| E04 | 有效覆盖率 | 1.000 | — | VERIFIED |
| E05 | 静置 OCV 校正终值误差（合成夹具） | −5.000 → −0.0189 | pp | VERIFIED（合成真值） |
| E06 | +20 pp 初始偏差收敛时间 | 479.6 | s | VERIFIED / PASS |
| E07 | 真实容量 SOH | 100（仅 1 次循环） | % | 无老化含义 |
| E08 | 合成 100 循环容量保持率 | 90.1 | % | VERIFIED（合成） |
| E09 | 真实表观 DCIR | 0.073274 | Ω | VERIFIED |

SOC 误差统一用百分点 pp。SOC 参考由公开数据电流积分推导，不是直接实测真实 SOC；E07/E08 不能描述为“本项目降低了真实电池老化”。

### 2.7 真实器件与硬件设计

| 编号 | 指标 | 数值 | 验证 |
|---|---|---|---|
| H01 | BQ76922 引脚映射 | 33 行（32 pin + PAD） | VERIFIED / PASS |
| H02 | BQ24610 引脚映射 | 25 行（24 pin + PAD） | VERIFIED / PASS |
| H03 | 关键网络 / 器件库 / MOSFET 候选 | 18 / 17 / 4 | VERIFIED |
| H04 | BOM 行数 / issue | 51 / 0 | VERIFIED / PASS |
| H05 | 原理图/PCB/ERC/DRC/Gerber/STEP | 全部 BLOCKED | **NOT_VERIFIED** |
| H06 | LLC 谐振频率（目标 12–17 kHz） | 11.07 kHz | VERIFIED / **FAIL** |
| H07 | 分流功耗 / 充电设定 / 电感纹波 | 62.5 mW / 1.0061 A / 0.299 A | VERIFIED |
| H08 | 降额项 / 评审文档 | 13 / 3 份 CSV + FMEA + 验证计划 | VERIFIED |

BQ76922、BQ24610 的研究状态是“数据手册级引脚/网络/选型核查”，不是芯片实测，不能把 Datasheet 典型精度当成项目采集精度。

**硬件交付状态明细**：

| 要求项 | 实际值 | 状态 |
|---|---|---|
| 已完成原理图 | 0 | BLOCKED（KiCad 未安装） |
| 已完成 PCB | 0 | BLOCKED |
| PCB 层数 / 板卡尺寸 | — | NOT_VERIFIED |
| BOM 元器件行数 | 51（BMS 26 + 充电器 25） | VERIFIED |
| 关键商业器件选型 | BQ76922、BQ24610、CSD17578Q5A 等 | VERIFIED |
| MOSFET 候选对比 | 4 款 | VERIFIED |
| 关键引脚核查 | 58（33 + 25） | VERIFIED |
| 关键网络核查 | 18 条 | VERIFIED |
| 封装核查 | 8 项 | BLOCKED |
| ERC / DRC 错误与警告 | — | NOT_VERIFIED |
| 未连接网络 | — | NOT_VERIFIED |
| 关键子电路 SPICE 复验 | 见第二至第六阶段（6/68/12/12 次） | VERIFIED |
| Gerber / 钻孔 / 3D | — | NOT_VERIFIED |
| 设计评审 | 3 份 CSV + FMEA + 验证计划 | VERIFIED |
| 器件降额 | 13 项 | VERIFIED |
| 理论功耗/温升 | 分流 62.5 mW；均衡电阻 59.92℃（一阶） | VERIFIED（估算） |

### 2.8 三项目联合仿真与系统运行

| 编号 | 指标 | 数值 | 单位 | 验证 |
|---|---|---|---|---|
| S01 | 联合 SPICE 输出电压均值 | 4.996228（报告 4.996827） | V | VERIFIED |
| S02 | 输出纹波 | 28.978 | mVpp | VERIFIED |
| S03 | 电池端→负载效率（能量比） | 93.686（算术平均口径 93.827） | % | VERIFIED |
| S04 | 电池负载压降 / 电压电流相关性 | 0.2327 / −0.99999988 | V / — | VERIFIED |
| S05 | 系统能量边界残差 | 0.00283 | % | VERIFIED / PASS |
| L01 | 16 工况电池供电运行时间 | 0.326–6.588 | h | VERIFIED / **LIMITED** |
| L02 | SOH 90%/80% 供电时间变化 | −10.9% / −21.6% | — | VERIFIED / LIMITED |
| L03 | Buck 有效功率映射 | 4 组 / 17/24 点收敛 | — | VERIFIED / PARTIAL |
| L04 | 功率映射最低效率 | 92.770 | % | VERIFIED |
| L05 | TestLab 判定一致性 | 4/4 | 项 | VERIFIED / PASS |

L01/L02 的所有工况均终止于“电池模型限值”或“已验证输入域边界”，没有到达保护切断，因此运行时间不能当作完整续航；L03 的 7 个未收敛点已被拒绝，没有外推。

**系统运行补充指标**：

| 指标 | 实际值 | 状态 |
|---|---|---|
| 电池输入电压变化范围 | 9.0–12.6 V（功率映射有效域） | VERIFIED |
| Buck 有效输入范围 | 0.5 A: 9.0–12.6 V；1.0 A: 9.6–12.6 V；1.5/2.0 A: 9.6–12.0 V | VERIFIED |
| 负载阶跃最大偏差 / 建立时间 | 14.97 mV / 2.0 µs | VERIFIED / PASS |
| 保护关断后输出维持 | 460.1 µs | VERIFIED |
| 保护/转换器/负载损耗（8.4–12 ms 能量窗口） | 0.190 mJ / 2.424 mJ / 输出 35.946 mJ | VERIFIED |
| 负载获得能量（SOH100，1.5 A） | 7.375 Wh | VERIFIED |
| 电芯不一致性导致模型限值 | 4 个工况 BATTERY_MODEL_LIMIT | VERIFIED / LIMITED |
| 容量下降/内阻增长对供电时间 | −10.9% / −21.6% | VERIFIED / LIMITED |
| 系统测试工况 | 放电 16、老化 3、功率映射 24 点、TestLab 4 | VERIFIED |
| PASS 计数 | 保护 10 + TestLab 4 + 负载阶跃 1 + 联合 SPICE 1 + 能量 1 = 17 | VERIFIED |
| FAIL / ERROR | 0（阶段 9 运行层） | VERIFIED |
| LIMITED | 放电 16 + 老化 3 = 19 | VERIFIED |
| NOT_VERIFIED | CSV 正式 5 项（P04、C06、C07、C08、H05）；正文另有 A16、B04B | 见第五节 |

---

## 三、仿真、软件测试与工程验证的实际数量

| 类别 | 数量 | 说明 |
|---|---|---|
| 全量 pytest | 550 passed | 2026-11-26 |
| 第二阶段真实 SPICE 求解 | 6 | 模型对照 |
| 第四阶段真实 SPICE 求解 | 68 | 分压/差分/电流/RC/温度/容差 |
| 第五阶段真实 SPICE 求解 | 12 | 保护/均衡/比较器 |
| 第六阶段真实 SPICE 求解 | 12 | 充电工况 |
| 第七阶段真实 SPICE 求解 | 2 | 电池模型接口 |
| 第九阶段功率映射点 | 24（17 收敛 / 7 拒绝） | PowerLab 开关级 |
| 第九阶段故障注入 | 10/10 通过 | 行为状态机 |
| 第九阶段长期放电工况 | 16 | 均 LIMITED |
| 第九阶段 TestLab 判定 | 4/4 一致 | 只读调用真实 judge |
| 联合 SPICE 能量窗口 | 8.4–12 ms，25 ns 步长 | 单次标称工况 |

---

## 四、未通过及尚未验证项（必须保留）

| 项 | 状态 | 原因 |
|---|---|---|
| FUDS 80% 空电区最大误差 375.836 mV | VERIFIED / FAIL | 4 A、SOC 1.1–1.5% 时模型失效 |
| 二阶 RC 慢时间常数 tau2 | BOUND_LIMITED | 触 100 s 下界，弱可辨识 |
| 电压/电流最坏误差预算 30.887 mV / 37.736 mA | RISK | 超过 10 mV / 20 mA 目标 |
| LLC 谐振频率 11.07 kHz | FAIL | 低于 12–17 kHz 目标 |
| KiCad 原理图/PCB/ERC/DRC/Gerber/STEP | NOT_VERIFIED | 本机未安装 KiCad |
| 真实电池老化 / 内阻增长 | NOT_VERIFIED | 仅 1 次完整循环 |
| 保护物理切断时间（2.5 ns） | ARTIFACT | 行为源钳位，早于栅极指令 |
| 软启动 / PI / 抗积分饱和前后对照 | NOT_VERIFIED | 未保留同条件“前”波形 |
| 长期放电完整续航 | LIMITED | 全部终止于模型/域边界 |
| 真实硬件实测（整机效率、温升、EMI） | NOT_VERIFIED | 未制板、未采购 |

---

## 五、使用边界

1. 所有 SPICE 结果均为仿真，不是硬件实测；所用 MOSFET/二极管为教学级或简化模型。
2. CALCE 数据为第三方公开实验，不是本人采集。
3. 阈值 4.25/2.80/1.50/4.00/8.00 V、65℃ 为工程设计值，不是 BQ76922 寄存器值。
4. SOC 参考由电流积分推导，不是实验室直接测量的真实 SOC。
5. 容量衰减/内阻增长是健康状态研究结果，不是本项目优化了真实电池老化。
6. 均衡 91.95% 为 ECM 长时仿真 + 单次 SPICE 支路校核，不等于完整 3S 硬件均衡实测。
