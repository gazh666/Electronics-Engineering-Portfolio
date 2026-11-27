# BatteryLab 研发岗成果证据卡（v3）

> 每张卡包含：结论 / 方法 / 关键数值 / 证据路径 / 局限。面试可据此复现，不得超出"局限"外推。

---

## 卡 A｜AFE 采集链路：理论最坏预算 + 统计 RMSE（分离报告）

- **结论**：候选 D 匹配网络将电压最坏预算 30.887→3.837 mV（−87.58%）、电流 37.736→6.666 mA（−82.33%）；同种子统计 RMSE 电压 0.8730→0.8750 mV、电流 0.8396→0.8408 mA（略变差）。
- **方法**：解析误差预算（线性叠加）+ 真实 ngspice 角点 + 1000 组蒙特卡洛（seed 42）。
- **证据**：`results/hardening/afe/run_20261126_185349_ef0845/optimized_budget.json`、`monte_carlo_before.csv`；源码 `hardening/afe_worst_case.py`、`analysis/tolerance_analysis.py`。
- **局限**：3.837mV/6.666mA 是**理论最坏预算**，非实测；候选 D 未打样；统计 RMSE 与预算必须分开引用。

## 卡 B｜MOSFET 保护时序（真实 ngspice）

- **结论**：独立功率通路故障→电流抑制 **0.871 µs**；联合系统 **119.8 µs（RISK）**；栅极下降 **44.6 ns**（受 20ns 分辨率限制）。
- **方法**：真实 ngspice Level-1 MOSFET 网表；独立/联合两套工况分别仿真。
- **证据**：`results/hardening/protection/run_20261126_185355_962fc1/protection_summary.json`、`event_sequence.csv`；源码 `hardening/protection_physical_validation.py`。
- **局限**：0.871µs 仅为独立功率通路，不是整机 BMS 保护时间；联合系统受过流爬升主导；2.5ns 伪迹已永久剔除。

## 卡 C｜系统负载阶跃与效率（真实开关级联合仿真）

- **结论**：过载阶跃（2.5→1.25Ω@5V≈2→4A）偏差 843.0→574.97 mV（−31.79%）；效率 94.16→95.21%；纹波 24.54→21.0 mV；恢复时间 1615→1717 µs。
- **方法**：开关级联合仿真（222k 采样点），基准/优化 LC + 调参控制器三组对照。
- **证据**：`results/hardening/system/run_20261126_185616_e47de7/system_candidate_comparison.csv`；源码 `hardening/system_candidate_validation.py`。
- **局限**：574.97mV **仍超 300mV 限值**且**超出 5V/2A 额定**（属过载研究）；恢复时间变差；不可判 PASS。

## 卡 D｜控制系统失败（如实保留）

- **结论**：PI 带宽分离最大 1.86×（目标 5×，25 组全未过）；5ms 软启动 CC 稳态误差 20.61 mA；back-calculation 旧 KAW 过冲 654.6 mV。
- **证据**：`results/hardening/charging/run_20261126_185404_348b91/summary.json`；源码 `hardening/soft_start_validation.py`、`hardening/pi_grid_search.py`、`hardening/antiwindup_comparison.py`。
- **局限**：均为真实失败，未消除；不得包装为达标。

## 卡 E｜电池模型有效域（LIMITED）

- **结论**：SOC 辨识窗口 0.011–0.507，窗口外为外推；温度**仅 25℃**；二阶 RC 弱可辨识；长期 SOH 数据不足；续航 LIMITED。
- **证据**：`results/hardening/domain/run_20261126_185653_8f3e08/domain_summary.json`；源码 `hardening/domain_audit.py`。
- **局限**：禁止宣称全 SOC/全温域有效或续航已验证。

## 卡 F｜EDA 硬件设计（真实 KiCad 10.0.8，PARTIAL）

- **结论**：2 套可编辑原理图（BMS/充电器），U1/U2 引脚审计 **0 失败**；ERC **0 错误**（59/50 告警）；2 块 **4 层** PCB 放置完成、GND 已铺铜（F.Cu/B.Cu）、原理图-PCB 一致性 **0 项**；真实导出 Gerber/钻孔/STEP/PDF。PCB **非 GND 布线未完成**（65/51 未连接），BMS 有 4 个 QFN 细间距 DRC。
- **方法**：`winget KiCad.KiCad 10.0.8`；脚本生成 `.kicad_sch/.kicad_pcb`；`kicad-cli` 真实 ERC/DRC/导出；`pcbnew` 赋网。
- **证据**：`hardware/eda/BatteryLab_BMS_V1/release/`、`.../BatteryLab_Charger_V1/release/`（各 38 文件 + `release_manifest.json` sha256）；`results/eda/schematic_check_20261127/`。
- **局限**：PCB 未布线、板框 102×122mm（>70×50 目标）、MOSFET SON 引脚映射需按数据手册复核；**不可投产**。

## 卡 G｜软件工程质量

- **结论**：全量 pytest **594 passed**（历史基线 550 passed 单独存档）。
- **证据**：`results/eda/pytest_v3_20261127.log`、`results/stage10/final_acceptance_20261126_185821/acceptance.json`、`results/_pytest_stage9_rerun.log`。
- **局限**：测试数量不代表电气性能。
