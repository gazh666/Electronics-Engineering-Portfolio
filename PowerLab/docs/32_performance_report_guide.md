# 32 性能报告使用指南

本文说明如何运行性能分析、读取结果、定位 run_id、找到原始波形、查看 CSV/JSON、
生成 HTML 报告，以及如何追溯每项指标的计算方法。

代码位置：`scripts/performance_common.py`（`run_performance_case`、
`save_performance_run`、`save_default_figures`）、`reports/performance_report.py`
（`render_performance_report`、`write_performance_report`）、
`storage/result_store.py`（`ResultStore.create_run_dir`、`write_json`、
`write_dataframe`）。

真实示例：`results/performance/run_20261125_143528_3011f8e8/`，
HTML 报告 `performance_report.html`。

## 1. 如何运行性能分析

所有命令在 `PowerLab` 下执行：

```powershell
conda run -n kaifa_power python -m scripts.buck_stage5_demo
```

该综合入口依次完成：基线性能分析（含频谱/谐波/判定/HTML）、6 个基准工况、
7 个负载点、5 个输入电压点，并写 `results/buck_stage5/run_<id>/stage5_validation.json`。

单点入口：

| 脚本 | 用途 |
| --- | --- |
| `python -m scripts.ripple_analysis_demo` | 纹波、逐周期统计、ESR 分解 |
| `python -m scripts.switching_analysis_demo` | 边沿、延迟、开关能量 |
| `python -m scripts.spectrum_demo` | A/E 频谱与谐波对照 |
| `python -m scripts.load_characteristics_demo` | 7 点负载扫描与调整率 |
| `python -m scripts.line_characteristics_demo` | 5 点输入扫描与灵敏度 |
| `python -m scripts.performance_report_demo` | 把最新 run 渲染为 HTML |

脚本必须用 `python -m scripts.<name>` 运行；直接 `python scripts\<name>.py`
会缺少包根路径。

## 2. 如何定位 run_id

每次真实运行都会新建目录：

```
results/performance/run_<run_id>/
```

`run_id` 形如 `20261125_143528_3011f8e8`（时间戳 + UUID 前 8 位）。目录名与
`metadata.json` 里的 `run_id` 一致（本次验收已逐项核对）。总线汇总目录则是：

```
results/buck_stage5/run_<run_id>/stage5_validation.json
```

定位最新一次运行：

```powershell
Get-ChildItem results\performance -Directory | Sort-Object Name | Select-Object -Last 1
```

`scripts/performance_report_demo.py` 的 `latest_run` 也按目录修改时间选择最新 run。

## 3. 单次 run 目录结构

```
results/performance/run_<run_id>/
├── metadata.json               # run_id、配置、算法入口、原始点数
├── config_snapshot.yaml        # 完整电路配置快照
├── analysis_config.yaml        # 分析参数快照
├── limits_snapshot.yaml        # 限值 profile 快照
├── circuit.cir                 # 真实 SPICE 网表
├── waveform.csv                # 稳态分析窗口波形
├── steady_state_waveform.csv   # 最后 5 个开关周期
├── cycle_statistics.csv        # 逐周期纹波
├── cycle_ripple.csv            # 逐周期纹波（同源）
├── performance_metrics.json    # 全部指标（分组）
├── performance_metrics.csv     # 全部指标（按组展开）
├── power_metrics.json          # 功率与效率
├── ripple_metrics.json         # 纹波与分解
├── switching_metrics.json      # 开关边沿与能量
├── spectrum.csv                # 频率、峰值、RMS、dBV、PSD
├── spectrum_metadata.json      # 采样率、Nyquist、分辨率、可信上限
├── harmonics.csv               # 前十阶谐波与正弦拟合
├── performance_checks.json     # 限值判定明细
├── checks.csv                  # 限值判定表格
├── data_quality.json           # 数据质量错误/告警
├── quality.json                # 质量摘要
├── summary.json                # 总体状态与统计
├── execution.log               # 运行摘要
├── performance_report.html     # 自包含 HTML 报告
└── plots/
    ├── ripple_window.png
    ├── spectrum.png
    └── harmonics.png
```

## 4. 如何找到原始波形

- `metadata.json` 的 `raw_point_count` 记录本次 SPICE 原始点数（基线 221 247）；
- `waveform.csv` 是稳态分析窗口的逐点波形（含 `time_s`、`vout_v`、
  `inductor_current_a`、`mosfet_vds_v` 等列），所有指标都可以由它复算；
- `steady_state_waveform.csv` 只保留最后 5 个开关周期，便于快速看纹波细节；
- `circuit.cir` 是生成该波形的真实网表，可与 `config_snapshot.yaml` 对照。

注意：`waveform.csv` 是**分析窗口**，不是全部 5 ms 原始数据；全量原始数据由
仿真器在内存中生成，分析器只截取稳态窗口写入结果目录，不覆盖、不改写。

## 5. 如何查看 CSV 与 JSON

- 指标口径：先看 `performance_metrics.csv` 的 `method` 列；
- 分组指标：`performance_metrics.json` 中 `groups.<group>.metrics.<name>`；
- 判定：`checks.csv`/`performance_checks.json` 的 `metric`、`limit`、`status`；
- 质量：`data_quality.json` 的 `error_codes`、`warning_codes`、`issues`；
- 频谱参数：`spectrum_metadata.json` 的 `sample_rate_hz`、`nyquist_hz`、
  `frequency_resolution_hz`、`trusted_max_hz`、`complete_cycles`；
- 谐波：`harmonics.csv` 同时给 `amplitude_peak`、`amplitude_rms` 与
  `sine_fit_amplitude`，用于交叉验证。

示例：输出电压误差百分比的计算口径是

$$
\text{error}\%=\frac{|\bar v_{out}-V_{target}|}{V_{target}}\times100\%
=\frac{|4.668158-5.0|}{5.0}\times100\%=6.6368\%
$$

## 6. 如何生成 HTML 报告

```powershell
conda run -n kaifa_power python -m scripts.performance_report_demo
```

输出示例（本次验收实际日志）：

```text
[report] run_dir=results\performance\run_20261125_143434_0180ce6a
[report] html=results\performance\run_20261125_143434_0180ce6a\performance_report.html size=18562 bytes
```

该脚本按目录修改时间选择“最新 run”，因此不同时刻运行会指向不同目录；
基线综合入口 `buck_stage5_demo` 会额外在基线 run 下生成报告
（`run_20261125_143528_3011f8e8/performance_report.html`，18 666 bytes）。

也可以直接调用：

```python
from reports.performance_report import write_performance_report
write_performance_report("results/performance/run_20261125_143528_3011f8e8")
```

报告是静态自包含 HTML，不依赖 JavaScript 或外部资源。

## 7. 如何追溯每项指标的计算方法

1. `performance_metrics.csv` 的 `method` 字段写明口径，例如
   `max-min of raw samples in window`、`time_weighted_integration`；
2. `metadata.json` 的 `algorithms` 指向统一入口
   `analysis.performance_analyzer.PerformanceAnalyzer.analyze`；
3. 按指标组读对应模块：
   - 时间加权/RMS：`analysis/time_domain.py`
   - 纹波/分解：`analysis/ripple_analysis.py`
   - 开关：`analysis/switching_analysis.py`
   - 频谱/谐波：`analysis/spectrum_analysis.py`、`harmonic_analysis.py`
   - 功率：`analysis/power_metrics.py`
   - 判定/质量：`performance_judge.py`、`performance_quality.py`
4. 用 `config_snapshot.yaml` 与 `circuit.cir` 复现同一工况，核对数值；
5. 任何数值都可回到 `waveform.csv` 用同一公式复算。

## 8. 安全边界

- 报告生成器只允许读取 `results/` 下的目录（`_validate_run_dir`）；
- 所有来自 JSON/CSV 的文本都经 `html.escape` 转义；
- 不执行 run 目录中的脚本、不联网、不补造缺失指标；
- 写入只发生在新建 run 目录，不覆盖历史结果。

## 9. 面试题

1. 为什么报告生成器要限制只能读取 results 目录？
   防止路径穿越读取源码、密钥或系统文件。
2. 为什么所有文本都要 HTML 转义？
   指标说明与模型名可能包含 `<`、`>`，不转义会破坏页面甚至注入脚本。
3. 为什么报告不内嵌全部原始波形？
   数据量太大；报告只放窗口图与关键指标，原始 CSV 单独留存。
4. `plots/` 缺图时报告应该报错吗？
   不应报错，应跳过该图并保留文字结论。
5. 为什么每个指标都要记录 `method` 与 `data_source`？
   读者必须能区分实测、理论与假设，并能按同一口径复算。
6. 如何证明报告数值不是手工填写的？
   目录中有网表、配置快照、原始窗口波形与 run_id，可重跑复现。
7. 为什么 `waveform.csv` 不是全部 5 ms 数据？
   分析只截取稳态窗口；全量数据由仿真器生成，报告关注可复算的稳态段。
