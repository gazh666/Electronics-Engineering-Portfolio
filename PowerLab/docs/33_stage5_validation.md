# 33 第五阶段验收报告

本文件按任务书第 43 节的 1–43 项逐条汇报。所有数值都来自本次真实验收运行
（2026-11-25），每项给出目录或 run_id；未实测的内容明确说明，不虚构通过率、
精度、覆盖率或提升百分比。

## 1. 实际新增及修改文件

**新增配置**

- `configs/performance_analysis.yaml`
- `configs/performance_limits.yaml`
- `configs/performance_cases.yaml`

**新增分析模块**

- `analysis/time_domain.py`
- `analysis/ripple_analysis.py`
- `analysis/switching_analysis.py`
- `analysis/spectrum_analysis.py`
- `analysis/harmonic_analysis.py`
- `analysis/regulation_analysis.py`
- `analysis/performance_models.py`
- `analysis/performance_analyzer.py`
- `analysis/performance_judge.py`
- `analysis/performance_quality.py`

**新增实验与报告**

- `experiments/load_characteristics.py`
- `experiments/line_characteristics.py`
- `experiments/performance_benchmark.py`
- `reports/performance_report.py`

**新增脚本**

- `scripts/performance_common.py`
- `scripts/ripple_analysis_demo.py`
- `scripts/switching_analysis_demo.py`
- `scripts/spectrum_demo.py`
- `scripts/load_characteristics_demo.py`
- `scripts/line_characteristics_demo.py`
- `scripts/performance_report_demo.py`
- `scripts/buck_stage5_demo.py`

**新增测试（12 个文件）**

`tests/test_time_domain.py`、`test_ripple_analysis.py`、
`test_switching_analysis.py`、`test_spectrum_analysis.py`、
`test_harmonic_analysis.py`、`test_performance_models.py`、
`test_performance_judge.py`、`test_performance_quality.py`、
`test_load_characteristics.py`、`test_line_characteristics.py`、
`test_performance_report.py`、`test_stage5_integration.py`。

**新增文档**

`docs/26_power_performance_metrics.md`、`27_ripple_and_rms_analysis.md`、
`28_switching_waveform_analysis.md`、`29_fft_and_harmonic_analysis.md`、
`30_line_and_load_characteristics.md`、`31_performance_validation.md`、
`32_performance_report_guide.md`、`33_stage5_validation.md`（本文件）。

**阶段内修改**

- `visualization/plots.py`：追加 5 个绘图函数；
- `analysis/performance_models.py`：`PerformanceResult` 增加
  `circuit_netlist`、`raw_point_count`；
- `analysis/performance_analyzer.py`：从 `SimulationResult` 填充上述字段；
- 四个入口脚本（ripple/switching/spectrum/stage5）改用 `result.run_id`
  命名目录，保证目录名与 `metadata.json` 的 `run_id` 一致；
- `reports/performance_report.py`：默认输出名改为 `performance_report.html`。

## 2. 前四阶段复用模块

| 模块 | 用途 |
| --- | --- |
| `circuits/nonideal_config.py` | `NonidealBuckConfig`、配置加载 |
| `circuits/nonideal_buck.py` | 变体特征、器件参数 |
| `simulations/nonideal_buck_runner.py` | `run_nonideal_buck_transient` 真实瞬态 |
| `simulations/models.py` | `SimulationResult` |
| `analysis/buck_waveforms.py` | 波形提取、PWM 周期边界 |
| `analysis/steady_state.py` | 稳态识别 |
| `analysis/power_metrics.py` | `compute_power_accounting` |
| `analysis/loss_analysis.py` | `switching_energy`、器件损耗 |
| `storage/result_store.py` | run 目录、JSON/CSV 写入 |
| `visualization/plots.py` | 既有绘图风格 |
| `simulations/artifacts.py` | `RESULTS_ROOT` |

没有修改 PySpice/ngspice 源码，没有修改 `TestLab` 或 `kaifa` 环境。

## 3. 实际仿真环境及后端

- 操作系统：Windows（PowerShell 5）
- Python：3.11.18
- 环境：conda `kaifa_power`
- 后端：PySpice 1.5 + ngspice-34
- 数值：numpy 1.26.4、pandas 3.0.6、scipy、PyYAML
- 温度：25 °C（配置值）
- 数据来源标记：`spice_simulation`（波形）/`spice_derived`（指标）

证据：`results/performance/run_20261125_143528_3011f8e8/metadata.json`。

## 4. 实际工程指标类别数量

基线 `performance_metrics.csv` 共 **8 组、65 条指标**：

| 组 | 条数 |
| --- | ---: |
| voltage | 10 |
| current | 15 |
| ripple | 5 |
| power | 13 |
| efficiency | 2 |
| switching | 12 |
| spectrum | 6 |
| quality | 2 |

证据：`results/performance/run_20261125_143528_3011f8e8/performance_metrics.csv`。

## 5. 实际独立指标数量及统计口径

基线共 **65 条指标记录**，每条包含 `value`、`unit`、`status`、`data_source`、
`method`。核心统一命名 9 项：

`output_voltage_mean_v`、`output_voltage_ripple_vpp`、
`inductor_current_mean_a`、`efficiency_system_percent`、
`power_residual_ratio`、`switching_frequency_hz`、
`pwm_duty_absolute_error`、`spectrum_frequency_resolution_hz`、
`switching_edge_resolution_ok`。

统计口径：均值/RMS/功率用时间加权梯形积分；峰峰值用窗口原始样本 max−min；
效率用 $P_{out}/(P_{in}+P_{drv})$；频率由完整 PWM 周期边界统计。

## 6. 实际稳态分析窗口

`run_20261125_143528_3011f8e8`：

| 项目 | 数值 |
| --- | ---: |
| 窗口起点 | 0.00478001 s |
| 窗口终点 | 0.00498001 s |
| 窗口长度 | 200 µs |
| 完整周期 | 20 |
| 窗口样本数 | 8 862 |
| 电压均值变化率 | 1.59×10⁻⁷ |
| 电流均值变化率 | 8.98×10⁻⁷ |
| 纹波变化率 | 3.03×10⁻⁶ |
| 状态 | `STEADY_STATE` |

## 7. 实际输出平均电压

**4.668158 V**（时间加权积分，`output_voltage_mean_v`）。

## 8. 实际输出误差

| 项目 | 数值 |
| --- | ---: |
| 目标电压 | 5.000000 V（`project_assumption`） |
| 误差 | −0.331842 V |
| 绝对误差 | 0.331842 V |
| 相对误差 | −6.6368 % |
| 相对精度 | 93.3632 % |

开环基线 profile 禁用了目标电压检查，因此该偏差记录为设计偏差，不触发 FAIL。

## 9. 实际输出峰峰纹波

**19.0416 mVpp**（原始样本 max−min）；最大值 4.677753 V，最小值 4.658711 V。
逐周期纹波均值 19.0402 mV，标准差 3.59×10⁻⁸ V，`drift_warning = false`。

## 10. 实际输出 AC RMS

**6.183367 mV**（去直流后时间加权 RMS）。

## 11. 实际电感电流纹波

$\Delta i_L=$ **0.639266 A**（峰值 2.187097 A，谷值 1.547831 A）。

## 12. 实际电感 RMS 电流

**1.876377 A**（时间加权 $\sqrt{\langle i_L^2\rangle}$）。

## 13. 实际电容 RMS 电流

**0.182518 A**（用于 ESR 发热评估）。

## 14. 实际 ESR 纹波分量

| 分量 | 实测 | 理论（CCM 近似） |
| --- | ---: | ---: |
| 电容电压纹波 | 7.904645 mV | 7.990829 mV |
| ESR 电压纹波 | 18.949599 mV | 19.177989 mV |
| 合成输出纹波 | 19.041561 mV | — |
| 重构最大绝对误差 | 5.707×10⁻¹⁶ V | — |

数据：`ripple_metrics.json`、`performance_metrics.json` 的
`ripple_decomposition`。

## 15. 实际输入输出功率

| 项目 | 数值 |
| --- | ---: |
| 输入功率 $P_{in}$ | 9.379313 W |
| 驱动功率 $P_{drv}$ | 0.010580 W |
| 输出功率 $P_{out}$ | 8.716695 W |
| 总损耗 | 0.673201 W |

## 16. 实际功率级及系统效率

- 功率级效率 $P_{out}/P_{in}$：**92.9353 %**
- 系统效率 $P_{out}/(P_{in}+P_{drv})$：**92.8306 %**

## 17. 实际功率平衡残差

残差 **−2.3949×10⁻⁶ W**，残差比 **−2.55×10⁻⁷**（限值 0.05）。
残差单独报告，不摊派给任何器件。

## 18. 实际 MOSFET 开关转换时间

| 项目 | 数值 | 状态 |
| --- | ---: | --- |
| 开通 VDS 10–90 % | 4.218 ns | `NOT_RESOLVED` |
| 关断 VDS 10–90 % | 6.558 ns | `NOT_RESOLVED` |
| 开通延迟 | 6.537 ns | `AVAILABLE` |
| 关断延迟 | 14.419 ns | `AVAILABLE` |

证据：`results/performance/run_20261125_143425_ddc5d86e/switching_metrics.json`。

## 19. 实际开关转换能量

| 项目 | 数值 |
| --- | ---: |
| 开通能量（10 个边沿） | 103.183 µJ |
| 关断能量（10 个边沿） | 102.029 µJ |
| 总能量 | 205.212 µJ |
| 单周期能量 | 20.521 µJ |
| 平均开关功率 | 20.005 mW |

该 20.005 mW 与第四阶段同工况一致。

## 20. 开关边沿数值分辨率验证

每个边沿只有 **3 个原始样本**，低于
`configs/performance_analysis.yaml` 的 `minimum_edge_samples: 10`。
边上最大采样间隔：开通 0.296 ns、关断 2.760 ns。因此 4.218/6.558 ns 只作为
插值数值报告，状态为 `NOT_RESOLVED`，并触发 `W_EDGE_NOT_RESOLVED` 告警。
边沿时间**不满足**作为测量规格的条件，不能写进 datasheet。

## 21. 原始 SPICE 数据点数量

**221 247** 点（`metadata.json` 的 `raw_point_count`）。

## 22. 频谱重采样率

$f_s=$ **20.000 MHz**（200 点/周期 × 100 kHz），重采样点数 **67 679**，
Nyquist 10.000 MHz，完整周期 338。

## 23. 实际频率分辨率

$\Delta f=$ **295.513 Hz**（`spectrum_frequency_resolution_hz`）。
可信上限 `trusted_max_hz = min(fs/2, 0.5/h_max) = 10.000 MHz`。

## 24. 实际基频

检出 **99 883.27 Hz**（标称 100 kHz），频点误差 −116.73 Hz，小于一个
$\Delta f$。PWM 周期统计得到的开关频率为 100.000 kHz。

## 25. 可可靠解析的最高谐波阶数

本次分析提取并解析到 **第 10 阶（1 MHz）**，10/10 为 `AVAILABLE`。
可信带宽 10 MHz 理论上允许到 100 阶，本阶段受
`analysis.spectrum.maximum_harmonic_order: 10` 限制，只报告前十阶。

## 26. 前十阶谐波结果及不可用原因

| 阶次 | 频率 | 峰值幅值 | RMS | dBV | 状态 |
| ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 99 883.27 Hz | 7.811 mV | 5.523 mV | −45.16 | AVAILABLE |
| 2 | 200 062.06 Hz | 0.983 mV | 0.695 mV | −63.16 | AVAILABLE |
| 3 | 299 945.33 Hz | 0.621 mV | 0.439 mV | −67.14 | AVAILABLE |
| 4 | 400 124.12 Hz | 0.382 mV | 0.270 mV | −71.37 | AVAILABLE |
| 5 | 500 007.39 Hz | 0.086 mV | 0.061 mV | −84.28 | AVAILABLE |
| 6 | 599 890.66 Hz | 0.201 mV | 0.142 mV | −76.93 | AVAILABLE |
| 7 | 700 069.45 Hz | 0.037 mV | 0.027 mV | −91.53 | AVAILABLE |
| 8 | 799 952.72 Hz | 0.107 mV | 0.075 mV | −82.46 | AVAILABLE |
| 9 | 900 131.50 Hz | 0.059 mV | 0.042 mV | −87.57 | AVAILABLE |
| 10 | 1 000 014.78 Hz | 0.041 mV | 0.029 mV | −90.69 | AVAILABLE |

不可用原因：本次无 `NOT_RESOLVED` 阶次。若某阶超出 `trusted_max_hz`、频率
偏移超限或幅值低于噪声底，会被标记 `NOT_RESOLVED` 并附 message，而不是补零。
THD = **16.0156 %**（只对 10 个已解析阶次求和）。

数据：`harmonics.csv`。

## 27. 实际 FFT 验证误差

`tests/test_spectrum_analysis.py::test_task_19_known_signal_fft_validation`
（已知信号 5 V + 1 kHz×0.02 V + 3 kHz×0.005 V）：

| 成分 | 设定 | 恢复 | 相对误差 |
| --- | ---: | ---: | ---: |
| DC | 5 V | 5.000000219 V | 4.4×10⁻⁸ % |
| 1 kHz | 0.02 V | 0.019998710 V | −0.00645 % |
| 3 kHz | 0.005 V | 0.004997098 V | −0.058 % |

Parseval 相对误差 **5.10×10⁻¹⁶**；103 个非整数周期时 1 kHz 幅值恢复
0.01999871 V。真实 Buck 波形上 FFT 峰值与正弦拟合幅值：平均相对误差
**6.0146 %**、最大 **14.0152 %**、基波 **9.5960 %**，原因是非整数 bin 与
邻近谐波泄漏。

## 28. 七种负载工况实际结果

| R (Ω) | Vout (V) | Iout (A) | 纹波 (mVpp) | 效率 (%) | 模式 | 状态 |
| ---: | ---: | ---: | ---: | ---: | --- | --- |
| 50 | 7.160348 | 0.143207 | 15.623 | 96.736 | DCM | PASS |
| 20 | 5.401912 | 0.270096 | 18.924 | 95.428 | DCM | PASS |
| 10 | 4.788689 | 0.478869 | 19.701 | 94.749 | CCM | INCOMPLETE |
| 5 | 4.743616 | 0.948723 | 19.267 | 94.208 | CCM | PASS |
| 2.5 | 4.668158 | 1.867263 | 19.042 | 92.831 | CCM | PASS |
| 2 | 4.634372 | 2.317186 | 19.001 | 92.256 | CCM | PASS |
| 1.667 | 4.601676 | 2.761005 | 19.213 | 91.630 | CCM | PASS |

数据：`results/performance/run_20261125_143608_abbb852d/load_characteristic.csv`。

## 29. 五种输入电压工况实际结果

| Vin (V) | D | Vout (V) | 纹波 (mVpp) | 效率 (%) | 状态 |
| ---: | ---: | ---: | ---: | ---: | --- |
| 9.0 | 0.555556 | 4.714662 | 15.029 | 93.940 | PASS |
| 10.8 | 0.462963 | 4.683818 | 17.784 | 93.227 | PASS |
| 12.0 | 0.416667 | 4.668158 | 19.042 | 92.831 | PASS |
| 14.4 | 0.347222 | 4.647228 | 21.232 | 92.330 | PASS |
| 16.0 | 0.312500 | 4.636728 | 22.482 | 92.060 | PASS |

数据：`results/performance/run_20261125_143621_633530cc/line_characteristic.csv`。

## 30. 实际开环负载调整率及适用区间

| 项目 | 数值 |
| --- | ---: |
| span（全范围） | 51.1734 % |
| CCM 斜率 | −78.508 mV/A |
| CCM 拟合 $r^2$ | 0.9992 |
| CCM 点数 | 4 |
| 剔除未稳态点 | 1（10 Ω） |
| 适用区间 | CCM 4 个可用点：5、2.5、2、1.667 Ω；10 Ω 因未稳态剔除 |

DCM 点（50 Ω、20 Ω）不参与 CCM 斜率。10 Ω 的逐周期平均电感电流存在约
3 kHz、峰峰约 1.4 mA 的振荡，超过 0.1 % 稳态判据，状态 `INCOMPLETE`。

## 31. 实际开环输入电压灵敏度

| 项目 | 数值 |
| --- | ---: |
| 灵敏度 | −10.840 mV/V |
| span | 1.5587 % |
| 拟合 $r^2$ | 0.9622 |
| 控制方式 | 前馈 $D=V_{target}/V_{in}$，**非闭环** |

该灵敏度不能当作 datasheet 线性调整率。

## 32. 实际性能检查结果

基线 profile `baseline_open_loop`：

| 指标 | 实测 | 限值 | 状态 |
| --- | ---: | --- | --- |
| 输出纹波 | 19.0416 mV | ≤ 50 mV | PASS |
| 开关频率 | 100.000 kHz | 99–101 kHz | PASS |
| 占空比误差 | 7.38×10⁻¹⁵ | ≤ 0.005 | PASS |
| 系统效率 | 92.8306 % | 85–100 % | PASS |
| 目标电压 | — | 4.9–5.1 V | SKIP（禁用） |
| 功率残差比 | −2.55×10⁻⁷ | ≤ 0.05 | PASS |

benchmark 六个工况：5 PASS + 1 FAIL（PERF004 高 ESR，纹波 61.561 mV）。

## 33. 各种判定状态数量

基线 `summary.json`：

| 状态 | 数量 |
| --- | ---: |
| PASS | 5 |
| FAIL | 0 |
| ERROR | 0 |
| SKIP | 1 |
| NOT_APPLICABLE | 0 |
| NOT_VERIFIED | 0 |
| 总体 | PASS |

数据质量：0 error，2 warning（`W_EDGE_NOT_RESOLVED` ×2）。

benchmark：PASS 5、FAIL 1。整个阶段所有结果中 FAIL 只来自 PERF004，
未通过放宽限值消除。

## 34. 实际独立 SPICE 求解次数

`buck_stage5_demo` 主链路 **19 次**：

- 基线 1 次
- benchmark 6 次
- 负载扫描 7 次
- 输入扫描 5 次

验收期间各入口（不含 pytest 内部集成测试）合计 **35 次**：
ripple 1 + switching 1 + spectrum 2 + load demo 7 + line demo 5 + stage5 19。

## 35. 实际复用历史结果次数

**0 次**。`benchmark` 的 `spice_run_count=6`、`unique_config_count=6`、
`skipped_duplicates=0`；所有扫描点都重新求解。

## 36. 实际仿真及分析耗时

10 条验收命令合计 **167.5 s**（逐条见第 39 项后的命令表）。
其中 `buck_stage5_demo` **58.4 s**，负载扫描 27.5 s，输入扫描 16.1 s，
pytest 35.6 s（pytest 自身报告 33.13 s）。

## 37. 实际 Pytest 测试结果

`conda run -n kaifa_power python -m pytest tests -v`：

- 退出码 **0**
- **401 passed**
- 测试自身耗时 **33.13 s**
- 命令墙钟耗时 **35.6 s**
- 0 failed、0 error

日志：`C:\\Users\\<user>\AppData\Local\Temp\stage5_pytest.log`（运行时），
持久副本 `results/stage5_acceptance/stage5_pytest.log`；
汇总：`results/stage5_acceptance.json`。

## 38. 与第四阶段测试基线对比

- 第四阶段验收记录：**323 passed**（`docs/25_stage4_validation.md`）
- 第五阶段：**401 passed**
- 差值：**+78**，全部来自本阶段新增测试文件与 Task 19 频谱算法验证用例
- 前四阶段用例仍全部通过，无回归

这是精确计数，不是估算。

## 39. 实际 CSV、JSON、PNG 及 HTML 路径

| 类型 | 路径 |
| --- | --- |
| 基线完整结果 | `results/performance/run_20261125_143528_3011f8e8/` |
| 基线指标 JSON | 同上 `performance_metrics.json` |
| 基线指标 CSV | 同上 `performance_metrics.csv` |
| 原始窗口波形 | 同上 `waveform.csv` |
| 稳态末 5 周期 | 同上 `steady_state_waveform.csv` |
| 网表 | 同上 `circuit.cir` |
| 配置快照 | 同上 `config_snapshot.yaml`、`analysis_config.yaml`、`limits_snapshot.yaml` |
| 频谱 | 同上 `spectrum.csv`、`spectrum_metadata.json` |
| 谐波 | 同上 `harmonics.csv` |
| 判定 | 同上 `performance_checks.json`、`checks.csv` |
| 质量 | 同上 `data_quality.json`、`quality.json` |
| PNG | 同上 `plots/ripple_window.png`、`spectrum.png`、`harmonics.png` |
| HTML | 同上 `performance_report.html`（18 666 bytes） |
| 纹波演示 | `results/performance/run_20261125_143419_75f723d6/` |
| 开关演示 | `results/performance/run_20261125_143425_ddc5d86e/` |
| 频谱 A/E | `results/performance/run_20261125_143430_3fe93959/`、`run_20261125_143434_0180ce6a/` |
| 负载扫描 | `results/performance/run_20261125_143608_abbb852d/` |
| 输入扫描 | `results/performance/run_20261125_143621_633530cc/` |
| 阶段汇总 | `results/buck_stage5/run_20261125_143621_dd15c905/stage5_validation.json` |
| 验收记录 | `results/stage5_acceptance.json` |
| 验收日志副本 | `results/stage5_acceptance/stage5_*.log`（10 条命令） |

验收命令与耗时（`results/stage5_acceptance.json`）：

| # | 命令 | 退出码 | 耗时 |
| --- | --- | ---: | ---: |
| 1 | `-m scripts.verify_environment` | 0 | 2.1 s |
| 2 | `-m scripts.ripple_analysis_demo` | 0 | 6.4 s |
| 3 | `-m scripts.switching_analysis_demo` | 0 | 6.1 s |
| 4 | `-m scripts.spectrum_demo` | 0 | 9.5 s |
| 5 | `-m scripts.load_characteristics_demo` | 0 | 27.5 s |
| 6 | `-m scripts.line_characteristics_demo` | 0 | 16.1 s |
| 7 | `-m scripts.performance_report_demo` | 0 | 3.7 s |
| 8 | `-m scripts.buck_stage5_demo` | 0 | 58.4 s |
| 9 | `-m pytest tests -v` | 0 | 35.6 s |
| 10 | `-m pip check` | 0 | 2.1 s |

## 40. 当前已知问题及限制

1. MOSFET 为 Level 1 教学模型，不是商业功率器件模型。
2. 二极管 `TT=0`，无反向恢复；高频振铃能量不能用于 EMC 结论。
3. VDS 10–90 % 边沿每边仅 3 个样本，时间值为 `NOT_RESOLVED`。
4. DCR/ESR 为常数，无频率与温度特性。
5. 没有探头、示波器带宽、PCB 与测量寄生模型；纹波是理想节点结果。
6. 输入特性是开环前馈，不是闭环线性调整率；目标 5 V 未钳位。
7. 10 Ω 负载点未稳态，未进入 CCM 拟合。
8. 未做不同栅极电阻的扫描、温度扫描、闭环补偿与 EMC 测试。
9. PERF004 高 ESR 工况真实 FAIL，保留未修改。
10. 频谱只提取前 10 阶，未做 100 阶全谱与噪声底统计。

## 41. 本阶段自主开发贡献

- 设计并实现统一指标模型 `PerformanceResult`/`PerformanceMetric`，
  把一个稳态窗口的电压、电流、纹波、功率、效率、开关、频谱、质量串成一条链路；
- 实现非均匀时间轴显式重采样、可信频段约束、Hann 相干增益补偿、
  FFT 与正弦拟合交叉验证；
- 实现开关边沿 10–90 % 插值与 `NOT_RESOLVED` 分辨率判据；
- 实现 ESR/电容纹波分解与代数恒等式校验；
- 实现开环负载/输入扫描、CCM 拟合、未稳态点剔除；
- 实现限值 profile、数据质量错误码、HTML 报告（只读 results、全量转义）；
- 编写 12 个测试文件与 7 份专业知识文档；
- 未修改 PySpice/ngspice/TestLab，未删除前四阶段内容。

## 42. 可用于简历的真实量化成果

以下都可以用本文件与对应 run 目录核验：

- 在 PySpice 1.5 + ngspice-34 上构建 65 项指标的 Buck 性能分析链路，覆盖 8 个指标组；
- 对 221 247 点非均匀 SPICE 波形完成 20 MHz 重采样、295.513 Hz 分辨率频谱，
  提取前十阶谐波，THD 16.0156 %；
- 完成 7 点负载扫描与 5 点输入扫描，CCM 负载调整率斜率 −78.508 mV/A
  （$r^2=0.9992$），开环输入灵敏度 −10.840 mV/V；
- 实现开关能量核算：205.212 µJ/窗口、20.005 mW 平均开关损耗，
  与第四阶段同工况一致；
- 建立 10 条命令的验收链，全部 exit 0，pytest 401 passed（第四阶段 323 passed）；
- 保留真实 FAIL（高 ESR 纹波 61.561 mV）与 `NOT_RESOLVED` 边沿，不修饰结论。

## 43. 二十五道电源测试及频谱分析面试题

**Q1. 为什么平均值必须时间加权？**
SPICE 步长非均匀，开关边沿附近采样密集；算术平均会高估边沿权重，改变积分结果。

**Q2. RMS 与 AC RMS 的区别？**
RMS 含直流，用于发热；AC RMS 去直流，用于纹波能量与噪声。

**Q3. 为什么功率要用 $\int vi\,dt$ 而不是 $\bar V\bar I$？**
开关波形电压电流不同相，均值相乘丢失相关性，产生系统误差。

**Q4. 纹波峰峰值的可信前提？**
窗口含完整周期，直接取原始样本 max−min，不平滑、不拟合。

**Q5. 为什么高开关频率下 ESR 纹波常占主导？**
$V_{ESR}=\Delta i_L\cdot ESR$ 不随频率下降，而 $V_C=\Delta i_L/(8fC)$ 随频率下降。

**Q6. 纹波分解误差为什么能到 1e-16 V？**
$v_{out}=v_C+v_{ESR}$ 是同一节点的代数关系，误差只来自浮点舍入。

**Q7. 开关边沿只有 3 个样本，为什么还报告时间？**
为透明保留插值值，同时标 `NOT_RESOLVED`，防止误用为规格。

**Q8. 开关能量为什么比边沿时间更可信？**
能量是积分量，具有平均效应；边沿时间是斜率推断，对稀疏采样敏感。

**Q9. 为什么 FFT 前必须重采样？**
FFT 要求等间隔；非均匀采样直接变换会产生频率与幅值错误。

**Q10. 频率分辨率由什么决定？**
$\Delta f=1/T$，由观测时长决定；提高采样率只提高 Nyquist。

**Q11. 为什么可信上限是 $\min(f_s/2,0.5/h_{max})$？**
重采样不能创造原始带宽；最大原始步长给出第二个 Nyquist 限制。

**Q12. Hann 窗相干增益如何补偿？**
除以窗样本和，再乘 2 得单边幅值；不加权会系统性低估幅值。

**Q13. 谱泄漏是什么？**
有限截断使谱与窗谱卷积，非整数 bin 能量扩散到邻近频点。

**Q14. 混叠如何产生与避免？**
高于 $f_{Nyq}$ 的成分折叠到低频；提高采样率或加抗混叠滤波。

**Q15. 幅值谱与 PSD 的区别？**
幅值谱读各阶谐波大小；PSD 归一化到每赫兹功率，便于比较噪声底。

**Q16. dBV 的定义？**
$20\log_{10}(A_{rms}/1\,\mathrm{V})$；本例基波 −45.16 dBV。

**Q17. 为什么 THD 只统计已解析谐波？**
未解析阶次超出可信频段，计入会把插值噪声当信号。

**Q18. 为什么 Model E 的 THD 高于 Model A？**
E 含非理想开关、二极管结电容与浮地驱动，边沿更慢、振铃更强。

**Q19. 电源 FFT 能替代 EMC 认证吗？**
不能。缺 LISN、天线、检波、布置与环境控制，只能做机理分析。

**Q20. 为什么 DCM 点不参与 CCM 斜率拟合？**
DCM 的电压增益关系不同，混入会扭曲线性趋势。

**Q21. CCM/DCM 边界如何估算？**
$R_{crit}=2Lf_{sw}V_{out}/((V_{in}-V_{out})D)\approx14.4$ Ω，与 10/20 Ω 实测一致。

**Q22. 开环 −10.84 mV/V 能当线性调整率吗？**
不能。datasheet 指标要求闭环稳压条件。

**Q23. 为什么目标电压在基线里禁用？**
5 V 是设计参考，不是强制目标；禁用避免用电压偏差否定纹波与效率结论。

**Q24. NOT_VERIFIED 与 FAIL 的区别？**
前者“无法证明”，后者“已证明不满足”；修复路径不同。

**Q25. 高 ESR 工况 FAIL 的工程含义？**
输出电容选型不能只看容值，ESR 直接决定纹波与发热；本例纹波 61.561 mV。

## 限制与暂停

本阶段到此完成并暂停。未开发第六阶段大规模参数扫描与器件优化、第七阶段
负载瞬态与闭环控制、Web 平台及 TestLab 接入；未修改 PySpice/ngspice、
`TestLab` 与 `kaifa` 环境；未删除第一至第四阶段任何内容。
