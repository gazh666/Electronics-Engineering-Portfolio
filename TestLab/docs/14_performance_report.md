# 14 性能分析报告（实际运行）

本文件记录第六阶段真实运行结果。所有数值均来自虚拟 DUT 行为模型，
不是真实硬件测量。

## 1. 运行环境

- Conda 环境 `kaifa`，Python 3.11.18；
- PyVISA 1.16.2、PyVISA-sim 0.7.1；
- pandas 3.1.1、plotly 7.0.0、pytest 9.2.0；
- 未修改 PyVISA / PyVISA-sim 上游源码。

## 2. 单工况分析

运行命令：

```powershell
conda run -n kaifa python -m scripts.performance_demo
```

工况：12 V 输入、限流 2 A、负载 1 A。

| 指标 | 实际值 |
| --- | --- |
| 输入功率 | 5.533333 W |
| 输出功率 | 4.980000 W |
| 功率损耗 | 0.553333 W |
| 转换效率 | 90.0000% |
| 带符号电压误差 | -0.4% |
| 绝对电压误差 | 0.4% |
| 数据质量 | VALID |
| 指标状态 | AVAILABLE |

限值判定：

| 指标 | 实际值 | 限值 | 判定 |
| --- | --- | --- | --- |
| 输出电压 | 4.98 V | 4.9–5.1 V | PASS |
| 绝对电压误差 | 0.4% | ≤2.0% | PASS |
| 效率 | 90.0% | 85–100% | PASS |
| 负载调整率 | 单条不可算 | ≤1.0% | N/A |
| 线性调整率 | 单条不可算 | ≤1.0% | N/A |

## 3. 负载调整率

运行编号：`20261124_155421_b9f525`

- 空载（0 A）：Vout = 5.000 V；
- 满载（2 A）：Vout = 4.960 V；
- 负载调整率 = `(5.000 - 4.960) / 5.0 × 100 = 0.8%`；
- 限值 1.0% → **PASS**。

负载扫描状态：

| 负载 | 状态 | 说明 |
| --- | --- | --- |
| 0–2.0 A | NORMAL | 稳压区，效率字段 90% |
| 2.25–2.5 A | OVERCURRENT | 简化停机，输出 0 V，效率不可定义 |

## 4. 线性调整率

运行编号：`20261124_155337_3f1456`（单独扫描）及完整分析中的
`line_sweep`。

- 8 V：UNDERVOLTAGE，输出 0 V；
- 9–16 V：NORMAL，Vout 恒为 4.980 V；
- 17 V：OVERVOLTAGE，输出 0 V；
- 正常区线性调整率 = **0.0%**（0.0 mV/V）；
- 限值 1.0% → **PASS**。

重要说明：0% 是当前模型不含输入电压项导致的**模型结构结果**，
不能解释为真实电源具有无限好的线性调整率。

## 5. 完整数据集

运行命令：

```powershell
conda run -n kaifa python -m scripts.full_performance_demo
```

运行编号：`20261124_155421_b9f525`

| 扫描 | 样本数 | 状态分布 |
| --- | --- | --- |
| 负载扫描 | 11 | NORMAL 9，OVERCURRENT 2 |
| 输入电压扫描 | 10 | NORMAL 8，UNDERVOLTAGE 1，OVERVOLTAGE 1 |
| 二维扫描 | 18 | NORMAL 15，OVERCURRENT 3 |

数据质量汇总：

```json
{"total": 0, "error_count": 0, "warning_count": 0, "by_code": {}}
```

## 6. 生成文件

目录：`results/performance_20261124_155421_b9f525/`

| 文件 | 内容 |
| --- | --- |
| `raw_load_sweep.csv` | 负载扫描原始模型数据 |
| `raw_line_sweep.csv` | 输入电压扫描原始数据 |
| `raw_matrix_sweep.csv` | 二维扫描原始数据 |
| `analyzed_results.csv` | 指标 + 质量状态 + 判定，共 39 行 |
| `data_quality_report.json` | 每个扫描的完整质量报告与排除原因 |
| `summary.json` | 样本数、状态分布、指标统计、调整率、假设说明 |
| `load_regulation.html` | 电压/输入电流/输出功率/损耗 4 子图，标注过流区 |
| `line_regulation.html` | 输入电压-输出电压曲线，标注欠压/过压区 |
| `power_analysis.html` | 输入/输出/损耗功率对比 |
| `efficiency_analysis.html` | 效率曲线，空载/保护留空 |
| `operating_state_heatmap.html` | 输入电压 × 负载状态热力图 |

单工况演示另生成 `results/line_sweep_20261124_155337_3f1456/`。
第五阶段负载扫描文件保留在 `results/load_sweep_*`。

## 7. 工程判断

- 建立完整的数据链路：仪器设置 → 模型计算 → 数据质量 → 指标 → 限值；
- 正常、保护与空载工况分别处理，保护状态不误判为 FAIL；
- 不可定义效率保留空值，不伪造 0%；
- 所有限值可配置，修改 YAML 后判定结果随之变化；
- 报告显式标注模型假设与非真实测量属性。

## 8. 不能验证的项目

- 真实器件的效率曲线、纹波、瞬态响应；
- 真实保护阈值、保护延迟与恢复行为；
- 真实线性调整率（当前模型与 Vin 无关）；
- 温度、老化、批次差异与生产良率；
- 与任何真实芯片数据手册的符合性。

## 9. 测试结果

```text
297 passed in 7.29s
```

第五阶段 239 个测试全部保留并通过，本阶段新增 58 个测试。
