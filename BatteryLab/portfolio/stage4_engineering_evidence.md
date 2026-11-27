# BatteryLab 第四阶段工程证据（模拟前端与采集链）

> 所有数值来自 `results/` 下已保存的真实运行记录，或标注为理论计算/Datasheet 规格。
> “SPICE”一律指本机 ngspice 34 真实求解；“Datasheet”一律指 TI 官方文档，不是本人实测。

## 1. 本阶段做了什么

在第三阶段冻结电池模型之上，建立并验证 3S 模拟采集链：

```text
电池模型（R0/R1/C1 + 3S 节点）
  ├─ 单体差分采样：四电阻差分放大器 + 47 Ω/0.22 µF
  ├─ 共模/差模扫描 + 电阻失配实验
  ├─ 双向电流：10 mΩ + INA240A2 规格行为模型 + RC
  ├─ ADC：12 位中点重构 + 非理想项 + 混叠实验
  ├─ NTC：10 kΩ/B3950 + 10 kΩ 上拉 + 真实 SPICE
  ├─ 零点/两点校准 + 1000 组容差 + 误差预算
  ├─ 3S 全链路静态/瞬态/干扰/异常状态
  └─ BQ76922/INA240 Datasheet 研究与初步 BOM/引脚映射
```

## 2. 量化证据（8 列，严格区分数据类型）

| 指标 | 实际数值 | 单位 | 工况 | 数据来源 | Run ID | 原始证据 | 验证状态 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 3S 节点电压 | 0 / 3.6 / 7.4 / 11.4 | V | 3.6/3.8/4.0 V 三节 | spice_simulation | `sensing_20261126_135112_b44fef` | `results/sensing/run_*/summary.json` | IDENTIFIED |
| 错误接地 cell2 偏差 | 3.6 | V | 把 N2 对地当 cell2 | analytical_theory | `sensing_20261126_135112_b44fef` | 同上 | IDENTIFIED |
| 差分理论与 SPICE 最大误差 | 0.003488 | mV | 理想运放，差模扫描 | spice_simulation | `sensing_20261126_135218_cb8cf7` | `results/sensing/run_*/summary.json` | IDENTIFIED |
| 差模增益 Ad | 0.49999925 | V/V | 100k/50k 四电阻 | spice_simulation | `sensing_20261126_135218_cb8cf7` | 同上 | IDENTIFIED |
| 共模增益 Acm | −5.82×10⁻¹¹ | V/V | 匹配电阻，共模扫描 | spice_simulation | `sensing_20261126_135218_cb8cf7` | 同上 | IDENTIFIED |
| CMRR 可验证下界 | 133.98 | dB | 数值分辨率下界 | spice_simulation | `sensing_20261126_135218_cb8cf7` | 同上 | IDENTIFIED |
| 1% 电阻 cell1/2/3 误差 | 8.126 / 16.079 / 25.071 | mV | 共模 1.8/5.5/9.7 V | spice_simulation（线性外推） | `sensing_20261126_135218_cb8cf7` | `cell_errors` | IDENTIFIED |
| 0.1% 电阻 cell1/2/3 误差 | 1.639 / 2.825 / 4.163 | mV | 同上 | spice_simulation（线性外推） | `sensing_20261126_135218_cb8cf7` | 同上 | IDENTIFIED |
| 输入滤波负载效应 | 0.846 / 0.893 / 0.940 | mV | 47 Ω + 0.22 µF | spice_simulation | `sensing_20261126_135112_b44fef` | `filter_loading_error_v` | IDENTIFIED |
| 单体电压采集范围 | 2.5–4.25 | V | 教学量程 | spice_simulation | `sensing_20261126_135542_6eec7a` | `static_scenarios` | IDENTIFIED |
| 电压最大采集误差（1000 组校准后） | 3.226 | mV | 0.1% 电阻，共模 9.7 V | adc_behavioral_model | `sensing_20261126_135449_d8a6d3` | `summary.json:voltage.post` | IDENTIFIED |
| 电压 RMSE（校准后） | 0.873 | mV | 同上 | adc_behavioral_model | `sensing_20261126_135449_d8a6d3` | 同上 | IDENTIFIED |
| 电压校准 RMSE 改善 | 88.49 | % | 两点校准 3.0/4.1 V | adc_behavioral_model | `sensing_20261126_135449_d8a6d3` | 同上 | IDENTIFIED |
| 双向电流范围 | −2.5–+2.5 | A | 正常量程 | spice_simulation | `sensing_20261126_135555_720959` | `results/sensing/run_*/summary.json` | IDENTIFIED |
| 电流跨导 | 0.500000063 | V/A | 10 mΩ × 50 V/V | spice_simulation | `sensing_20261126_135555_720959` | 同上 | IDENTIFIED |
| 分流压降（2.5 A） | 25.000 | mV | 10 mΩ | spice_simulation | `sensing_20261126_135555_720959` | 同上 | IDENTIFIED |
| 分流功耗（2.5 A） | 62.500 | mW | 10 mΩ | analytical_theory | `sensing_20261126_135555_720959` | 同上 | IDENTIFIED |
| 电流最大采集误差（校准后） | 3.004 | mA | 1000 组，两点校准 | adc_behavioral_model | `sensing_20261126_135449_d8a6d3` | `summary.json:current.post` | IDENTIFIED |
| 电流 RMSE（校准后） | 0.840 | mA | 同上 | adc_behavioral_model | `sensing_20261126_135449_d8a6d3` | 同上 | IDENTIFIED |
| RC 实际截止频率 | 7695.23 | Hz | 47 Ω + 0.22 µF | spice_simulation | `sensing_20261126_135324_f7f014` | `summary.json:ac` | IDENTIFIED |
| RC 截止相对误差 | −0.011 | % | 理论 7696.08 Hz | spice_simulation | `sensing_20261126_135324_f7f014` | 同上 | IDENTIFIED |
| 100 kHz 干扰衰减 | −22.3003 | dB | 差模 100 kHz | spice_simulation | `sensing_20261126_135324_f7f014` | `summary.json:interference` | IDENTIFIED |
| 阶跃上升时间 | 45.427 | µs | 10–90%，0→1 V | spice_simulation | `sensing_20261126_135324_f7f014` | `summary.json:step` | IDENTIFIED |
| ADC LSB（12 位/3.3 V） | 0.805664 | mV | 中点重构 | adc_behavioral_model | `sensing_20261126_135332_67fb34` | `summary.json:resolution_comparison` | IDENTIFIED |
| ADC 最大量化误差 | 0.402832 | mV | 0.5 LSB | adc_behavioral_model | `sensing_20261126_135332_67fb34` | 同上 | IDENTIFIED |
| ADC 正常量程饱和比例 | 0 | — | 2.5–4.25 V | adc_behavioral_model | `sensing_20261126_135542_6eec7a` | `voltage_metrics.invalid_count` | IDENTIFIED |
| NTC 最大温度误差（校准后） | 0.0726 | ℃ | 1000 组，两点校准 | adc_behavioral_model | `sensing_20261126_135449_d8a6d3` | `summary.json:temperature.post` | IDENTIFIED |
| NTC 自热 | NOT_VERIFIED | — | 缺耗散系数 | educational_assumption | `sensing_20261126_135306_def360` | 文档 37 | NOT_VERIFIED |
| NTC 开路/短路状态 | 3.267 V / 0.033 V | V | SENSOR_OPEN / SENSOR_SHORT | spice_simulation | `sensing_20261126_135542_6eec7a` | `status_cases` | IDENTIFIED |
| 电压校准前→后最大误差 | 2.4714 → 0.000858 | mV | 5 个独立验证点 | spice_simulation | `sensing_20261126_135458_c01b86` | `summary.json:voltage.metrics` | IDENTIFIED |
| 电流校准前→零点→两点 | 10.7286 → 8.7316 → ≈0 | mA | 6 个独立验证点 | spice_simulation | `sensing_20261126_135458_c01b86` | `summary.json:current.metrics` | IDENTIFIED |
| 温度校准前→后最大误差 | 0.4507 → 0.0205 | ℃ | 6 个独立验证点 | spice_simulation | `sensing_20261126_135458_c01b86` | `summary.json:temperature.metrics` | IDENTIFIED |
| 随机容差样本数 | 1000 | 组 | 均匀独立，seed 42 | synthetic_test_data | `sensing_20261126_135449_d8a6d3` | `summary.json:sample_count` | IDENTIFIED |
| 角点 SPICE 与解析最大差 | 16.25 | µV | 4 通道 × 3 输入 | spice_simulation | `sensing_20261126_135449_d8a6d3` | `corner_spice_verification.csv` | IDENTIFIED |
| 电压最坏情况预算 | 30.887 | mV | 线性叠加 | analytical_theory | `sensing_20261126_135449_d8a6d3` | `error_budget_voltage.json` | RISK（超 10 mV 目标） |
| 电流最坏情况预算 | 37.736 | mA | 线性叠加 | analytical_theory | `sensing_20261126_135449_d8a6d3` | `error_budget_current.json` | RISK（超 20 mA 目标） |
| 温度最坏情况预算 | 0.2457 | ℃ | 线性叠加 | analytical_theory | `sensing_20261126_135449_d8a6d3` | `error_budget_temperature.json` | IDENTIFIED |
| BQ76922 规格条目 | 28 | 项 | 官方 Datasheet | datasheet_specification | — | `hardware/device_study/bq76922_specifications.csv` | IDENTIFIED |
| INA240 规格条目 | 20 | 项 | 官方 Datasheet | datasheet_specification | — | `hardware/device_study/ina240_specifications.csv` | IDENTIFIED |
| 初步 BOM 行数 | 15 | 行 | 器件级初选 | educational_assumption | — | `hardware/afe/preliminary_bom.csv` | TBD（未采购） |
| 引脚映射 | 32 | 脚 | 3S 真实 VC 映射 | datasheet_specification | — | `hardware/afe/pin_mapping.csv` | IDENTIFIED |
| 真实 SPICE 求解总数 | 68 | 次 | 9 个 demo 合计 | spice_simulation | 见 docs/40 | `results/*/summary.json:real_spice_solves` | IDENTIFIED |
| Pytest 用例 | 257 passed / 0 failed / 0 skipped | 个 | 全量测试 | python_test | — | pytest 输出 | PASS |
| Python 依赖检查 | No broken requirements | — | `pip check` | python_test | — | pip check 输出 | PASS |

数据类型图例：

- `spice_simulation`：真实 ngspice 数值求解；
- `adc_behavioral_model`：ADC/采集行为模型；
- `analytical_theory`：公式推导；
- `educational_assumption`：教学假设；
- `datasheet_specification`：TI 官方 Datasheet 规格；
- `synthetic_test_data`：容差随机样本，不代表真实批次或良率。

## 3. 不能这样写（表述边界）

- 不能把 3.226 mV 写成 BQ76922 芯片实测精度；
- 不能把 1000 组随机样本通过比例写成商业良率；
- 不能把 CALCE 公开数据写成个人电池硬件实验；
- 不能把 INA240 行为模型写成芯片内部晶体管电路；
- 不能把 12 位 ADC 量化步距写成系统采集精度。
