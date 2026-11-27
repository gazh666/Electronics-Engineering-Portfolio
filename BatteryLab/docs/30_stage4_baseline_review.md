# 30 第四阶段开发基线核查

## 1. 电路拓扑（系统分层）

```text
真实 ngspice 3S 电池模型（复用第三阶段冻结参数）
        │
        ├── 单体电压 3.6/3.8/4.0 V → 3S 节点 N0..N3
        ├── 组端电流（充电/放电方向）
        └── 外部给定温度
                ↓
        模拟采集网络（差分放大 / RC / 分流+INA240 / NTC）
                ↓
        真实 SPICE 输出
                ↓
        ADC 行为模型（12 bit, 3.3 V）
                ↓
        电压/电流/温度反演 + 校准
                ↓
        误差指标与限值检查
```

## 2. 专业原理

第四阶段不是重新辨识电池，而是在**已验证的第三阶段电池模型**上增加“采集链路”。
因此必须先固定电池模型、容量、参数来源与可用数据范围，再讨论 AFE 误差。

## 3. 公式推导（基线量）

3S 节点：

```text
N0 = 0
N1 = Vcell1
N2 = Vcell1 + Vcell2
N3 = Vcell1 + Vcell2 + Vcell3
Vcell_k = N_k - N_{k-1}
```

冻结一阶 RC 参数关系：

```text
tau1 = R1*C1
```

## 4. 变量及单位

| 量 | 数值 | 单位 | 来源 |
| --- | --- | --- | --- |
| 电芯 | INR18650-20R | — | 第三阶段模型 |
| 实测容量 | 2.028083 | Ah | CALCE SP2 积分 |
| R0 | 77.068 | mΩ | 第三阶段辨识 |
| R1 | 22.845 | mΩ | 第三阶段辨识 |
| C1 | 788.6 | F | 由 τ1/R1 派生 |
| τ1 | 18.016 | s | 第三阶段辨识 |
| 单体实验范围 | 2.4034–4.2001 | V | 第三阶段 BMS 参考表 |
| 电流实验范围 | −2.142–+4.002 | A | 第三阶段 BMS 参考表 |
| 组端标称 | 11.1 | V | 3S |

## 5. 实际器件参数来源

- 电池模型：`data/identified/` 冻结参数，**公开 CALCE 实验数据辨识，不是本人硬件实测**。
- ngspice：本机 `ngspice` 34，PySpice 1.5，Conda 环境 `kaifa_battery`。
- BQ76922：TI `references/datasheets/bq76922_datasheet.pdf`，SLUSE86A。
- INA240：本次新增下载 `references/datasheets/ina240_datasheet.pdf`，SBOS662C。
- 教学 ADC、NTC、容差：`configs/*.yaml`，标记 `educational_assumption`。

## 6. 实际核心源码

- `configs/afe_config.yaml`
- `configs/adc_config.yaml`
- `configs/current_sensing.yaml`
- `configs/ntc_config.yaml`
- `configs/sensing_tolerances.yaml`
- `configs/stage4_validation.yaml`
- `scripts/stage4_common.py`

## 7. 函数名称及行号

| 名称 | 位置 | 作用 |
| --- | --- | --- |
| `load_afe_config` | `sensing/config.py:70` | 加载并校验 AFE 配置 |
| `afe` | `scripts/stage4_common.py:28` | 脚本统一入口 |
| `amplifier_config` | `scripts/stage4_common.py:32` | 构造差分放大器配置 |
| `current_sense_config` | `scripts/stage4_common.py:36` | 构造电流采集配置 |
| `adc_settings` | `scripts/stage4_common.py:53` | 构造 ADC 配置 |
| `limits` | `scripts/stage4_common.py:95` | 加载预先固定的限值 |

## 8. 核心代码逐行解释

```python
def afe() -> dict[str, Any]:
    return load_afe_config()          # 六份 YAML 的根配置，含 3S/量程/增益/ADC/NTC
```

- `load_afe_config()` 不仅读文件，还检查有限性、正性、范围与单位一致性；
- 任何缺失字段都会在运行前抛出 `ConfigError`，避免脚本用默认值悄悄跑出结果。

## 9. 实际运行命令

```powershell
conda run -n kaifa_battery python -m scripts.verify_environment
conda run -n kaifa_battery python -m scripts.battery_stage4_demo
```

## 10. 实际图表及原始结果路径

- 基线核查：`results/stage4/run_stage4_20261126_135645_a30da4/`
- 3S 节点：`results/sensing/run_sensing_20261126_135112_b44fef/plots/01_3s_node_voltages.png`
- 完整链路：`results/sensing/run_sensing_20261126_135542_6eec7a/plots/29_afe_3s_waveform.png`
- 汇总验收：`results/stage4/run_stage4_20261126_135645_a30da4/validation_summary.json`

## 11. 常见错误

1. 把第三阶段辨识参数说成“真实 BQ76922 芯片参数”。
2. 把 3S 教学节点 N0–N3 直接映射为 BQ76922 的 VC0–VC3。
3. 把公开 CALCE 数据说成本人电池实验。
4. 把理想运放、行为 ADC 说成商业器件实测。
5. 用第三阶段二阶 RC 的 `tau2` 边界值做 AFE 动态设计而不加说明。

## 12. 独立学习练习

1. 从 `data/identified/` 找出 R0/R1/C1 的原始文件并核对单位。
2. 把 `afe_config.yaml` 的单体上限改为 4.3 V，观察哪些限值检查会变化。
3. 画出“电池模型 → 采集 → ADC → 校准”的数据流，并标注每段的误差来源。

## 13. 面试问题

1. 为什么采集电路验证可以先固定电池模型？
2. 第三阶段参数辨识的不确定度会如何影响第四阶段结论？
3. 教学模型与真实 AFE 的边界应该怎样在简历中表述？
