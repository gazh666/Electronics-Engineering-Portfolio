# 24 时间步长与固定温度对照

## 1. 时间步长统计（Model E，真实 5 ms）

运行：`conda run -n kaifa_power python -m scripts.nonideal_buck_demo`
结果：`results/nonideal_buck/run_20261125_131421_21b3c28d/metadata.json`。

| 指标 | 实测 |
| --- | --- |
| 采样点 | 221,247 |
| 输出步长 | 50 ns |
| 配置最大内部步长 | 25 ns |
| 实际最大步长 | 25.000 ns |
| 实际最小步长 | **1.06e-16 s** |
| 平均步长 | 22.60 ns |
| 中位步长 | 25.00 ns |
| 最大步长是否遵守 | True |
| 非均匀采样 | True |

结论：ngspice 严格遵守 25 ns 上限；开关跳变处会自动压到 1e-16 s 量级以保证收敛。
这说明“采样点数远多于 5 ms / 50 ns”不是异常，而是求解器在开关边沿加密。

## 2. 步长敏感性（1 ms 瞬态，Model E）

运行：`scripts/buck_stage4_demo` 内的 `_timestep_rows`。
注意这是 1 ms 瞬态，输出尚未建立到最终稳态，只用于比较不同步长在同一时间窗内的一致性。

| 最大步长 | 状态 | 采样点 | 平均步长 | 末端 Vout | 末端纹波 |
| --- | --- | --- | --- | --- | --- |
| 50 ns | success | 24,594 | 40.66 ns | 4.600605 V | 51.320 mV |
| 25 ns | success | 44,149 | 22.65 ns | 4.600076 V | 51.274 mV |
| 12.5 ns | **failed** | – | – | – | – |

- 50 ns 与 25 ns 的 Vout 相差 **0.53 mV（0.011 %）**，纹波相差 0.046 mV，说明 25 ns 已足够。
- 12.5 ns 在 1 ms 窗口内触发 `timestep too small`，属于 ngspice 在个别采样点的数值偶然失败，
  不代表 12.5 ns 物理上不可用；脚本如实记录为 `failed`，没有伪造结果。
- 全部 5 ms 模型运行都记录 `convergence_retries`；Model E 默认 25 ns 一次通过，无重试。

结果文件：`results/buck_stage4/run_20261125_132536_adff1fab/timestep_sensitivity.csv`。

## 3. 固定温度对照

运行：`conda run -n kaifa_power python -m scripts.temperature_demo`
（Model E，25 / 50 / 75 °C，每个温度独立完整 5 ms）。

| 温度 | Vout | 纹波 | 功率级效率 | MOSFET 损耗 | 二极管损耗 | DCR 损耗 | 总损耗 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 25 °C | 4.668158 V | 19.042 mV | 92.9356 % | 51.68 mW | 434.15 mW | 176.04 mW | 673.18 mW |
| 50 °C | 4.650961 V | 19.090 mV | 92.6427 % | 45.46 mW | 466.20 mW | 174.77 mW | 697.77 mW |
| 75 °C | 4.633079 V | 19.138 mV | 92.2470 % | 49.97 mW | 497.48 mW | 173.45 mW | 732.24 mW |

结果目录：`results/nonideal_buck/run_20261125_131549_efbd1daf/temperature_summary.csv`。

### 3.1 如何解读

- 温度升高时二极管损耗从 434 mW 升到 497 mW，是总损耗上升的主因；效率下降 0.69 个百分点。
- `Level 1` MOSFET 没有温度参数，其参数本身不随温度变化；MOSFET 损耗的 45–52 mW 波动
  来自工作点（占空比固定、Vout 下降导致电流与电压波形变化），**不能**解释为真实温度系数。
- DCR 损耗略降，同样是工作点变化的结果，不是铜电阻的温度特性。
- 温度为**求解器固定温度**，不是自热：没有热阻网络，没有 `损耗 → 温升 → 参数` 的反馈。

## 4. 限制

1. 12.5 ns 失败说明数值收敛具有工况偶然性；本阶段通过重试机制解决，而不是修改器件参数掩盖。
2. 1 ms 步长敏感性不是稳态比较，不能用于给出最终效率误差界。
3. 固定温度不等于结温，不能用于热设计。
4. 本阶段没有做温度循环、热失控或封装模型。

## 5. 复现命令

```powershell
$env:PYTHONPATH='PowerLab'
conda run -n kaifa_power python -m scripts.nonideal_buck_demo
conda run -n kaifa_power python -m scripts.temperature_demo
conda run -n kaifa_power python -m scripts.buck_stage4_demo
```
