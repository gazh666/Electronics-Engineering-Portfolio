# BatteryLab 研发岗成果证据卡（v2）

每条包含：指标、前后值、条件、证据路径、局限。

## M02 一阶 RC 模型独立验证 RMSE（FUDS 50/80 平均）

- 优化前 → 优化后：26.705 → 22.385 mV（改善 —）
- 条件：FUDS 50/80 SOC 起点，同 M01
- 数据来源：PUBLIC_EXPERIMENT + ECM 仿真
- 原始证据：`BatteryLab\results\dynamic_validation\run_dynamic_validation_20261126_131720_0e4677\residuals.csv.gz`
- 核心源码：`validation/dynamic_validation.py`
- 状态：VERIFIED / PASS
- 局限：相对 Rint 降低 16.18%；同数据集同区间

## A01 单体电压采集最大误差（1000 组容差，两点校准后）

- 优化前 → 优化后：23.657 → 3.226 mV（改善 86.36%）
- 条件：2.5–4.25 V，1000 组随机容差，seed 42
- 数据来源：SPICE + 行为 ADC + 统计
- 原始证据：`BatteryLab\results\sensing\run_sensing_20261126_135449_d8a6d3\voltage_sample_metrics.csv`
- 核心源码：`analysis/tolerance_analysis.py`
- 状态：VERIFIED / PASS（统计）
- 局限：统计值非保证最坏情况；最坏预算 30.887 mV 为 RISK

## A02 单体电压采集 RMSE（校准前→后）

- 优化前 → 优化后：7.5848 → 0.8730 mV（改善 88.49%）
- 条件：同上
- 数据来源：SPICE + 行为 ADC + 统计
- 原始证据：`BatteryLab\results\sensing\run_sensing_20261126_135449_d8a6d3\summary.json`
- 核心源码：`analysis/tolerance_analysis.py`
- 状态：VERIFIED / PASS（统计）
- 局限：RMSE 由 summary 记录，MAE/最大值已独立复算

## V01 AFE 电压最坏情况预算（线性叠加）

- 优化前 → 优化后：30.887 → 3.837 mV（改善 87.58%）
- 条件：3S 最高单体 4.0 V、共模 9.7 V、0.1%（基线）→0.01%（候选D）匹配网络
- 数据来源：解析误差预算 + 真实 SPICE 角点
- 原始证据：`BatteryLab\results\hardening\afe\run_20261126_185349_ef0845/optimized_budget.json`
- 核心源码：`hardening/afe_worst_case.py`
- 状态：VERIFIED / PASS（设计）
- 局限：候选 D 未打样；0.01% 匹配网络为设计目标参数

## V02 AFE 电流最坏情况预算（线性叠加）

- 优化前 → 优化后：37.736 → 6.666 mA（改善 82.33%）
- 条件：±2.5 A、分流 10 mΩ、0.5%→0.05%、TCR 50→10 ppm/°C
- 数据来源：解析误差预算 + 真实 SPICE 角点
- 原始证据：`BatteryLab\results\hardening\afe\run_20261126_185349_ef0845/optimized_budget.json`
- 核心源码：`hardening/afe_worst_case.py`
- 状态：VERIFIED / PASS（设计）
- 局限：ADC 增益剩余误差按两点校准后残差建模

## V05 真实 MOSFET 故障→电池电流抑制（独立）

- 优化前 → 优化后： → 0.871 µs（改善 —）
- 条件：10 V/2 A→8 A 阶跃，阈值 4 A，20 ns 步长
- 数据来源：真实 ngspice Level-1 MOSFET 网表
- 原始证据：`BatteryLab\results\hardening\protection\run_20261126_185355_962fc1/protection_summary.json`
- 核心源码：`hardening/protection_physical_validation.py`
- 状态：VERIFIED / PASS
- 局限：教学 MOSFET 模型；command→suppression 受采样分辨率限制

## V08 保护级真实导通电阻（双管串联）

- 优化前 → 优化后： → 30.67 mΩ（改善 —）
- 条件：1.99 A 放电，VGS 10 V
- 数据来源：真实 ngspice 工作点
- 原始证据：`BatteryLab\results\hardening\protection\run_20261126_185355_962fc1/conduction_results.csv`
- 核心源码：`hardening/protection_physical_validation.py`
- 状态：VERIFIED / PASS
- 局限：双管串联；体二极管漏电约 1e-11 A

## V10 软启动峰值充电电流（0→5 ms）

- 优化前 → 优化后：1.0897 → 1.0562 A（改善 3.07%）
- 条件：18 V 输入，1 A CC，8 ms 窗口
- 数据来源：真实开关级 ngspice
- 原始证据：`BatteryLab\results\hardening\charging\run_20261126_185404_348b91/soft_start_comparison.csv`
- 核心源码：`hardening/charging_control_comparison.py`
- 状态：VERIFIED / PASS
- 局限：电感已限制 di/dt，峰值改善有限

## V11 软启动启动能量（0→5 ms）

- 优化前 → 优化后：0.2492 → 0.1368 J（改善 45.10%）
- 条件：0–5 ms 积分窗口
- 数据来源：真实开关级 ngspice
- 原始证据：`BatteryLab\results\hardening\charging\run_20261126_185404_348b91/soft_start_comparison.csv`
- 核心源码：`hardening/charging_control_comparison.py`
- 状态：VERIFIED / PASS
- 局限：窗口为启动段，非整段充电

## V13 抗积分饱和 CV 过冲（none→conditional）

- 优化前 → 优化后：3.257 → 2.068 mV（改善 36.51%）
- 条件：CC→CV 11.95→12.15 V，12 ms
- 数据来源：真实开关级 ngspice
- 原始证据：`BatteryLab\results\hardening\charging\run_20261126_185404_348b91/antiwindup_comparison.csv`
- 核心源码：`hardening/charging_control_comparison.py`
- 状态：VERIFIED / PASS
- 局限：恢复时间基本不变

## V17 系统效率（基准→优化LC+控制器）

- 优化前 → 优化后：94.158 → 95.206 %（改善 +1.048 pp / +1.11%）
- 条件：3S SOC 0.4，5 V/2 A，10 ms
- 数据来源：真实开关级联合仿真
- 原始证据：`BatteryLab\results\hardening\system\run_20261126_185616_e47de7/system_candidate_summary.json`
- 核心源码：`hardening/system_candidate_validation.py`
- 状态：VERIFIED / PASS
- 局限：仿真效率，不含驱动与辅助电源

## V18 系统输出纹波（基准→优化）

- 优化前 → 优化后：24.54 → 21.0 mV（改善 14.43%）
- 条件：2.5 Ω 稳态，6 ms 前窗口
- 数据来源：真实开关级联合仿真
- 原始证据：`BatteryLab\results\hardening\system\run_20261126_185616_e47de7/system_candidate_comparison.csv`
- 核心源码：`hardening/system_candidate_validation.py`
- 状态：VERIFIED / PASS
- 局限：需与控制器配套

## V19 负载阶跃最大偏差（2.5→1.25 Ω）

- 优化前 → 优化后：843.0 → 574.97 mV（改善 31.79%）
- 条件：6 ms 阶跃，10 ms 窗口
- 数据来源：真实开关级联合仿真
- 原始证据：`BatteryLab\results\hardening\system\run_20261126_185616_e47de7/system_candidate_comparison.csv`
- 核心源码：`hardening/system_candidate_validation.py`
- 状态：VERIFIED / PASS
- 局限：恢复时间略变慢

## V24 SOC 方法误差（raw OCV / ECM observer / 安时积分）

- 优化前 → 优化后： → 9.30–9.70 / 1.48–1.81 / ~0 pp（改善 —）
- 条件：US06/BJDST 50/80
- 数据来源：公开数据重放
- 原始证据：`BatteryLab\results\stage7\run_stage7_20261126_162211_3590e5\soc_method_comparison.csv`
- 核心源码：`estimation/`
- 状态：VERIFIED / LIMITED
- 局限：安时积分参考由同一电流积分推导，非独立实测 SOC
