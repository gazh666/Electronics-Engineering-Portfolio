# 15 3S1P 电池组模型

## 1. 电路拓扑

三节二阶 RC 电芯首尾串联：

```text
 gnd ─ CELL1 ─ CELL2 ─ CELL3 ─ pack+
          │       │       │
       (R0,R1C1,R2C2 各一节，结构相同)
```

串联时所有电芯流经同一电流：

```text
Icell1 = Icell2 = Icell3 = Ipack
```

## 2. 专业公式

```text
Vpack = Vcell1 + Vcell2 + Vcell3
Ppack = Vpack · Ipack
Ploss,pack = Ipack²·(R0,1+R0,2+R0,3) + Σ(Vj,k²/Rj,k)
```

串联容量关系：

```text
Qpack(Ah) = Qcell(Ah)          # 串联不增加 Ah
Epack(Wh) = 3 · Qcell · Vcell  # 能量近似三倍
```

串联内阻：

```text
R0,pack = R0,1 + R0,2 + R0,3 = 0.09 Ω
```

## 3. 变量与单位

| 符号 | 含义 | 单位 |
| --- | --- | --- |
| Vcell,k | 第 k 节端电压 | V |
| Vpack | 电池组端电压 | V |
| R0,pack | 串联总欧姆内阻 | Ω |
| SOCk | 第 k 节 SOC | 0–1 |

## 4. 公式推导

串联回路电流相同，基尔霍夫电压定律给出组端电压为各节端电压之和。每节内部仍满足二阶 RC 关系：

```text
Vcell,k = OCV(SOCk) - I·R0,k - V1,k - V2,k
```

因此初始一致时 `Vpack = 3×(3.8 - 0.06) = 11.22 V`；60 s 后约 `3×3.683056 = 11.049 V`。

## 5. 适用条件

- 仅建模串联主回路，不含均衡电路、继电器、熔断器与采样线束。
- 终止事件只是“模型运行边界”，不是真实 BMS 保护动作。
- 参数来源仍为教学假设。

## 6. 实际代码与核心函数

| 功能 | 路径 | 函数/类 |
| --- | --- | --- |
| 单节模型 | `battery_models/battery_pack.py` | `PackCellModel` |
| 串联电池组 | `battery_models/battery_pack.py` | `SeriesBatteryPack` |
| 一致电芯构造 | `battery_models/battery_pack.py` | `build_uniform_pack` |
| 不一致电芯构造 | `battery_models/battery_pack.py` | `build_inconsistent_pack` |
| 组仿真 | `battery_models/battery_pack.py` | `simulate_series_pack` |
| 一致性指标 | `analysis/pack_consistency.py` | `consistency_metrics` |
| 恒阻/恒功率 | `simulations/power_delivery.py` | `simulate_constant_resistance`、`simulate_constant_power` |

## 7. 关键代码逐行解释

```python
def step(self, current_a, dt_s):
    for cell in self.cells:          # 同一电流同时推进所有电芯
        cell.step(current_a, dt_s)
```

组端与一致性：

```python
voltages = pack.cell_voltages(current_value)
pack_voltage = float(sum(voltages))
delta = max(voltages) - min(voltages)
```

终止定位：逐节计算 SOC 与端电压，取最小越过比例的电芯作为首个越限电芯，并按该比例插值停止时刻。

## 8. 实际运行命令

```powershell
conda run -n kaifa_battery python -m scripts.battery_pack_demo
conda run -n kaifa_battery python -m scripts.pack_inconsistency_demo
```

## 9. 真实结果：一致电芯基准

运行编号：`battery_pack_20261126_122903_614806`；对应真实 ngspice 三串运行：`spice_ecm_20261126_122903_5a36ba`。

| 指标 | 实际值 |
| --- | --- |
| 开路组电压 | 11.400000 V |
| 2 A 接入后 | 11.220000 V |
| 60 s 放电结束（69.9 s 采样） | 11.049169 V |
| 组电压最小值 | 11.049169 V |
| 电压求和误差 | 0.0 V |
| 一致电芯最大压差 | 0.0 V |
| 一致电芯最大 SOC 差异 | 0.0 |
| 三节末端 SOC | 0.583333 |

Python 与 ngspice 三串对照：MAE 0.800 µV、最大误差 3.644 µV（3798 个有效点）。

## 10. 真实结果：电芯不一致性

运行编号：`battery_pack_20261126_122915_bee8ed`（汇总），使用教学 OCV 查表、2 A 恒流、最长 2500 s。

| 实验 | 最大压差 (V) | 最大 SOC 差异 | 首个越限电芯 | 停止时间 (s) | 停止原因 |
| --- | --- | --- | --- | --- | --- |
| A SOC 不一致 | 0.407143 | 0.200000 | cell3 | 1666.29 | cell_voltage_lower_limit |
| B 容量不一致 | 0.197000 | 0.056286 | cell3 | 1823.66 | cell_voltage_lower_limit |
| C 内阻不一致 | 0.060000 | 0.000000 | cell3 | 1964.57 | cell_voltage_lower_limit |
| D 综合不一致 | 0.468857 | 0.244571 | cell3 | 1444.11 | cell_voltage_lower_limit |

终止原因是单体端电压先到 3.0 V，而不是 SOC 先到 0。这正是“电池组端电压正常但单体已经欠压”的典型现象。

## 11. 真实结果：恒阻与恒功率负载

运行编号：`battery_pack_20261126_122903_614806`，时长 1800 s，3S 一致电芯，ZOH 步长 0.1 s 与 0.05 s 对照。

| 负载 | 初始电流 (A) | 末端电流 (A) | 初始组压 (V) | 末端组压 (V) | 平均功率 (W) | 步长细化电压差 (V) | 步长细化电流差 (A) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 恒阻 5.7 Ω | 1.968912 | 1.933842 | 11.222798 | 11.022901 | 21.3323 | 1.02e-6 | 1.80e-7 |
| 恒功率 11.1111 W | 0.982276 | 0.991474 | 11.311595 | 11.206663 | 11.1111 | 2.73e-7 | 2.40e-8 |

恒功率目标按 `10 W / 0.9 = 11.111 W` 计算，其中 0.9 是独立教学假设，未调用 PowerLab 的真实 Buck 开关模型。

## 12. 为什么串联不增加 Ah，但增加 Wh

串联电流相同，因此通过的总电荷量不变，Ah 容量不变；但电压叠加，所以能量 `Wh = Ah × V` 近似三倍。工程上常说“3S 提高电压与功率能力”，而不是“提高容量”。

## 13. 为什么必须监测单体差分电压

组端电压是三节之和，某一节欠压会被另外两节掩盖。一旦欠压电芯继续放电，会加速老化甚至反极。因此 BMS 必须采集每节电压并计算最大压差、SOC 差异，而不是只看组端总压。

## 14. 常见错误

- 把串联后的 Ah 写成 3 倍。
- 把模型停止事件描述为“BMS 保护动作”。
- 用组端电压判断一致性。
- 忽略内阻不一致导致的动态压差，只在静置时比较。

## 15. 独立练习

1. 计算三节 R0 分别为 30/40/60 mΩ 时 2 A 下的组端压降。
2. 说明容量不一致为什么会导致 SOC 差异扩大。
3. 设计一个 4S 配置并重算组端电压与总内阻。

## 16. 面试题

1. 串联与并联电池组分别如何影响电压、容量与内阻？
2. 电芯不一致性有哪些来源？
3. 被动均衡与主动均衡的区别是什么？
4. 如何用差分电压与 SOC 估计判断不一致性？
5. 为什么组端电压正常仍可能发生过放？
