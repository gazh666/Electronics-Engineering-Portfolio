# BatteryLab 第三阶段工程证据（真实数据驱动）

> 所有数值均来自 `results/` 下已保存的真实运行记录，可用文档第 8 节命令复现。
> “实测”一律指 CALCE 公开实验数据，不是本人硬件实测。

## 1. 本阶段做了什么

把第二阶段的“教学参数 ECM”升级为“真实实验数据驱动的参数辨识与独立验证”：

```
CALCE 原始数据
  ├─ 容量：1 A 恒流放电积分
  ├─ OCV：0.1 A 连续充放电 + 迟滞 + 跨样品对照 + 增量静置质量
  ├─ R0：真实 DST 阶跃的 1 s 窗口表观内阻
  ├─ RC：7200 s 静置恢复的一阶/二阶指数拟合
  ├─ 动态辨识：DST 50% 最小二乘（Rint / 一阶 / 二阶 RC）
  ├─ 冻结 → FUDS 50%/80% 独立验证（不调参）
  ├─ 额外：US06、BJDST 6 组工况
  ├─ 真实 ngspice 网表 + 3S1P 电池组
  └─ 温度：缺 0/45℃ 数据，NOT_VERIFIED
```

## 2. 量化证据（8 列，严格区分数据类型）

| 指标 | 实际数值 | 单位 | 实验条件 | 数据来源 | Run ID | 原始证据 | 验证状态 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 公开实验文件数量 | 9 | 个 | CALCE INR18650-20R，25 ℃ | public_experimental_data | `configs/dataset_split.yaml` | `configs/dataset_split.yaml` | IDENTIFIED |
| 低电流 OCV 有效点数 | 147659 | 点 | SP1，±0.1 A，25 ℃ | public_experimental_data | `ocv_20261126_131453_852541` | `results/ocv/run_*/ocv_quality_report.json` | IDENTIFIED |
| 实测容量（SP2） | 2.028083 | Ah | 1.0003 A 恒流放电至 2.5 V，25 ℃ | public_experimental_data | `capacity_20261126_124452_8cff3c` | `results/capacity/run_*/capacity_results.json` | IDENTIFIED |
| 容量积分差异 | 1.996×10⁻⁵ | Ah | 积分值 vs 文件记录值 | public_experimental_data | `capacity_20261126_124452_8cff3c` | `results/capacity/run_*/capacity_results.json` | IDENTIFIED |
| OCV 覆盖 SOC | 0–1（201 点） | 1 | 端点由实测分支常量延伸 | identified_parameters | `ocv_20261126_131453_852541` | `data/identified/ocv/ocv_soc_average.csv` | IDENTIFIED |
| 最大充放电迟滞 | 129 | mV | SOC 0.87，25 ℃ | public_experimental_data | `ocv_20261126_131453_852541` | `results/ocv/run_*/ocv_quality_report.json` | IDENTIFIED |
| 跨样品 OCV 最大差 | 23.23 | mV | SP1 vs SP3，SOC 5%–85% | public_experimental_data | `ocv_20261126_131453_852541` | `results/ocv/run_*/ocv_quality_report.json` | IDENTIFIED |
| 增量 OCV 有效段 | 1 / 22 | 段 | 静置 ≥1800 s、末端漂移 ≤2 mV/h | public_experimental_data | `ocv_20261126_131453_852541` | `results/ocv/run_*/ocv_quality_report.json` | NOT_VERIFIED |
| 有效 R0 样本数 | 727（281+446） | 个 | DST 50%/80%，1 s 窗口 | public_experimental_data | `pulse_identification_20261126_131603_5d0fd3` | `results/pulse_identification/run_*/pulse_summary.json` | IDENTIFIED |
| 表观 R0 中位数 | 71.56 / 71.61 | mΩ | DST 50% / DST 80% | identified_parameters | `pulse_identification_20261126_131603_5d0fd3` | `results/pulse_identification/run_*/pulse_summary.json` | IDENTIFIED |
| R1（一阶 RC） | 22.84 | mΩ | DST 50%，25 ℃ | identified_parameters | `identification_20261126_131901_fb66db` | `results/identification/run_*/identified_parameters.yaml` | IDENTIFIED |
| C1（一阶 RC） | 788.6 | F | 同上 | identified_parameters | `identification_20261126_131901_fb66db` | 同上 | IDENTIFIED |
| τ1 / τ2（二阶 RC） | 11.64 / 100.0 | s | 同上 | identified_parameters | `identification_20261126_131901_fb66db` | 同上 | BOUND_LIMITED |
| DST 训练 RMSE | 28.83 / 25.99 / 25.94 | mV | DST 50%，6685 点 | custom_ecm_simulation | `identification_20261126_131901_fb66db` | `results/identification/run_*/training_metrics.json` | IDENTIFIED / BOUND_LIMITED |
| FUDS 独立验证 RMSE | 21.73–28.45 | mV | FUDS 50%/80%，冻结参数 | custom_ecm_simulation | `dynamic_validation_20261126_131720_0e4677` | `results/dynamic_validation/run_*/validation_summary.csv` | FAIL（最大误差项） |
| FUDS 独立验证 MAE | 12.03–21.97 | mV | 同上 | custom_ecm_simulation | `dynamic_validation_20261126_131720_0e4677` | 同上 | IDENTIFIED |
| 最大绝对误差 | 375.84 | mV | SOC 1.1–1.5%，4 A | custom_ecm_simulation | `dynamic_validation_20261126_131720_0e4677` | `results/dynamic_validation/run_*/validation_metrics.json` | FAIL |
| 模型误差改善（二阶 vs Rint） | 16.96 | % | FUDS 平均 RMSE | custom_ecm_simulation | `dynamic_validation_20261126_131720_0e4677` | `results/dynamic_validation/run_*/model_selection.csv` | IDENTIFIED |
| Python vs ngspice 最大差 | 0.001600 | mV | 固定 OCV 3.7215 V，2 A/60 s | spice_simulation | `identified_spice_20261126_131837_230b2b` | `results/identified_spice/run_*/spice_pack_bms_summary.json` | IDENTIFIED |
| 3S1P 组端电压 | 11.1645 → 11.1195 | V | 初始 SOC 0.55，2 A/60 s | custom_ecm_simulation | `identified_spice_20261126_131837_230b2b` | `results/identified_spice/run_*/pack_waveform.csv` | IDENTIFIED |
| 3S 最大单体压差 | 0.000 | mV | 三节一致参数 | custom_ecm_simulation | `identified_spice_20261126_131837_230b2b` | 同上 | IDENTIFIED |
| 温度特性 | NOT_VERIFIED | — | 仅 25 ℃ 数据 | public_experimental_data | `temperature_20261126_125907_51b9d9` | `results/temperature/run_*/temperature_report.json` | NOT_VERIFIED |
| 测试数量 | 168 | 项 | 全量 pytest | synthetic_test_data / public_experimental_data | — | `tests/` | IDENTIFIED |

数据类型图例：

- `public_experimental_data`：CALCE 第三方公开实验记录；
- `identified_parameters`：由公开实验辨识得到的参数；
- `custom_ecm_simulation`：自主 ECM 预测；
- `spice_simulation`：真实 ngspice 数值求解；
- `analytical_theory`：公式推导值；
- `educational_assumption`：教学假设；
- `synthetic_test_data`：仅用于算法单元测试的人工数据。

**不得把以上全部称为实测值。**

## 3. 工程判断（不是数字堆砌）

1. **一阶 RC 被推荐，而不是误差略低的二阶 RC**：二阶的 R2 多初值离散度 46.7%、
   τ2 离散度 202.9%，且 τ2 压在 100 s 下界；训练误差只比一阶低 0.19%，独立验证低 0.9%。
   多一个不可辨识参数不值得。
2. **R0 71.6–88.4 mΩ 明显高于 datasheet 20–30 mΩ**：没有掩盖，而是记录了三个可能原因
   （1 s 窗口含极化、样品老化、批次状态未知），并明确不能当作新电芯标称值。
3. **最大误差 375.8 mV 保留 FAIL**：RMSE/MAE 达标不等于所有点达标；误差集中在 SOC < 2% 的
   空电区（占点 0.2%–1.2%），根因是 OCV 陡峭段 + 跨样品 + 静态 RC 无法表达扩散限制。
4. **增量 OCV 判为 NOT_VERIFIED**：22 个静置段只有 1 个满足 2 mV/h，说明“静置 2 h 即平衡”
   的常见假设不成立；没有用它美化 OCV 曲线。
5. **温度结论为空**：只有 25 ℃ 数据，不做外推、不生成占位参数。
6. **3S 压差为 0 不能证明均衡有效**：三节参数一致，压差必然为 0，已明确写出。

## 4. 与第二阶段的区别

| 项目 | 第二阶段 | 第三阶段 |
| --- | --- | --- |
| 参数来源 | 教学假设（30 mΩ / 1000 F 等） | CALCE 真实数据辨识 |
| OCV | 固定 3.8 V 或 7 点教学表 | 14.8 万实测点提取的 201 点曲线 |
| 验证 | 解析解、SPICE、PyBaMM 自洽 | 独立 FUDS 工况 + US06/BJDST |
| 结论性质 | “求解器正确” | “模型在真实数据上能做到什么、做不到什么” |

## 5. 已知不足与后续

1. OCV 与动态工况来自同型号不同样品，跨样品偏差无法消除；
2. 只有 25 ℃，无法给出温度系数；
3. 首次运行了 FUDS 验证，没有第二次独立留出集；最大误差阈值未通过；
4. 若要提升空电区精度，需要同一电芯的 OCV+动态数据、SOC 相关参数或扩散环节；
5. 3S 电池组未使用不一致电芯与真实均衡硬件，只验证了串并联与限压逻辑。

## 6. 面试可讲的三个技术点

1. **容量积分口径**：为什么不用文件自带的累计容量字段，而按工步做 ZOH 积分；如何用
   1.996×10⁻⁵ Ah 的差异证明读取链路正确。
2. **可辨识性**：为什么 `success=True` 不代表参数可用；如何用边界检查 + 多初值离散度
   + 条件数把二阶 RC 判为 `BOUND_LIMITED`，并据此推荐一阶 RC。
3. **不调参的独立验证**：如何用文件记录容量计算初始 SOC、如何冻结参数、为什么空电区
   375 mV 的 FAIL 必须保留而不是通过调阈值掩盖。

## 7. 诚实边界

- 不是本人硬件实测，全部为公开数据二次分析；
- 不宣称 SOH、不宣称温度特性、不宣称均衡算法有效；
- 不把教学参数当辨识结果；
- 未通过 git 提交（该目录不是 git 仓库）。

## 8. 复现命令

```powershell
conda run -n kaifa_battery python -m scripts.capacity_analysis_demo
conda run -n kaifa_battery python -m scripts.ocv_extraction_demo
conda run -n kaifa_battery python -m scripts.pulse_identification_demo
conda run -n kaifa_battery python -m scripts.ecm_identification_demo
conda run -n kaifa_battery python -m scripts.dynamic_validation_demo
conda run -n kaifa_battery python -m scripts.temperature_analysis_demo
conda run -n kaifa_battery python -m scripts.identified_spice_demo
conda run -n kaifa_battery python -m scripts.battery_stage3_demo
conda run -n kaifa_battery python -m pytest tests -q
```
