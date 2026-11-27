# 05 CALCE 真实实验数据分析

## 1. 数据提供机构

CALCE（Center for Advanced Life Cycle Engineering），University of Maryland。
官方入口：https://calce.umd.edu/battery-data
实际文件下载地址：`https://web.calce.umd.edu/batteries/data/`

引用要求（官方页面）：引用需包含机构、数据集标题、访问日期与 URL；本项目按此记录清单字段 `citation`。

## 2. 电芯型号与额定参数

| 项目 | 官方数值 |
| --- | --- |
| 型号 | INR 18650-20R |
| 额定容量 | 2000 mAh |
| 化学体系 | LiNiMnCo / Graphite |
| 重量（不含安全电路） | 45 g |
| 直径 | 18.33 mm ± 0.07 mm |
| 长度 | 64.85 mm ± 0.15 mm |

以上来自官方页面正文，非本项目测量。

## 3. 实际下载清单

共 **9 个文件**、**50,034,565 字节（47.72 MB）**，均在 500 MB 预算内。

| dataset_id | 文件 | 字节 | 测试类型 | 样品 |
| --- | --- | --- | --- | --- |
| calce_inr18650_20r_sp1_initial_capacity_20151016 | SP1_Initial capacity_10_16_2015.zip | 3,370,015 | initial_capacity | SP1 |
| calce_inr18650_20r_sp2_initial_capacity_20151016 | SP2_Initial_capacity_10_16_2015.zip | 3,146,319 | initial_capacity | SP2 |
| calce_inr18650_20r_sp1_25c_low_current_ocv_20151105 | SP1_25C_LC_OCV_11_5_2015.zip | 3,015,812 | low_current_ocv | SP1 |
| calce_inr18650_20r_sp3_25c_low_current_ocv_20151116 | SP3_25C_LC_OCV_11_16_2015.zip | 11,486,330 | low_current_ocv | SP3 |
| calce_inr18650_20r_sp3_25c_incremental_ocv_20151202 | SP3_25C_IC_OCV_12_2_2015.zip | 16,022,212 | incremental_ocv | SP3 |
| calce_inr18650_20r_sp2_25c_dst | SP2_25C_DST.zip | 3,189,603 | dst | SP2 |
| calce_inr18650_20r_sp2_25c_fuds | SP2_25C_FUDS.zip | 3,426,587 | fuds | SP2 |
| calce_inr18650_20r_sp2_25c_us06 | SP2_25C_US06.zip | 3,372,078 | us06 | SP2 |
| calce_inr18650_20r_sp2_25c_bjdst | SP2_25C_BJDST.zip | 3,005,609 | bjdst | SP2 |

清单文件：`data/manifests/dataset_manifest.json`、`data/manifests/dataset_catalog.csv`（含 SHA256）。

## 4. 实测温度

- 文件名与官方说明标注 25 ℃ 的数据集按 `temperature_c = 25.0` 记录。
- Arbin 导出表中没有逐点温度列，只有 SP1 低电流 OCV 的简化表有 `Temperature` 列，首行 23.0 ℃，
  其余为空。
- 因此**不能声称每个时刻的电芯表面温度均为 25 ℃**，只能记录为实验环境标称温度。

## 5. 实际文件结构

两类结构，均由本项目的加载器自动识别：

1. Arbin 单表：`Data_Point, Test_Time(s), Date_Time, Step_Time(s), Step_Index, Cycle_Index,
   Current(A), Voltage(V), Charge_Capacity(Ah), Discharge_Capacity(Ah), Charge_Energy(Wh),
   Discharge_Energy(Wh), dV/dt(V/s), Internal_Resistance(Ohm), ...`
2. 简化 OCV 表：`Duration (sec), Pgm step, mV, mA, Temperature`

`Info` 工作表是测试报告元数据，解析时跳过；`Channel_*` 工作表为真实数据表。

## 6. 采样时间

| 数据集 | 采样间隔中位数 |
| --- | --- |
| SP1 初始容量 | 1.015536 s |
| SP2 初始容量 | 1.015533 s |
| SP1 低电流 OCV | 1.000000 s |
| SP3 低电流 OCV | 1.015588 s |
| SP3 增量 OCV | 1.015525 s |
| SP2 DST | 1.015585 s |
| SP2 FUDS | 1.015584 s |
| SP2 US06 | 1.009218 s |
| SP2 BJDST | 1.002946 s |

时间轴按文件保留原始 `Test_Time(s)`，跨文件不排序、不拼接时间。

## 7. 电流符号

实际判定结果：**全部 9 个数据集原始约定为 `charge_positive`（充电为正）**。

判定依据（程序自动）：放电容量字段增长时原始电流为负，充电容量字段增长时原始电流为正。
例：DST 50% SOC 文件起始 1 A 脉冲期间 `Charge_Capacity(Ah)` 每 10 s 增加 0.00278 Ah
（1 A × 10 s / 3600 = 0.00278 Ah），电流记录为 +0.9998 A。

统一转换为内部约定（放电为正）后，`current_a = -原始电流`。
未对原始文件做任何修改。

## 8. 解析结果总览

运行：`results/calce/run_calce_20261126_120012_8cefbd`

| 数据集 | 行数 | 电压范围 (V) | 电流范围 (A) | 电流积分放电容量 (Ah) | 质量 |
| --- | --- | --- | --- | --- | --- |
| SP1 初始容量 | 27,602 | 2.499921 – 4.200097 | −1.000313 – 1.000525 | 2.009335 | PASS |
| SP2 初始容量 | 26,322 | 2.499974 – 4.200292 | −1.000544 – 1.000785 | 2.028252 | PASS |
| SP1 低电流 OCV | 169,412 | 2.496 – 4.205 | −0.107 – 0.135 | — | WARN |
| SP3 低电流 OCV | 90,915 | 2.499891 – 4.204940 | −0.999840 – 0.100632 | — | WARN |
| SP3 增量 OCV | 165,696 | 2.499963 – 4.273285 | −1.000253 – 1.000581 | — | WARN |
| SP2 DST | 22,062 | 2.403369 – 4.200139 | −2.004563 – 4.001960 | 2.160675 | PASS |
| SP2 FUDS | 22,989 | 2.496777 – 4.200139 | −2.142187 – 4.000515 | 2.324972 | PASS |
| SP2 US06 | 20,219 | 2.498234 – 4.200139 | −1.000195 – 3.996541 | 2.137705 | PASS |
| SP2 BJDST | 20,822 | 2.499367 – 4.200139 | −1.000195 – 1.667404 | 2.097799 | PASS |

合计 **566,039 个采样点**；质量检查 6 PASS / 3 WARN / 0 FAIL。

WARN 原因：OCV 数据集中存在 1–2 行完全重复的时间/电压/电流记录（SP1 LC 2 行、SP3 LC 1 行、
SP3 IC 2 行），保留原始数据并在质量报告中标注。

动态工况电流积分容量（2.10–2.32 Ah）高于初始容量（2.01–2.03 Ah），原因是动态工况文件包含
充电段与不同起始 SOC，不能直接当作额定容量。

## 9. OCV 实验

- 低电流 OCV：官方用 C/20、C/25 小电流连续充放电，以充放电平均端电压近似 OCV。
- 增量 OCV：小电流脉冲 + 静置，逐点逼近平衡电位，SP3 文件包含 3 个 Channel 工作表。
- 本阶段只解析与绘图，**未完成 OCV-SOC 辨识**，不能给出 OCV 曲线拟合结论。

## 10. DST 与 FUDS

- DST（Dynamic Stress Test）：电流峰值 4.00196 A，最低电压 2.403369 V（触及 2.5 V 以下，
  说明存在深度放电段）。
- FUDS（Federal Urban Driving Schedule）：电流范围 −2.142187 – 4.000515 A。
- 两者均为动态工况，适合第二阶段做等效电路参数辨识与模型验证。

## 11. 数据清洗

本阶段规则：**保留全部原始采样点**，只增加派生列（内部符号电流、阶段标签），
`cleaning_record` 记录 raw/processed/removed 点数（当前 removed = 0）。
重复行、越界值只报告，不静默删除；电流脉冲、静置、反向电流、截止事件全部保留。

## 12. 后续数据划分建议

- 参数辨识：DST（50% SOC 文件）+ 低电流 OCV。
- 验证：FUDS、US06、BJDST（不同动态工况）。
- 注意 SP1/SP2/SP3 是不同样品，不可混为同一电芯的连续实验。

## 13. 实际图表路径

`results/calce/run_calce_20261126_120012_8cefbd/plots/`

- `01_initial_capacity_voltage_current.png`、`02_initial_capacity_discharge_capacity.png`、
  `03_initial_capacity_power.png`、`04_sampling_interval_histogram.png`、`05_stage_segments.png`
- `06_dynamic_current.png`、`07_dynamic_voltage.png`（DST/FUDS/US06/BJDST 各自目录内同名文件按数据集 ID 区分）
- `08_low_current_ocv_voltage.png`、`08_low_current_ocv_stage_segments.png`
- `09_incremental_ocv_voltage.png`、`09_incremental_ocv_stage_segments.png`

## 14. 核心代码

- `datasets/downloader.py`：官方链接、预算控制、SHA256。
- `datasets/calce_loader.py`：两种表结构识别、符号判定、统一字段。
- `datasets/data_quality.py`：缺失/非有限/重复/时间重置/越界检查。
- `scripts/calce_data_demo.py`：解析、质量、绘图、清单回填。

## 15. 已知局限

- 未获取 0 ℃ 与 45 ℃ 数据（本阶段只做 25 ℃ 优先集）。
- 未做参数辨识与 OCV-SOC 拟合。
- 温度不是逐点实测。
- 官方页面未提供电芯出厂批次与循环历史。

---

## 面试题（附参考答案要点）

**Q1：为什么解析前必须确认电流符号？**
A：不同设备约定不同（充电为正或放电为正），符号错误会让容量、能量、SOC 全部反向。

**Q2：时间重置如何处理？**
A：按文件/工步分段，保留原始时间，不全局排序，避免把不同实验段拼接成连续时间轴。

**Q3：为什么不能删除重复行？**
A：可能是设备重复记录的真实事件，删除会改变容量积分；应先报告再决定策略。

**Q4：DST 与 FUDS 的用途差异？**
A：都是动态工况；DST 为标准化应力测试，FUDS 模拟城市行驶，常用于验证模型泛化能力。

**Q5：电流积分容量为什么和额定容量不同？**
A：起始 SOC、温度、截止电压、老化与工况都影响可用容量；动态工况还包含充电段。

**Q6：为什么 25 ℃ 只能写环境温度？**
A：原始数据没有逐点温度列，环境温度不等于每个时刻的电芯表面温度。
