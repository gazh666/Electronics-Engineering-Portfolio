# BatteryLab 研发岗成果证据卡

- 审计运行：`results/resume_audit/run_20261126_175610`
- 对应指标编号见 [BatteryLab_resume_metrics.csv](file:///BatteryLab/portfolio/BatteryLab_resume_metrics.csv)
- 每张卡只写能从原始结果复算的数字；局限与“不可宣称”逐卡列出。

---

## 卡 01｜电池等效电路建模与参数辨识

- **工程问题**：3S 电池组需要可用于电路仿真的端电压模型，且要区分模型阶数与真实精度收益。
- **技术方法**：CALCE INR18650-20R 公开数据；R0 脉冲辨识 + 一阶/二阶 RC 松弛拟合；Rint/一阶/二阶三模型在 6 个独立动态工况开环验证；从 21 组残差逐点复算 MAE/RMSE/最大值。
- **实际量化成果**：
  - **FUDS 50/80 两工况平均**：Rint 独立验证 RMSE **26.705 mV**；一阶 RC **22.385 mV**；二阶 RC **22.175 mV**。
  - Rint→一阶降低 **16.18%**；一阶→二阶仅 **0.93%**（tau2 触下界）。
  - **US06/BJDST 四工况**：一阶 RC RMSE **40.652–53.599 mV**，部分工况不优于 Rint；未并入上面的 22 mV / 16.18%。
  - R0 = **77.068 mΩ**；R1/C1/tau1 = **22.845 mΩ / 788.6 F / 18.02 s**；R2/C2/tau2 = **7.377 mΩ / 13555.6 F / 100.0 s**。
  - 7 个验证数据集共 **64,407** 个动态点；OCV 147,659 点压缩为 201 点。
- **证据**：`results/dynamic_validation/run_dynamic_validation_20261126_131720_0e4677/residuals.csv.gz`；`results/identification/run_identification_20261126_131901_fb66db/identified_parameters.csv`
- **核心源码**：`validation/dynamic_validation.py`、`identification/ecm_fitter.py`
- **适用岗位**：电池系统、BMS、电源硬件（前级建模）。
- **局限**：数据为第三方公开实验；仅 25℃；FUDS 80% 空电区最大误差 375.836 mV，整体验收保留 FAIL。

---

## 卡 02｜单体电压采集链与两点校准

- **工程问题**：3S 单体电压在共模 0–12.6 V 下采集，分压电阻容差与运放失调会直接变成 mV 级误差。
- **技术方法**：电阻分压 + 四电阻差分放大 + RC 滤波 + 12 位行为 ADC；1000 组随机容差蒙特卡洛（seed 42）；增益/失调两点校准。
- **实际量化成果**：
  - 电压最大误差 **23.657 → 3.226 mV**（−86.36%）；RMSE **7.5848 → 0.8730 mV**（−88.49%）。
  - 差分增益 **0.49999925 V/V**；理想匹配 CMRR 数值下界 **133.98 dB**；1% 电阻失配时 CMRR 降至 **53.66 dB**、单体误差最大 **25.07 mV**。
  - RC 截止 **7695.23 Hz**（理论 7696.08 Hz，误差 0.011%）；100 kHz 干扰 **0.14141 → 0.01085 V RMS**（−22.301 dB）；建立时间 **95.333 µs**（理论 95.231 µs）。
  - NTC 0–60℃ 最大温度误差 **0.00085℃**（SPICE vs 理论），含 12 位 ADC 后 **0.01290℃**；自热温升因缺耗散系数标 NOT_VERIFIED。
- **证据**：`results/sensing/run_sensing_20261126_135449_d8a6d3/`；`results/sensing/run_sensing_20261126_135218_cb8cf7/summary.json`
- **核心源码**：`analysis/tolerance_analysis.py`、`circuits/differential_amplifier.py`
- **适用岗位**：模拟芯片应用、AFE、芯片验证、BMS 硬件。
- **局限**：SPICE + 行为 ADC，不是真实 ADC 芯片；最坏预算 30.887 mV 仍为 RISK，统计通过不等于最坏情况保证。

---

## 卡 03｜双向电流采集与零漂校准

- **工程问题**：充放电双向电流需要围绕中点偏置，且零点失调会随温漂累积成 SOC 漂移。
- **技术方法**：10 mΩ 分流 + 50 V/V 放大 + 1.65 V 中点偏置；3 次真实 SPICE 求解提取跨导；零点校准与两点校准分离评估；1000 组容差统计。
- **实际量化成果**：
  - 跨导 **0.50000006 V/A**（理论 0.5）；分流最大压降 **25 mV**、功耗 **62.5 mW**。
  - 电流最大误差 **24.146 → 3.004 mA**（−87.56%）；RMSE **6.5249 → 0.8396 mA**（−87.13%）。
  - 仅零点校准后最大误差 **20.166 mA**，说明增益误差仍需两点校准。
  - 12 位 ADC 在 50 V/V 下输入折算 **1.611 mA/LSB**。
- **证据**：`results/sensing/run_sensing_20261126_135555_720959/summary.json`；`results/sensing/run_sensing_20261126_135449_d8a6d3/current_sample_metrics.csv`
- **核心源码**：`circuits/current_sensing.py`、`sensing/calibration.py`
- **适用岗位**：模拟采集、BMS 硬件、电源管理芯片应用。
- **局限**：仿真跨导非芯片实测；最坏预算 37.736 mA 为 RISK；未做温漂实测。

---

## 卡 04｜MOSFET 保护、比较器与故障状态机

- **工程问题**：3S 电池组需要过压/欠压/过流/短路/过温保护，并区分“配置延时”与“实际响应”。
- **技术方法**：背靠背 N-MOSFET + 分立比较器 + RC 确认延时 + 状态机；10 类故障注入；41 项阶段验收；严格区分软件逻辑、配置延时、比较器仿真响应与栅极关断。
- **实际量化成果**：
  - 故障注入 **10/10** 通过；阶段验收 **41/41**。
  - 背靠背 1 A 压降 **37.584 mV**，单管 Rds(on) **18.666 mΩ**；双向阻断残余 **1.00 nA**。
  - 比较器跳闸误差 **46 µV**、迟滞误差 **0.31 mV**、确认延时误差 **0.074%**。
  - 故障→栅极关断指令 **10 µs**；指令→输入电压衰减 **199 µs**；输出维持 **460 µs**。
- **证据**：`results/stage9/system_protection/protection_20261126_173438_1e53b2/case_result.json`；`results/stage5_validation/run_stage5_validation_20261126_143914_3f8da9/summary.json`
- **核心源码**：`protection/state_machine.py`、`circuits/integrated_protection.py`
- **适用岗位**：BMS 硬件、功率半导体应用、芯片验证。
- **局限**：**2.5 ns“电流切断”是行为源伪迹，已标 NOT_VERIFIED**；MOSFET 为教学级模型；阈值 4.25/2.80/1.50/4.00/8.00 V、65℃ 是工程配置值，不是 BQ76922 寄存器。

---

## 卡 05｜被动均衡与同条件对照

- **工程问题**：3S 不一致电芯需要被动均衡，但静置极化恢复也会让压差缩小，必须证明改善来自均衡。
- **技术方法**：均衡电阻 + MOSFET 支路；12 h ECM 长时仿真；新增“同一初值、同一时长、仅关闭均衡许可”的对照；SOC 差由同一 ECM 状态给出。
- **实际量化成果**：
  - 单体最大压差 **130.000 → 10.470 mV**（−91.95%）；对照 **130.000 → 130.000 mV**（0%）。
  - 3S 单体 SOC 最大差异 **11.818 → 0.952 pp**（−91.95%）。
  - 均衡支路电流 **41.783 mA**、峰值功耗 **174.65 mW**、12 h 耗散 **1.3393 Wh**；电阻温升一阶估算 **59.92℃**。
- **证据**：`results/protection/run_protection_20261126_143916_7ed424/balancing_long_run.csv`；`results/resume_audit/run_20261126_175610/balancing_control.json`
- **核心源码**：`protection/balancing.py`、`circuits/balancing_circuit.py`
- **适用岗位**：BMS 硬件、电池系统。
- **局限**：ECM 长时仿真 + 单次 SPICE 支路校核，不是完整 3S 硬件均衡实测；电阻温升未做热仿真。

---

## 卡 06｜CC-CV 充电与双环稳定裕度

- **工程问题**：18 V 输入、12.15 V/1 A 充电，需要恒流/恒压平滑切换与足够相位裕度。
- **技术方法**：开关级 Buck + CC/CV 双环 PI + 软启动 + 条件积分/反计算抗饱和；SPICE 工况 + 线性化平均模型频域分析。
- **实际量化成果**：
  - 恒流稳态误差 **1.09 mA**；恒压稳态误差 **13.50 mV**；CC→CV 过冲 **2.07 mV**。
  - 功率级效率 **98.01%**；电压环相位裕度 **107.22°**。
  - 有软启动时启动过冲 **8.34%**。
- **证据**：`results/stage6/run_stage6_20261126_155147_64c696/summary.json`
- **核心源码**：`charging/cc_cv_controller.py`、`analysis/charging_loop_analysis.py`
- **适用岗位**：电源硬件、电源管理芯片应用、AE/FAE。
- **局限**：开关级 SPICE + 平均模型，不是 BQ24610 实测；**软启动/PI/抗饱和没有保留“前”的同条件波形，改善比例 NOT_VERIFIED**。

---

## 卡 07｜SOC 估计与静置校正

- **工程问题**：动态工况下安时积分会漂移，端电压查表在平台区不敏感。
- **技术方法**：安时积分、OCV 查表、ECM 状态观测器三法对比；4 个独立工况；静置 OCV 校正；初始偏差收敛实验。
- **实际量化成果**：
  - ECM 观测器 SOC RMSE **1.8247 pp**；最大误差 **3.087 pp**；覆盖率 **1.000**。
  - 端电压查表 **12.5433 pp → 1.8247 pp**（−85.45%，同 4 工况）。
  - +20 pp 初始偏差收敛 **479.6 s**。
  - 静置校正合成夹具：−5.000 → **−0.0189 pp**（25 次校正，2400 s）。
- **证据**：`results/stage7/run_stage7_20261126_162211_3590e5/soc_method_comparison.csv`；`results/soc_estimation/run_soc_estimation_20261126_161725_90c158/correction_metrics.json`
- **核心源码**：`estimation/ecm_observer.py`、`estimation/rest_correction.py`
- **适用岗位**：BMS 算法/硬件、电池系统。
- **局限**：SOC 参考由公开数据电流积分推导，不是直接实测真实 SOC；校正夹具为合成真值，真实连续动态段校正 0 次。

---

## 卡 08｜SOH、容量与内阻健康评估

- **工程问题**：需要区分“真实老化证据”与“合成老化演示”。
- **技术方法**：真实容量积分一致性检查；表观 DCIR 计算；100 循环合成容量序列；SOH 参数对系统供电时间的敏感性。
- **实际量化成果**：
  - 真实 SP2 参考容量 **2.02808 Ah**，记录值与积分值差 **0.00098%**。
  - 真实表观 DCIR **0.073274 Ω**（SOC 0.391，4.483 A，1.003 s）。
  - 合成 100 循环保持率 **90.1%**（合成）。
  - SOH 100/90/80 供电时间 **0.990 / 0.882 / 0.776 h**（−10.9% / −21.6%）。
- **证据**：`results/battery_health/run_battery_health_20261126_161753_3e607b/capacity_soh_summary.json`；`results/stage9/system_lifetime/aging_20261126_173726_efe310/case_result.json`
- **核心源码**：`health/capacity_soh.py`、`health/resistance_health.py`
- **适用岗位**：电池系统、BMS。
- **局限**：**真实老化 NOT_VERIFIED**（仅 1 次循环）；合成序列不得称为真实老化；供电时间终止于已验证输入域边界。

---

## 卡 09｜真实器件选型与硬件设计输入

- **工程问题**：把 BQ76922/BQ24610 方案落到可检查的引脚、网络、BOM 与降额。
- **技术方法**：数据手册级引脚映射；关键网络规则；器件库与 MOSFET 候选对比；BOM 完整性；降额检查；设计评审/FMEA。
- **实际量化成果**：
  - BQ76922 **33 行**（32 pin + PAD）；BQ24610 **25 行**（24 pin + PAD）。
  - 关键网络 **18 条**；器件库 **17 条**；MOSFET 候选 **4 款**。
  - BOM **51 行**，issue **0**；降额 **13 项**；评审 **3 份 CSV + FMEA + 验证计划**。
  - 分流功耗 **62.5 mW**；充电设定 **1.0061 A**；电感纹波 **0.299 A**。
- **证据**：`results/eda/run_stage8_20261126_165159_f06bd0/`
- **核心源码**：`eda_tools/pin_mapping_audit.py`、`eda_tools/design_calculations.py`
- **适用岗位**：硬件研发、AE/FAE、电源硬件。
- **局限**：**KiCad 未安装，原理图/PCB/ERC/DRC/Gerber/STEP 全部 BLOCKED**；LLC 谐振 11.07 kHz 未达 12–17 kHz 目标（FAIL）；被动件料号仍有 TBD。

---

## 卡 10｜三项目联合仿真与系统能量

- **工程问题**：电池 ECM 与真实开关级 Buck 必须双向耦合，而不是单向数据回放。
- **技术方法**：同一网表联合 SPICE（电池 ECM + PowerLab Buck + 保护 + 负载）；平均模型负载阶跃；4 组有效功率映射；能量边界残差；真实 TestLab judge 只读调用。
- **实际量化成果**：
  - 输出电压 **4.996228 V**（记录 4.996827 V）；纹波 **28.978 mVpp**。
  - 电池端→负载效率 **93.686%**（能量比；算术口径 93.827%）。
  - 电池压降 **0.2327 V**，电压-电流相关 **−0.99999988**，证明电池电压随负载真实变化。
  - 能量边界残差 **0.00283%**；功率映射 **4 组有效 / 17/24 点收敛**，最低效率 **92.770%**。
  - TestLab 判定 **4/4 一致**（judge sha256 `f8182b41…`）。
- **证据**：`results/system_spice/integrated_nominal_20261126_172452_cb19d4/waveform.csv`；`results/stage9/system_energy/energy_20261126_173741_2a5eef/case_result.json`
- **核心源码**：`circuits/system_spice_netlist.py`、`integration/testlab_bridge.py`
- **适用岗位**：电源硬件、系统仿真、AE/FAE。
- **局限**：SPICE 仿真不是硬件在环；2.5 Ω 电阻负载不能外推到恒流/恒功率；7 个未收敛映射点已拒绝，未外推。
