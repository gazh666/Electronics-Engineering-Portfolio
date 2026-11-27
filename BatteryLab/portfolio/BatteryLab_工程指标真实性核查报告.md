# BatteryLab 工程指标真实性核查报告

- 审计运行：`results/resume_audit/run_20261126_175610`
- 执行日志：[audit.log](file:///BatteryLab/results/resume_audit/run_20261126_175610/audit.log)
- 复算结果：[recomputed_metrics.json](file:///BatteryLab/results/resume_audit/run_20261126_175610/recomputed_metrics.json)
- 证据索引：[evidence_index.csv](file:///BatteryLab/results/resume_audit/run_20261126_175610/evidence_index.csv)
- 审计脚本：[audit_resume_metrics.py](file:///BatteryLab/scripts/audit_resume_metrics.py)

本报告回答一个问题：简历里打算写的每个数字，是否真的能从原始结果复算出来，以及它的适用边界是什么。

---

## 一、审计方法

1. **只读**：脚本只读取 `results/` 下历史 `run_*` 目录，不写入、不覆盖任何历史结果。
2. **原始数据优先**：模型误差从 `residuals.csv.gz` 逐点复算；采集误差从 1000 组 `*_sample_metrics.csv` 复算；系统级指标从 484,142 点 `waveform.csv` 重新积分。
3. **严格时间加权**：`time_average` 使用梯形积分；效率用能量比 `∫Pout dt / ∫Pin dt`，并用平均电压×平均电流做交叉核对。
4. **同条件才比较**：只有同一数据集、同一评价区间、同一定义的结果才计算改善比例；否则标记 `NOT_COMPARABLE`。
5. **缺证据不估算**：无法复算或无原始“前/后”记录的指标直接写 `NOT_VERIFIED`。

时间积分实现：

```python
def time_average(t, x):
    ...
    return float(integrate(x, t) / (t[-1] - t[0]))

def mean_power(t, voltage, current):
    return time_average(t, np.asarray(voltage) * np.asarray(current))
```

---

## 二、复算一致性

| 数据块 | 记录值 | 独立复算 | 相对差 | 结论 |
|---|---|---|---|---|
| 模型 21 组（7 工况 × 3 模型）RMSE | `validation_summary.csv` | `residuals.csv.gz` 逐点 | 0.0000% | 完全一致 |
| 电压采集 MAE / 最大误差 | `summary.json` | 1000 组样本均值/最大值 | 2.7e-13 / 2.3e-12 | 一致 |
| 电流采集 MAE / 最大误差 | `summary.json` | 1000 组样本 | 5.9e-12 / 2.2e-12 | 一致 |
| 温度采集 MAE / 最大误差 | `summary.json` | 1000 组样本 | 5.3e-12 / 5.2e-11 | 一致 |
| 联合 SPICE 输出电压 | 4.996827 V | 4.996228 V（8.4–12 ms 时间加权） | 0.0120% | 一致 |
| 联合 SPICE 纹波 | 28.9783 mVpp | 28.9783 mVpp（同窗口峰峰值） | 2.9e-6% | 一致 |
| 联合 SPICE 效率 | 93.8274%（算术平均口径） | 93.6856%（能量比口径） | 0.1510% | 口径差，均保留 |
| 均衡终值压差 | 10.470 mV | 10.470 mV（CSV 末行） | 0 | 一致 |

结论：历史记录值没有发现“配置目标值冒充输出值”的情况；唯一需要说明的是效率口径——原始 `_window_metrics` 用算术平均，审计用能量比，两者相差 0.15 个百分点，报告中同时给出，不择优。

---

## 三、本次发现并纠正的问题

### 3.1 OCV 跨样品差字段单位错误（已在审计中纠正）

原始 `ocv/summary.json` 字段名为 `cross_cell_max_difference_mv`，但数值 `0.0232335` 实际是 **V**。若直接当 mV 会写成 0.023 mV，缩小 1000 倍。审计按 23.234 mV 计，与阶段文档“跨样品最大 23.23 mV”一致。

### 3.2 保护“2.5 ns 电流切断”是行为源伪迹

`protection_20261126_173438_1e53b2` 记录：

- 故障注入：12.000 ms
- 电池电流“被抑制”：12.0000025 s → 2.5 ns
- 栅极关断指令：12.010 ms → 故障后 10 µs
- 输入电压衰减：12.209 ms → 指令后 199 µs
- 输出跌出稳压：12.470 ms → 指令后 460 µs

2.5 ns **早于** 10 µs 的栅极指令，物理上不可能由 MOSFET 关断产生。它来自行为电流源在故障时刻的钳位。因此：

- `P04 = NOT_VERIFIED / ARTIFACT`，不得写成“2.5 ns 切断”。
- 可报告的真实时序是：故障→栅极指令 10 µs、指令→输入衰减 199 µs、输出维持 460 µs。
- 真实 MOSFET 关断时间仍然是 `NOT_VERIFIED`（教学级模型，无器件级开关波形）。

### 3.3 长期放电与老化全部终止于边界，不是完整续航

16 个放电工况状态为 `BATTERY_MODEL_LIMIT` 4 个、`OUT_OF_VERIFIED_DOMAIN` 12 个；3 个老化场景也全部 `OUT_OF_VERIFIED_DOMAIN`。运行时间 0.326–6.588 h 是“直到离开已验证输入域”的时间，不是“直到保护切断”的续航。审计已将 `L01/L02` 的验收状态改为 `LIMITED`。

### 3.4 最坏情况误差预算仍是 RISK

统计 1000 组通过（A01/A03）不等于最坏情况保证：

- 电压最坏预算 30.887 mV > 10 mV 目标
- 电流最坏预算 37.736 mA > 20 mA 目标

因此 `A13` 的验收状态为 `RISK`，不能因为统计通过就宣称“满足最坏情况精度”。

### 3.5 真实数据与合成数据必须分开

- `E07` 真实容量 SOH：只有 1 次完整循环，保持率 100%，没有老化含义。
- `E08` 100 循环 90.1%：是合成线性衰减，不是实测。
- `E05` 静置校正：合成夹具（初始 −5 pp），25 次校正后 −0.0189 pp；真实 CALCE 连续动态段校正次数为 0，不能外推。

### 3.6 KiCad 未安装，硬件交付 BLOCKED

阶段 8 的 `blocked_items.json` 明确：ERC、DRC、Gerber、钻孔、STEP、封装验证均因本机无 KiCad 而 BLOCKED。已完成的是数据手册级引脚映射（BQ76922 33 行、BQ24610 25 行）、BOM（51 行）、降额（13 项）、选型对比（MOSFET 4 款）与设计评审。**不得宣称已完成原理图/PCB 或通过 ERC/DRC。**

---

## 四、分阶段真实性结论

| 阶段 | 可对外声称 | 不可声称 |
|---|---|---|
| 1 | 使用 CALCE 公开数据完成加载与 PyBaMM 交叉 | 数据为本人采集 |
| 2 | Rint/一阶/二阶 ECM 与 3S 模型、SPICE 对照 | 商业电芯实测参数 |
| 3 | 一阶 RC 独立验证 22.385 mV（仅 FUDS 50/80）；Rint 26.705 mV；改善 16.18% | 全工况都达标；US06/BJDST 一阶 RC 为 40.652–53.599 mV（FUDS 80% 空电区 FAIL） |
| 4 | 两点校准后统计电压 3.226 mV、电流 3.004 mA | 最坏情况达标；真实 ADC 芯片精度 |
| 5 | 10/10 故障工况、41/41 验收、均衡 130→10.47 mV | 2.5 ns 物理切断；真实保护 IC 实测 |
| 6 | CC 误差 1.09 mA、CV 误差 13.5 mV、效率 98.01%、PM 107.22° | 软启动/PI/抗饱和有前后改善（无对照） |
| 7 | SOC RMSE 1.825 pp、最大 3.087 pp、收敛 479.6 s | 真实 SOH 老化；真实 SOC 直接实测 |
| 8 | 引脚/网络/BOM/降额/选型核查 | 原理图/PCB/ERC/DRC/Gerber 完成 |
| 9 | 联合 SPICE 4.996 V、28.978 mVpp、93.686%、残差 0.00283% | 完整续航；双向硬件在环 |
| 10 | 未执行 | 最终交付已完成 |

---

## 五、NOT_VERIFIED 清单（正式）

| 编号 | 指标 | 原因 |
|---|---|---|
| P04 | 电池电流物理抑制时间 2.5 ns | 早于栅极指令，行为源伪迹 |
| C06 | 软启动前后过冲改善比例 | 无“无软启动”同条件波形 |
| C07 | PI 优化前后动态性能 | 仅保留最终参数与整定网格 |
| C08 | 抗积分饱和前后恢复时间 | 无保留的前后对照 |
| H05 | 原理图/PCB/ERC/DRC/Gerber/STEP | 本机无 KiCad |
| E07 | 真实容量老化 / 内阻增长 | 仅 1 次完整循环 |
| L01/L02 | 完整续航 | 全部终止于模型/域边界（LIMITED，非 NOT_VERIFIED） |
| — | 真实硬件效率/温升/EMI | 未制板、未采购 |

另有 `E08` 为 VERIFIED（合成），已单独标注。

---

## 六、禁止在简历/面试中出现的表述

1. “实测电池内阻 77 mΩ” → 应为“基于 CALCE 公开数据辨识的 R0”。
2. “AFE 采集精度 0.87 mV” → 应为“SPICE+行为 ADC 的 1000 组容差统计 RMSE”。
3. “保护响应 2.5 ns” → 禁止；只能写“仿真中故障→栅极指令 10 µs”。
4. “均衡实测降低 91.95%” → 应为“ECM 长时仿真 + 单次 SPICE 支路校核”。
5. “充电效率 98% 实测” → 应为“开关级 SPICE 仿真效率”。
6. “完成了 PCB 设计” → 禁止；只能写“完成选型、引脚/网络/BOM/降额核查，PCB 因环境未制板”。
7. “降低了电池老化速度” → 禁止；只能写“完成 SOH 参数敏感性分析”。
8. “3S 硬件在环联合仿真” → 禁止；是同一网表的联合 SPICE + 真实 TestLab 判定调用。

---

## 七、审计产物

| 文件 | 内容 |
|---|---|
| `audit.log` | 执行日志、每段通过/失败 |
| `recomputed_metrics.json` | 全部复算值与分区块结果 |
| `evidence_index.csv` | 80 行 × 16 字段证据表 |
| `before_after.csv` | 有前后数值的对照行 |
| `config_snapshot.json` | 环境、输入运行、口径定义 |
| `model_accuracy_recompute.csv` | 21 组模型 RMSE/MAE/最大值复算 |
| `model_fuds_average.csv` | FUDS 两工况平均 |
| `balancing_control.json` | 无均衡同条件对照 |
| `balancing_recheck.json` | 均衡同条件重跑 |
| `simulation_counts.json` | 各阶段 SPICE/工况计数 |

全量回归：`550 passed`（`kaifa_battery`）。
