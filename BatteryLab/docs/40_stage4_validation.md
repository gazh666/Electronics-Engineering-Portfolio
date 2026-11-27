# 40 第四阶段最终验收报告

本报告汇总第四阶段全部真实运行结果。所有数值来自 `results/` 下保存的运行记录；
未验证项保留 `NOT_VERIFIED`，预算超限项保留 `RISK`，不修改限值换 PASS。

## 1. 验收环境与入口

| 项目 | 实际值 |
| --- | --- |
| Conda 环境 | `kaifa_battery` |
| Python | 3.11.18 |
| PySpice | 1.5 |
| ngspice | 34（真实后端） |
| 电池模型 | 第三阶段冻结 R0=77.068 mΩ，R1=22.845 mΩ，C1=788.6 F，τ1=18.016 s |
| 容量 | 2.028083 Ah（CALCE SP2，公开数据） |
| 综合验收 Run ID | `stage4_20261126_135645_a30da4` |
| 综合验收结果 | **PASS 16 / FAIL 0** |

## 2. 实际运行 ID

| 模块 | Run ID | 真实 SPICE 求解 |
| --- | --- | --- |
| 3S 单体 | `sensing_20261126_135112_b44fef` | 2 |
| 差分放大器 | `sensing_20261126_135218_cb8cf7` | 8 |
| 双向电流 | `sensing_20261126_135555_720959` | 3 |
| RC 滤波 | `sensing_20261126_135324_f7f014` | 27 |
| ADC | `sensing_20261126_135332_67fb34` | 0 |
| NTC | `sensing_20261126_135306_def360` | 3 |
| 校准 | `sensing_20261126_135458_c01b86` | 3 |
| 容差/预算 | `sensing_20261126_135449_d8a6d3` | 12 |
| 3S 全链路 | `sensing_20261126_135542_6eec7a` | 10 |
| 综合验收 | `stage4_20261126_135645_a30da4` | 0（复用） |
| **合计** | — | **68 次** |

真实 SPICE 求解 68 次，低于任务书建议预算 80 次；容差数学仿真 1000 组/通道。
两者严格区分，不把 1000 组数学样本称为 1000 次 SPICE。

## 3. 采集模块汇总表

| 采集模块 | 设计目标 | 实际仿真结果 | 最大误差 | RMSE | 校准改善 | 验证状态 |
| --- | --- | --- | --- | --- | --- | --- |
| 3S 单体电压 | 2.5–4.25 V；≤10 mV | 3.6/3.8/4.0 V；校准后 1000 组 | 3.226 mV | 0.873 mV | 88.49% | PASS（统计）/ 预算 RISK 30.887 mV |
| 差分放大器 | 理论 vs SPICE ≤0.1 mV | Ad=0.49999925；Acm=−5.82e−11 | 0.003488 mV | — | — | PASS |
| 双向电流 | ±2.5 A；≤20 mA | 跨导 0.500000063 V/A | 3.004 mA | 0.840 mA | 87.13% | PASS（统计）/ 预算 RISK 37.736 mA |
| 分流电阻 | 压降/功耗可接受 | 25 mV / 62.5 mW @2.5 A | — | — | — | PASS |
| RC 滤波 | 截止误差 ≤2%；100 kHz ≤−20 dB | 7695.23 Hz；−22.3003 dB | 0.011%（截止） | — | — | PASS |
| ADC | 量化 ≤0.5 LSB；单调 | 12 位，LSB 0.805664 mV | 0.5 LSB（0.402832 mV） | — | — | PASS |
| NTC 温度 | 0–60 ℃；≤1 ℃ | SPICE-理论 18.115 µV | 0.0726 ℃ | 0.01994 ℃ | 87.51% | PASS；自热 NOT_VERIFIED |
| 3S 全链路 | 正常量程不饱和；异常有状态 | 正常 0 饱和；开路/短路状态明确 | 电压 4.189 mV | 电压 2.514 mV | — | PASS |

注：表中“最大误差/RMSE”对电压/电流/温度是 **1000 组随机容差、两点校准后的统计值**，
不是保证最坏情况。最坏情况预算见第 6 节。

## 4. 限值检查（预先固定，未修改）

| 检查 | 实际值 | 阈值 | 状态 |
| --- | --- | --- | --- |
| 差分放大理论 vs SPICE | 0.003488 mV | 0.1 mV | PASS |
| 单体电压最大误差（校准后） | 3.226 mV | 10 mV | PASS |
| 单体电压 RMSE（校准后） | 0.873 mV | 10 mV | PASS |
| 正常量程 ADC 饱和比例 | 0.0 | 0.0 | PASS |
| 理想电流理论 vs SPICE | 0.000157 mV | 0.1 mV | PASS |
| 电流最大误差（校准后） | 3.004 mA | 20 mA | PASS |
| 电流 RMSE（校准后） | 0.840 mA | 20 mA | PASS |
| RC 截止相对误差 | −0.00011 | 0.02 | PASS |
| 100 kHz 差模衰减 | −22.301 dB | ≤−20 dB | PASS |
| RC 阶跃上升时间相对误差 | 0.000145 | 0.05 | PASS |
| ADC 最大量化误差 | 0.5 LSB | 0.5 LSB | PASS |
| ADC 单调性 | True | True | PASS |
| NTC 最大温度误差（校准后） | 0.0726 ℃ | 1 ℃ | PASS |
| NTC 温度 RMSE（校准后） | 0.01994 ℃ | 1 ℃ | PASS |
| 无效测量状态 | 明确 | 必须明确 | PASS |
| 缺失实验数 | 0 | 0 | PASS |

ADC 0.5 LSB 的浮点值为 0.5000000000001654；比较时使用 1e-9 数值容差吸收二进制表示误差，
**限值仍为 0.5 LSB，未放宽**。

## 5. 关键真实结果

### 5.1 单体与差分

- 节点 0/3.6/7.4/11.4 V，KVL 误差 0 V。
- 错误接地 cell2 偏差 3.6 V。
- 输出 2.000/2.100/2.200 V（无滤波理论），含滤波 1.99915/2.09910/2.19906 V。
- 滤波负载效应 −0.846/−0.893/−0.940 mV。
- 1% 电阻失配（共模 1.8/5.5/9.7 V）：8.126/16.079/25.071 mV。
- 0.1% 电阻：1.639/2.825/4.163 mV。
- CMRR 数值 198.68 dB；可验证下界 133.98 dB。

### 5.2 电流

- 跨导 0.500000063 V/A；理论 vs SPICE 最大 0.000157 mV。
- ±2.5 A → 0.4–2.9 V；2.5 A 压降 25 mV、功耗 62.5 mW。
- 输出滤波 fc 1591.55 Hz，阶跃建立 100.02 µs。
- −3.25 A 输出 0.1 V（放大器下限饱和）；+3.5 A 输出 3.4 V（ADC 上限饱和）。

### 5.3 RC 与 ADC

- RC：理论 7696.08 Hz，SPICE 7695.23 Hz（−0.011%）；100 kHz −22.3003 dB；
  上升时间 45.427 µs（理论 45.434 µs）；超调 0.0005%；稳态误差 −0.583 µV。
- 100 kHz 干扰：0.1414 V → 0.01085 V RMS，−22.301 dB。
- ADC：10/12/16 位最大量化误差 1.611/0.403/0.0252 mV；单调 True。
- 混叠：100 kHz 在 1 kHz 采样下混叠到 DC，0°/90° 相位均值 3.7024/3.8024 V，
  4/16 点平均不能消除；1.1 kHz 采样混叠到 100 Hz，峰峰值 0.202 V。

### 5.4 NTC 与异常状态

- 0/25/60 ℃ 分压 2.54348/1.65000/0.65707 V。
- SPICE vs 理论最大 18.115 µV；理想反演 0.000853 ℃；ADC 后 0.012896 ℃。
- 1000 组校准后最大 0.0726 ℃，RMSE 0.01994 ℃。
- 开路 3.267 V → `SENSOR_OPEN`；短路 0.033 V → `SENSOR_SHORT`。
- 自热温升 `NOT_VERIFIED`（缺耗散系数）。

### 5.5 校准

| 通道 | 校准前最大 | 校准后最大 | 说明 |
| --- | --- | --- | --- |
| 电压 | 2.4714 mV | 0.000858 mV | 两点 3.0/4.1 V |
| 电流 | 10.7286 mA | ≈0（1e−13 A） | 零点 + 两点 ±2 A |
| 温度 | 0.4507 ℃ | 0.02050 ℃ | 两点 0/60 ℃ |

1000 组独立容差：电压 RMSE 7.585→0.873 mV；电流 6.525→0.840 mA；温度 0.1596→0.01994 ℃。
验证点从未参与拟合。

## 6. 误差预算与风险

| 通道 | 最坏情况 | RSS | 主导项 | 结论 |
| --- | --- | --- | --- | --- |
| 电压 | **30.887 mV** | 23.189 mV | 四电阻失配 22.679 mV | 超过 10 mV 目标；0.1% 电阻 + 9.7 V 共模无保证裕量 |
| 电流 | **37.736 mA** | 15.868 mA | 分流电阻容差 12.5 mA | 超过 20 mA 目标；需更小容差/更高增益/校准 |
| 温度 | 0.2457 ℃ | 0.2248 ℃ | NTC R25 容差 0.2238 ℃ | 满足 1 ℃ |

**统计样本与保证最坏情况必须分开报告。** 1000 组通过不能证明量产良率或最坏情况保证。

## 7. 实际器件研究

- BQ76922：28 项规格，SLUSE86A；单体精度 ±5 mV（25 ℃）/±10 mV（0–60 ℃）/±15 mV（−40–85 ℃）（p.7）。
- 3S 真实 VC 映射：cell1 VC1–VC0；cell2 VC2–VC1；cell3 **VC5–VC4A**；VC3A/B 短接到 VC2。
- INA240A2：20 项规格，SBOS662C；50 V/V，CMRR 120 dB min/132 dB typ，Vos ±25 µV max。
- 初步 BOM 15 行，全部真实料号状态为 TBD，未采购/未打样。
- 未完成 KiCad 原理图与 PCB，不声称完成硬件设计。

## 8. 测试与依赖

```powershell
conda run -n kaifa_battery python -m pytest tests -q
conda run -n kaifa_battery python -m pip check
```

实际结果：**257 passed**（原 168 + 新增 89），无失败；`pip check` 无损坏依赖。
新增测试文件 9 个：ADC、电压、电流、温度、RC、校准、预算、容差、Stage4 集成。
集成测试包含真实 ngspice：3S 差分、双向电流、RC AC；不允许 Mock 替代全部真实 SPICE。

## 9. 当前模型局限

1. 运放为理想/教学模型，不是商业运放内部电路。
2. INA240 为 Datasheet 规格行为模型，不是芯片晶体管级模型。
3. ADC 为 12 位行为模型，与 BQ76922 内部 16 位 ADC 是独立方案。
4. 容差为均匀独立教学假设，不是真实生产分布。
5. 未建模 PCB 寄生、EMI、温度漂移、长期漂移。
6. 电池波形为单向驱动，不是实时双向联合仿真。
7. 未做真实电池实验、未做危险短路/过充实验。

## 10. 尚未验证事项（NOT_VERIFIED）

- NTC 自热温升（缺耗散系数）。
- BQ76922 真实开线检测与板级失调校准。
- 真实器件温漂、长期漂移与批次分布。
- 1000 组样本对应的商业良率。
- 完整原理图/PCB/EMC/热设计。
- MOSFET 保护与均衡（第五阶段）。

## 11. 48 项交付索引

1. 前三阶段真实基线：3S1P、2.028083 Ah、R0=77.068 mΩ、R1=22.845 mΩ、C1=788.6 F、τ1=18.016 s；见 docs/30。
2. 实际新增及修改文件：`sensing/` 8 个模块、`circuits/` 8 个模块、`analysis/` 5 个模块、`simulations/` 1 个、`scripts/` 10 个 demo + 1 个公共模块、`tests/` 9 个新增测试、`hardware/` 6 个产物、`docs/30–40` 11 份。
3. 实际 SPICE 后端：ngspice 34 + PySpice 1.5，真实求解 68 次。
4. 实际差分采集电路：R1=R3=100 kΩ，R2=R4=50 kΩ，Vref=0.2 V，47 Ω + 0.22 µF。
5. 实际运放模型：理想 VCVS / 教学非理想 / INA240 规格行为模型三层。
6. 实际差分增益：0.49999925 V/V（理论 0.5）。
7. 实际共模扫描：电池共模 0–8 V，引脚共模 0.750–3.417 V，输出 2.049997 V 恒定。
8. 实际电阻匹配误差：1% → 8.126/16.079/25.071 mV；0.1% → 1.639/2.825/4.163 mV。
9. 实际 CMRR：198.68 dB 数值；可验证下界 133.98 dB。
10. 实际单体电压采集范围：2.5–4.25 V。
11. 实际最大电压采集误差：3.226 mV（1000 组、两点校准后）。
12. 实际电压 RMSE：0.873 mV（校准后）。
13. 实际输入滤波参数：47 Ω + 0.22 µF，差模 fc=7696.08 Hz。
14. 实际 RC 截止频率：7695.23 Hz，误差 −0.011%。
15. 实际 100 kHz 干扰衰减：−22.3003 dB；RMS 0.1414→0.01085 V。
16. 实际阶跃响应时间：45.427 µs（10–90%），理论 45.434 µs。
17. 实际双向电流采集范围：−2.5–+2.5 A，3.5 A 时 ADC 饱和。
18. 实际 Shunt 压降：25.000 mV @2.5 A。
19. 实际 Shunt 功耗：62.500 mW @2.5 A。
20. 实际电流采集增益：0.500000063 V/A。
21. 实际最大电流误差：3.004 mA（1000 组、两点校准后）。
22. 实际电流 RMSE：0.840 mA（校准后）。
23. 实际 ADC 分辨率：12 位，LSB=0.805664 mV。
24. 实际量化误差：0.5 LSB=0.402832 mV，单调 True。
25. 实际采样及混叠分析：100 kHz→DC（3.7024/3.8024 V 依赖相位）；1.1 kHz→100 Hz（0.202 V 峰峰）。
26. 实际 NTC 阻温曲线：10 kΩ/B3950，0/25/60 ℃ → 33.6/10.0/5.0 kΩ。
27. 实际温度采集范围：0–60 ℃。
28. 实际最大温度误差：0.0726 ℃（1000 组、两点校准后）。
29. 实际 NTC 自热分析状态：NOT_VERIFIED（缺耗散系数；25 ℃ 自热功率 272 µW）。
30. 实际传感器异常实验：开路 3.267 V→SENSOR_OPEN；短路 0.033 V→SENSOR_SHORT。
31. 实际零点校准结果：电流 10.7286→8.7316 mA（仅零点残差）。
32. 实际两点校准结果：电压 0.000858 mV；电流 ≈0；温度 0.02050 ℃。
33. 实际校准前后误差变化：电压 RMSE 7.585→0.873 mV（88.49%）；电流 6.525→0.840 mA（87.13%）；温度 0.1596→0.01994 ℃（87.51%）。
34. 实际误差预算：电压 30.887/23.189 mV；电流 37.736/15.868 mA；温度 0.2457/0.2248 ℃（线性/RSS）。
35. 实际随机容差样本数量：1000 组/通道，seed 42。
36. 实际角点 SPICE 复验：4 通道 × 3 输入，最大差 16.25 µV。
37. 实际采集限值检查结果：16 PASS / 0 FAIL；电压/电流最坏预算另列 RISK。
38. 实际 BQ76922 官方规格研究：28 项，SLUSE86A；3S 用 VC5–VC4A 顶部电芯。
39. 实际 INA240 器件研究：20 项，SBOS662C；50 V/V、CMRR 120 dB min、Vos ±25 µV max。
40. 实际外围电路草图：`hardware/afe/circuit_architecture.md`。
41. 实际初步 BOM：15 行，料号状态 TBD，未采购/未打样。
42. 实际 SPICE 求解次数：68 次（预算 80 次以内）。
43. 实际 Pytest：257 passed / 0 failed / 0 skipped；`pip check` 无损坏依赖。
44. 实际原始证据文件路径：`results/sensing/run_sensing_20261126_135112_b44fef/` 等 9 个 Run ID，见第 2 节。
45. 可直接用于研发岗简历的真实成果：3S 模拟采集链、68 次真实 SPICE、1000 组容差、校准改善 87–88%、BQ76922/INA240 规格研究，见 portfolio。
46. 当前电路模型局限：理想/教学运放、行为 ADC、均匀独立容差、无 PCB 寄生与温漂，见第 9 节。
47. 尚未验证事项：NTC 自热、真实开线检测、板级校准、批次分布、良率、PCB/EMC，见第 10 节。
48. 三十道模拟电路、运放、ADC 及 BMS 面试题：见第 12 节。

## 12. 30 道模拟电路/运放/ADC/BMS 面试题

1. 单端采样与差分采样有什么区别？
2. 共模电压与差分电压如何定义？
3. 推导四电阻差分放大器公式。
4. 电阻匹配如何影响 CMRR？
5. 运放输入共模范围与输出摆幅有什么区别？
6. 为什么双向电流检测需要零点偏置？
7. 为什么采样电阻不能无限增大？
8. 为什么 RC 滤波会带来延迟？
9. ADC 分辨率与精度有什么区别？
10. 参考电压误差如何影响转换结果？
11. 什么是混叠？如何避免？
12. 为什么数字平均不能消除混叠到 DC 的干扰？
13. NTC 的温度特性如何表示？
14. 零点校准与两点校准分别修正什么？
15. 为什么校准不能消除全部误差？
16. 如何进行工程误差预算？
17. 最坏情况与 RSS 有什么区别？
18. BQ76922 实际功能与教学电路有什么区别？
19. 如何根据 Datasheet 选择 VC 输入 RC？
20. 为什么 3S 顶部电芯接 VC5–VC4A？
21. 未使用 VC 引脚应如何处理？
22. Kelvin 连接解决什么问题？
23. 高侧与低侧电流检测各有什么取舍？
24. 输入偏置电流如何影响高阻采样网络？
25. 如何测量/验证 CMRR？
26. ADC 的 INL 与 DNL 分别是什么？
27. 为什么量化误差最大是 0.5 LSB？
28. 如何设计抗混叠滤波器？
29. NTC 自热如何评估？
30. 如何在简历中诚实区分仿真、Datasheet 规格与硬件实测？

## 13. 电路拓扑（验收数据流）

```text
configs/*.yaml
   ↓
sensing/ 解析模型（ADC/电压/电流/温度）
   ↓
circuits/ 真实 ngspice 网表（VC/差分/分流/NTC/RC）
   ↓
results/<category>/run_<id>/summary.json + *.csv + plots/
   ↓
analysis/ 指标、预算、容差、限值
   ↓
scripts/battery_stage4_demo.py → 16 项 PASS/FAIL
```

## 14. 专业原理（为什么这样验收）

- 先用解析公式给出可解释的期望值，再用真实 ngspice 复验，两者偏差必须可归因。
- 统计误差与最坏情况预算分开：1000 组随机样本回答“典型分布”，线性叠加回答“保证边界”。
- 校准集与验证集分离，避免用验证点反算校准系数。
- 任何饱和、共模超限、开路/短路都必须显式进入状态字段，不能静默丢弃。

## 15. 公式推导（验收指标）

```text
MAE = mean(|x̂−x|)
RMSE = sqrt(mean((x̂−x)²))
worst_case = Σ|e_i|
RSS = sqrt(Σe_i²)
CMRR = 20*log10(|Ad/Acm|)
量化误差上限 = 0.5*LSB
```

## 16. 变量及单位

| 变量 | 含义 | 单位 |
| --- | --- | --- |
| `x` | 真实输入 | V/A/℃ |
| `x̂` | 校准后估计 | V/A/℃ |
| `Ad/Acm` | 差模/共模增益 | V/V |
| `LSB` | ADC 量化步距 | V |
| `e_i` | 单项误差 | 与输入同单位 |
| `RSS` | 均方根合成 | 与输入同单位 |

## 17. 实际器件参数来源

- 电池：第三阶段冻结模型（公开 CALCE 数据辨识）。
- BQ76922：SLUSE86A，28 项规格（`hardware/device_study/bq76922_specifications.csv`）。
- INA240A2：SBOS662C，20 项规格（`hardware/device_study/ina240_specifications.csv`）。
- 运放/ADC/NTC/电阻：教学假设，`configs/*.yaml`，不是商业器件实测。

## 18. 实际核心源码

- `sensing/adc.py`、`sensing/voltage_decoder.py`、`sensing/current_decoder.py`、`sensing/temperature_decoder.py`
- `sensing/calibration.py`、`sensing/measurement_chain.py`
- `circuits/differential_amplifier.py`、`circuits/cell_voltage_sensing.py`、`circuits/current_sensing.py`
- `circuits/rc_filter.py`、`circuits/ntc_sensing.py`、`circuits/afe_frontend.py`
- `analysis/error_budget.py`、`analysis/tolerance_analysis.py`、`analysis/sensing_validation.py`
- `scripts/battery_stage4_demo.py`

## 19. 函数名称及行号

| 名称 | 位置 |
| --- | --- |
| `measure_voltage/current/temperature` | `sensing/measurement_chain.py:36/89/148` |
| `adc_convert` | `sensing/adc.py:80` |
| `four_resistor_output` | `sensing/voltage_decoder.py:18` |
| `fit_zero_calibration` | `sensing/calibration.py:65` |
| `fit_two_point_calibration` | `sensing/calibration.py:77` |
| `run_voltage_tolerance` | `analysis/tolerance_analysis.py:234` |
| `voltage_error_budget` | `analysis/error_budget.py:91` |
| `summarize_checks` | `analysis/sensing_validation.py:46` |
| `main`（综合验收） | `scripts/battery_stage4_demo.py:62` |

## 20. 核心代码逐行解释（验收入口）

```python
composed = {name: find_latest_run(keyword) for name, keyword in DEMO_KEYWORDS.items()}
checks += voltage_checks(...)
checks += current_checks(...)
validation = summarize_checks(checks)
```

- 第 1 行只读取各 demo 已落盘的 `summary.json`，不在验收阶段重算仿真；
- 第 2–3 行按预先固定的限值生成检查项；
- 第 4 行统计 PASS/FAIL，并写入 `validation_summary.json`，保证可追溯。

## 21. 实际运行命令

```powershell
conda run -n kaifa_battery python -m scripts.battery_stage4_demo
conda run -n kaifa_battery python -m pytest tests -q
conda run -n kaifa_battery python -m pip check
```

## 22. 实际图表及原始结果路径

- 单体/差分：`run_sensing_20261126_135112_b44fef/plots/01–03`、`run_sensing_20261126_135218_cb8cf7/plots/04–06`
- 电流：`run_sensing_20261126_135555_720959/plots/09–12`
- RC/ADC：`run_sensing_20261126_135324_f7f014/plots/07–08c`、`run_sensing_20261126_135332_67fb34/plots/12–16`
- NTC：`run_sensing_20261126_135306_def360/plots/17–19`
- 校准/容差：`run_sensing_20261126_135458_c01b86/plots/20–22`、`run_sensing_20261126_135449_d8a6d3/plots/23–28`
- 全链路：`run_sensing_20261126_135542_6eec7a/plots/29–32`
- 综合验收：`results/stage4/run_stage4_20261126_135645_a30da4/validation_summary.json`

## 23. 常见错误（验收视角）

1. 用统计最大误差 3.226 mV 覆盖最坏情况 30.887 mV。
2. 用 0.5 LSB 量化误差代替总采集误差。
3. 用理想运放结果宣称商业运放性能。
4. 用 Python 数学结果替代真实 SPICE 并仍称为仿真。
5. 修改限值或删除失败项来制造 PASS。

## 24. 独立学习练习

1. 从 `validation_summary.json` 找出 16 项检查各自的数据来源。
2. 把电压限值改为 5 mV，观察哪些统计/预算项会失败。
3. 用 20 组样本重跑容差，比较与 1000 组的最大误差差异。
4. 为 NTC 补充耗散系数，估算自热温升并重新判定。

