# BatteryLab 真实量化工程成果总表（v2）

- 行数：100（v1 76 + 新增 24）
- 已删除 v1 中 P03/P04/P04B/P05 四条基于行为源钳位的无效保护指标，改用真实 MOSFET 结果。
- 所有数值均来自 SPICE、公开数据重放或解析计算；未做硬件实测。

| 成果编号 | 研发模块 | 指标名称 | 优化前 | 优化后 | 单位 | 改善比例 | 验证状态 | 验收状态 |
|---|---|---|---|---|---|---|---|---|
| M01 | 第二阶段/第三阶段 | Rint 模型独立验证 RMSE（FUDS 50/80 平均） |  | 26.705 | mV |  | VERIFIED | PASS |
| M02 | 第二阶段/第三阶段 | 一阶 RC 模型独立验证 RMSE（FUDS 50/80 平均） | 26.705 | 22.385 | mV |  | VERIFIED | PASS |
| M03 | 第二阶段/第三阶段 | 二阶 RC 模型独立验证 RMSE（FUDS 50/80 平均） | 22.385 | 22.175 | mV |  | VERIFIED | PASS |
| M14 | 第三阶段 | US06/BJDST 四工况一阶 RC RMSE 范围 |  | 40.652–53.599 | mV |  | VERIFIED | 范围 |
| M04 | 第三阶段 | Rint→一阶 RC 独立验证误差降低 | 26.705 | 22.385 | mV | 16.18% | VERIFIED | PASS |
| M05 | 第三阶段 | 一阶→二阶 RC 独立验证误差降低 | 22.385 | 22.175 | mV | 0.93% | VERIFIED | PASS |
| M06 | 第三阶段 | FUDS 独立验证最大瞬时误差 |  | 375.836 | mV |  | VERIFIED | FAIL |
| M07 | 第三阶段 | 欧姆内阻 R0（一阶 RC 冻结值） |  | 77.068 | mΩ |  | VERIFIED | IDENTIFIED |
| M08 | 第三阶段 | 极化 R1 / C1 / tau1 |  | 22.845 mΩ / 788.6 F / 18.02 s | mΩ / F / s |  | VERIFIED | IDENTIFIED |
| M09 | 第三阶段 | 极化 R2 / C2 / tau2 |  | 7.377 mΩ / 13555.6 F / 100.0 s | mΩ / F / s |  | VERIFIED | BOUND_LIMITED |
| M10 | 第三阶段 | OCV 实测点 → 201 点查表 |  | 147659 → 201 | 点 |  | VERIFIED | PASS |
| M11 | 第三阶段 | 充放电 OCV 迟滞（最大） |  | 129.0 | mV |  | VERIFIED | 记录 |
| M12 | 第三阶段 | 跨样品 OCV 最大差（3 只电芯） |  | 23.234 | mV |  | VERIFIED | 记录 |
| M13 | 第三阶段 | 线性 vs PCHIP 插值最大差 |  | 11.610 | mV |  | VERIFIED | 记录 |
| A01 | 第四阶段 | 单体电压采集最大误差（1000 组容差，两点校准后） | 23.657 | 3.226 | mV | 86.36% | VERIFIED | PASS（统计） |
| A02 | 第四阶段 | 单体电压采集 RMSE（校准前→后） | 7.5848 | 0.8730 | mV | 88.49% | VERIFIED | PASS（统计） |
| A03 | 第四阶段 | 电流采集最大误差（校准后） | 24.146 | 3.004 | mA | 87.56% | VERIFIED | PASS（统计） |
| A04 | 第四阶段 | 电流采集 RMSE（校准前→后） | 6.5249 | 0.8396 | mA | 87.13% | VERIFIED | PASS（统计） |
| A05 | 第四阶段 | 电流零点失调（仅零点校准） |  | 20.166 | mA |  | VERIFIED | 记录 |
| A06 | 第四阶段 | NTC 温度误差（校准后） | 0.1596 | 0.0199 | degC | 87.51% | VERIFIED | PASS |
| A07 | 第四阶段 | 输入 RC 滤波截止频率（SPICE vs 理论） | 7696.08 | 7695.23 | Hz |  | VERIFIED | PASS |
| A08 | 第四阶段 | 100 kHz 干扰衰减 |  | -22.300 | dB |  | VERIFIED | PASS |
| A09 | 第四阶段 | RC 阶跃上升时间（10–90%） | 45.434 | 45.427 | µs |  | VERIFIED | PASS |
| A10 | 第四阶段 | ADC 分辨率与量化步长 |  | 12 bit / 0.805664 mV | bit / mV |  | VERIFIED | PASS |
| A11 | 第四阶段 | 双向电流采集跨导 |  | 0.500000063 | V/A |  | VERIFIED | PASS |
| A12 | 第四阶段 | 差分放大器增益与 CMRR |  | 0.49999925 / 198.68 dB | V/V / dB |  | VERIFIED | PASS |
| A13 | 第四阶段 | 误差预算最坏情况（电压/电流） |  | 30.887 mV / 37.736 mA | mV / mA |  | VERIFIED | RISK |
| S01 | 第九阶段 | 电池供电 Buck 输出电压均值 |  | 4.996228 | V |  | VERIFIED | PASS |
| S02 | 第九阶段 | 输出电压纹波 |  | 28.978 | mVpp |  | VERIFIED | PASS |
| S03 | 第九阶段 | 电池端→负载效率（能量比） |  | 93.686 | % |  | VERIFIED | 记录 |
| S04 | 第九阶段 | 电池负载压降与相关性 |  | 0.2327 V / -0.99999988 | V / - |  | VERIFIED | PASS |
| S05 | 第九阶段 | 系统能量边界残差 |  | 0.00283 | % |  | VERIFIED | PASS |
| P01 | 第五阶段 | 保护阈值组（OV/UV/充电OC/放电OC/短路/过温） |  | 4.25/2.80/1.50/4.00/8.00 V,A,A,A,A,65℃ | V/A/℃ |  | VERIFIED | PASS |
| P02 | 第五阶段 | 故障工况通过数（状态机+故障注入） |  | 10/10 | 个 |  | VERIFIED | PASS |
| P06 | 第五阶段 | 保护后输出维持时间 |  | 460.1 | µs |  | VERIFIED | PASS |
| P07 | 第五阶段 | 背靠背 MOSFET 1 A 导通压降/单管 Rds(on) |  | 37.584 mV / 18.666 mΩ | mV / mΩ |  | VERIFIED | PASS |
| P08 | 第五阶段 | 双向阻断残余电流（双管关断，12.6 V 反压） |  | 1.00 | nA |  | VERIFIED | PASS |
| P09 | 第五阶段 | 比较器跳闸/迟滞误差 |  | 46 µV / 0.31 mV | µV / mV |  | VERIFIED | PASS |
| P10 | 第五阶段 | 保护确认延时误差 |  | 0.074 | % |  | VERIFIED | PASS |
| P11 | 第五阶段 | 综合验收检查通过数 |  | 41/41 | 项 |  | VERIFIED | PASS |
| B06 | 第五阶段 | 被动均衡前后 3S 单体 SOC 最大差异 | 11.818 | 0.952 | pp | 91.95% | VERIFIED | PASS |
| B01 | 第五阶段 | 被动均衡前后单体最大压差 | 130.000 | 10.470 | mV | 91.95% | VERIFIED | PASS |
| B02 | 第五阶段 | 无均衡同条件对照（12 h） | 130.000 | 130.000 | mV |  | VERIFIED | 对照 |
| B03 | 第五阶段 | 均衡支路电流/电阻功耗 |  | 41.783 mA / 174.65 mW | mA / mW |  | VERIFIED | PASS |
| B04 | 第五阶段 | 均衡累计耗散能量 |  | 1.3393 | Wh |  | VERIFIED | 记录 |
| B05 | 第七阶段 | 电池组 SOC 估计误差（忽略均衡→计入均衡） | 1.970 | 0.000 | pp |  | VERIFIED | PASS |
| C01 | 第六阶段 | 恒流稳态电流误差 |  | 0.00109 | A |  | VERIFIED | PASS |
| C02 | 第六阶段 | 恒压稳态电压误差 |  | 0.01350 | V |  | VERIFIED | PASS |
| C03 | 第六阶段 | CC→CV 切换电压过冲 |  | 2.07 | mV |  | VERIFIED | PASS |
| C04 | 第六阶段 | 功率级效率 |  | 98.01 | % |  | VERIFIED | PASS |
| C05 | 第六阶段 | 电压环相位裕度 |  | 107.22 | deg |  | VERIFIED | PASS |
| C06 | 第六阶段 | 软启动前后启动过冲 | NOT_VERIFIED | 8.34 | % |  | NOT_VERIFIED | PASS |
| C07 | 第六阶段 | PI 参数优化前后动态性能 | NOT_VERIFIED | NOT_VERIFIED | - |  | NOT_VERIFIED | NOT_VERIFIED |
| C08 | 第六阶段 | 抗积分饱和前后恢复时间 | NOT_VERIFIED | NOT_VERIFIED | ms |  | NOT_VERIFIED | NOT_VERIFIED |
| E01 | 第七阶段 | ECM 观测器 SOC RMSE（4 个独立动态工况平均） |  | 1.8247 | pp |  | VERIFIED | PASS |
| E02 | 第七阶段 | 端电压查表 → ECM 观测器 SOC RMSE 降低 | 12.5433 | 1.8247 | pp | 85.45% | VERIFIED | PASS |
| E03 | 第七阶段 | SOC 估计最大误差 |  | 3.087 | pp |  | VERIFIED | PASS |
| E04 | 第七阶段 | 有效覆盖率 |  | 1.0000 | - |  | VERIFIED | PASS |
| E05 | 第七阶段 | 静置 OCV 校正前后 SOC 终值误差（合成夹具） | -5.000 | -0.0189 | pp |  | VERIFIED | PASS |
| E06 | 第七阶段 | 初始 SOC 偏差收敛时间（+20 pp） |  | 479.6 | s |  | VERIFIED | PASS |
| E07 | 第七阶段 | 容量 SOH（真实数据） |  | 1 次完整循环，100% | % |  | VERIFIED | NOT_VERIFIED（老化） |
| E08 | 第七阶段 | 合成 100 循环容量保持率 |  | 90.1 | % |  | VERIFIED（合成） | 记录 |
| E09 | 第七阶段 | 真实表观 DCIR |  | 0.073274 | Ω |  | VERIFIED | 记录 |
| H01 | 第八阶段 | BMS 引脚映射完整度 |  | 33 行（32 pin + PAD） | 行 |  | VERIFIED | PASS |
| H02 | 第八阶段 | 充电器引脚映射完整度 |  | 25 行（24 pin + PAD） | 行 |  | VERIFIED | PASS |
| H03 | 第八阶段 | 关键网络规则 / 器件库 / MOSFET 候选 |  | 18 / 17 / 4 | 条 |  | VERIFIED | 记录 |
| H04 | 第八阶段 | BOM 完整性 |  | 51 行，issues=0 | 行 |  | VERIFIED | PASS |
| H05 | 第八阶段 | ERC / DRC / Gerber / 钻孔 / STEP |  | 全部 BLOCKED | - |  | NOT_VERIFIED | BLOCKED |
| H06 | 第八阶段 | LLC 谐振/LC 谐振目标 |  | 11.07 kHz（目标 12–17 kHz） | kHz |  | VERIFIED | FAIL |
| H07 | 第八阶段 | 分流电阻功耗/充电设定/电感纹波 |  | 62.5 mW / 1.0061 A / 0.299 A | mW / A / A |  | VERIFIED | PASS |
| H08 | 第八阶段 | 降额检查 / 设计评审 |  | 13 项 / 3 份评审 CSV + FMEA + 验证计划 | 项 |  | VERIFIED | 记录 |
| L01 | 第九阶段 | 电池供电运行时间（16 工况） |  | 0.326–6.588 | h |  | VERIFIED | LIMITED |
| L02 | 第九阶段 | SOH 90%/80% 供电时间变化 | 0.990 h (SOH100) | 0.882 h / 0.776 h | h |  | VERIFIED | LIMITED |
| L03 | 第九阶段 | Buck 有效功率映射 |  | 4 组负载 / 17/24 点收敛 | 组 |  | VERIFIED | PARTIAL |
| L04 | 第九阶段 | 功率映射最低效率 |  | 92.770 | % |  | VERIFIED | 记录 |
| L05 | 第九阶段 | TestLab 判定一致性 |  | 4/4 | 项 |  | VERIFIED | PASS |
| V01 | 第四阶段 | AFE 电压最坏情况预算（线性叠加） | 30.887 | 3.837 | mV | 87.58% | VERIFIED | PASS（设计） |
| V02 | 第四阶段 | AFE 电流最坏情况预算（线性叠加） | 37.736 | 6.666 | mA | 82.33% | VERIFIED | PASS（设计） |
| V03 | 第四阶段 | AFE 电压统计 RMSE（两点校准后，同种子） | 0.873 | 0.875 | mV | -0.23% | VERIFIED | 记录 |
| V04 | 第四阶段 | AFE 电流统计 RMSE（两点校准后，同种子） | 0.8396 | 0.8408 | mA | -0.14% | VERIFIED | 记录 |
| V05 | 第五阶段 | 真实 MOSFET 故障→电池电流抑制（独立） |  | 0.871 | µs |  | VERIFIED | PASS |
| V06 | 第五阶段 | 真实 MOSFET 栅极下降时间（90%→10%） |  | 44.6 | ns |  | VERIFIED | PASS |
| V07 | 第五阶段 | 联合系统故障→电流抑制（电池+Buck+负载） |  | 119.8 | µs |  | VERIFIED | RISK |
| V08 | 第五阶段 | 保护级真实导通电阻（双管串联） |  | 30.67 | mΩ |  | VERIFIED | PASS |
| V09 | 第五阶段 | 历史 2.5 ns 保护伪迹 |  | 拒绝 | - |  | VERIFIED | PASS（真实性） |
| V10 | 第六阶段 | 软启动峰值充电电流（0→5 ms） | 1.0897 | 1.0562 | A | 3.07% | VERIFIED | PASS |
| V11 | 第六阶段 | 软启动启动能量（0→5 ms） | 0.2492 | 0.1368 | J | 45.10% | VERIFIED | PASS |
| V12 | 第六阶段 | 软启动 CC 稳态误差（0→5 ms） | 0.357 | 20.61 | mA | 变差 5673% | VERIFIED | FAIL（5 ms） |
| V13 | 第六阶段 | 抗积分饱和 CV 过冲（none→conditional） | 3.257 | 2.068 | mV | 36.51% | VERIFIED | PASS |
| V14 | 第六阶段 | back-calculation 沿用旧 KAW 的 CV 过冲 | 3.257 | 654.6 | mV | 变差 20000% | VERIFIED | FAIL |
| V15 | 第六阶段 | PI 带宽分离比（目标 ≥5×） |  | 最大 1.86× | - | 0/25 通过 | VERIFIED | FAIL |
| V16 | 第三阶段 | 低 SOC 0–5% 端电压 RMSE（bjdst_80 二阶） |  | 157.7 | mV |  | VERIFIED | FAIL |
| V17 | 第九阶段/系统 | 系统效率（基准→优化LC+控制器） | 94.158 | 95.206 | % | +1.048 pp / +1.11% | VERIFIED | PASS |
| V18 | 第九阶段/系统 | 系统输出纹波（基准→优化） | 24.54 | 21.0 | mV | 14.43% | VERIFIED | PASS |
| V19 | 第九阶段/系统 | 负载阶跃最大偏差（2.5→1.25 Ω） | 843.0 | 574.97 | mV | 31.79% | VERIFIED | PASS |
| V20 | 第九阶段/系统 | 负载阶跃恢复时间（基准→优化） | 1615.0 | 1717.0 | µs | 变差 6.32% | VERIFIED | 记录 |
| V21 | 第三阶段/第九阶段 | 模型有效域（7 个动态工况） |  | 7/7 LIMITED | 项 |  | VERIFIED | LIMITED |
| V22 | 第八阶段/EDA | EDA 交付状态 |  | PASS 10 / BLOCKED 9 / FAIL 1 | 项 |  | BLOCKED | BLOCKED |
| V23 | 全项目 | 自动化测试实际通过数 |  | 550 | 项 |  | VERIFIED | PASS |
| V24 | 第七阶段 | SOC 方法误差（raw OCV / ECM observer / 安时积分） |  | 9.30–9.70 / 1.48–1.81 / ~0 | pp |  | VERIFIED | LIMITED |
