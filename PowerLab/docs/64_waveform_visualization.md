# 64 波形可视化

## 1. 原始波形与展示数据

一次真实 SPICE 运行把完整波形写入 `results/**/run_<id>/waveform.csv`。波形文件是
**分析事实来源**：性能指标、判定、导出与复核都基于完整文件。

页面绘图使用另一次只读读取，并按显示预算抽样。展示波形只用于观察趋势，
不能替代原始分析数据。页面上明确标注“抽样说明”和“导出使用完整波形”。

相关文件：

- `storage/result_repository.py`：`load_waveform()`、`downsample_frame()`、`load_run_bundle()`
- `ui/result_reader.py`：`waveform()`（`st.cache_data` 缓存）、`DOWNLOAD_LIMIT`
- `ui/waveform_viewer.py`：信号选择、点数选择、稳态窗口、导出按钮
- `ui/chart_factory.py`：`waveform_figure()`、`two_panel_waveform()`

## 2. 分块与按列读取

`load_waveform(directory, columns=None, max_points=None)`：

1. 只读取 `waveform.csv` 或 `waveform.csv.gz`；
2. `columns` 非空时用 `usecols` 只加载需要的列；
3. 不修改文件，不写回；
4. 读取异常返回 `None`，页面显示“波形不可用”，不生成替代数据。

大数据文件不会被一次性送入浏览器；页面只接收抽样后的 DataFrame。

## 3. 降采样算法

`downsample_frame(frame, max_points)`：

- 取等间隔位置：`step = max(1, len(frame) // max_points)`，位置为 `range(0, len, step)`；
- 额外强制加入每一列的 `idxmax` 与 `idxmin`，避免峰值/谷值被等间隔抽样漏掉；
- 按索引排序后若仍超过上限，再等间隔截取；
- 输入行数不超过上限时原样返回。

测试 `tests/test_result_repository.py::test_downsample_keeps_extreme_points` 构造
300 点、单个峰值在索引 150 的波形，以 100 点上限读取，断言结果行数 ≤ 100 且最大值为 10.0。

**限制**：极端点保留只保证“被加入候选”，最终截取仍可能丢弃个别点；
因此任何用于判定的计算都不得基于展示数据。

## 4. Plotly 图表

`ui/chart_factory.py` 统一生成：

| 图表 | 函数 | 用途 |
| --- | --- | --- |
| 单/多信号波形 | `waveform_figure()` | 电压、电流、PWM 等 |
| 双面板波形 | `two_panel_waveform()` | 输出电压与电感电流对齐 |
| 参数扫描曲线 | `sweep_figure()` | 指标随参数变化 |
| 直方图 | `histogram_figure()` | Monte Carlo 分布 |
| 箱线图 | `box_figure()` | 样本离散程度 |
| 收敛曲线 | `convergence_figure()` | 时间步与误差（对数横轴） |

波形横轴默认换算为毫秒，hover 显示原始数值；信号可多选。

## 5. 多信号对齐

- 所有信号共享同一 `time_s` 列，绘图前不做独立重采样；
- 稳态窗口从波形后 20% 开始，用于纹波/均值观察；
- 双面板图共享横轴，便于观察开关瞬态与电流响应；
- 不同运行之间不做自动插值对齐，比较时分别读取各自时间轴。

## 6. 实际数据规模与耗时

以真实非理想 Buck 运行 `20261125_175823_618448b9` 为例：

| 项目 | 实际值 |
| --- | --- |
| 原始波形行数 | 14,761 |
| 完整读取耗时 | 0.032 s |
| 上限 30,000 点读取耗时 | 0.036 s |
| 页面可选点数 | 2,000 / 5,000 / 8,000 / 15,000 / 30,000 |
| 默认显示点数 | 8,000 |
| 配置上限 | 30,000（`configs/web_config.yaml`） |

测量命令（2026-11-25 18:03）：

```powershell
conda run -n kaifa_power python -c "import time; from pathlib import Path; from storage.result_repository import load_waveform; d=Path('results/web_runs/run_20261125_175823_618448b9'); t=time.perf_counter(); f=load_waveform(d, max_points=30000); print(len(f), round(time.perf_counter()-t,4))"
```

## 7. 为什么展示波形不能代替原始分析数据

1. 展示数据经过抽样，尖峰、窄脉冲和开关振铃可能被稀释；
2. 性能分析使用完整波形与时间加权统计，抽样会改变均值与纹波；
3. 判定阈值可能落在被抽掉的极值点上；
4. 导出按钮始终读取完整文件，不经展示缓存；
5. HTML 报告与 CSV/JSON 导出均从磁盘真实文件生成，不触发 SPICE 重跑。

因此页面把“展示”和“分析/导出”分开，并在波形区显式提示抽样比例与原始行数。
