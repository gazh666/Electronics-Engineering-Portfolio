# 39 BQ76922 外围电路应用设计

> 依据 TI BQ76922 数据手册 **SLUSE86A（2022-04，2024-04 修订）**。
> 器件规格表见 `hardware/device_study/bq76922_specifications.csv`；
> 引脚映射见 `hardware/afe/pin_mapping.csv`；架构见 `hardware/afe/circuit_architecture.md`。

## 1. 电路拓扑

```text
3S 电芯组
  CELL3+ ──► VC5 (pin2)
  CELL3− ──► VC4A/VC4B (pin3/4, PCB 短接)
  CELL2+ ──► VC2 (pin7)
  CELL2− ──► VC1 (pin8)
  CELL1+ ──► VC1 (pin8)
  CELL1− ──► VC0 (pin9) ──R/C── VSS (pin10)
  VC3A/VC3B (pin5/6) ── 短接到 VC2（未用通道）

PACK− ──[10 mΩ]── SRP/SRN (pin11/12)
NTC ── TS1 (pin13)
BAT (pin1) ◄── 组端+
REG18 (pin15) ── 2.2 µF ── VSS
REG1 (pin22) ── 3.3 V ── 2.2 µF ── VSS
REGIN (pin23) ◄── ≥4.1 V
SCL/SDA (pin17/18) ── 2.2 kΩ 上拉
```

## 2. 专业原理

BQ76922 是 3S–5S 电池监测/保护 AFE，内部包含多路电压 ADC、库仑计、温度测量、保护逻辑、
高侧 NFET 驱动、可编程 LDO 与均衡开关。外围设计的核心是：

1. 把每节电芯正确接到 VC 差分对；
2. 给 VC/TS/SRP/SRN 提供符合手册的 RC 网络；
3. 保证 BAT/REG18/REG1 供电与去耦；
4. 处理未用 VC 引脚；
5. 规划采样地/功率地与 Kelvin 连接。

## 3. 公式推导（选型计算）

单体输入 RC 的截止频率：

```text
fc = 1/(2π*(2R)*C)
```

取 R=47 Ω、C=0.22 µF：

```text
fc = 1/(2π*94*0.22e-6) = 7696 Hz
```

REG18 去耦：手册推荐 1.8–22 µF，取 2.2 µF。

分流电阻与库仑计：

```text
Vshunt = I*Rshunt
```

10 mΩ、±2.5 A → ±25 mV，位于库仑计 ±200 mV 输入范围内。

## 4. 变量及单位

| 量 | 数值 | 单位 | 依据 |
| --- | --- | --- | --- |
| 单体精度 25 ℃ | ±5 | mV | p.7 |
| 单体精度 0–60 ℃ | ±10 | mV | p.7 |
| 单体精度 −40–85 ℃ | ±15 | mV | p.7 |
| VC 输入 R | 20–100 | Ω | p.7 |
| VC 输入 C | 0.1/0.22/1 | µF | p.7 |
| REG18 | 1.8 | V | p.10 |
| REG1 3.3 V 档 | 3.0–3.6 | V | p.11 |
| 库仑计输入 | ±200 | mV | p.11 |
| 均衡电阻 | 15/28/46 | Ω | p.14 |
| 工作温度 | −40–85 | ℃ | p.7 |

## 5. 实际器件参数来源

| 项目 | 来源 | 页码 |
| --- | --- | --- |
| VC 引脚定义 | SLUSE86A Table 5-1 | p.3–4 |
| 3S 真实 VC 映射 | Table 8-3 | p.62 |
| 未用 VC 处理 | §7.5.1.2 / Table 8-3 | p.29–30 / p.62 |
| 单体精度 | §6.3 | p.7 |
| REG18 | §6.10 | p.10 |
| REG1 | §6.12 | p.11 |
| 库仑计 | §6.14 | p.11–12 |
| ADC 转换时间 | §6.18 | p.14 |
| 均衡 | §6.19 | p.14 |

**没有 BQ76922 内部晶体管级模型；本设计只做器件级外围研究。**

## 6. 实际核心源码/产物

- `hardware/afe/circuit_architecture.md`
- `hardware/afe/design_calculations.md`
- `hardware/afe/pin_mapping.csv`
- `hardware/afe/preliminary_bom.csv`
- `hardware/device_study/bq76922_specifications.csv`
- `hardware/device_study/ina240_specifications.csv`

## 7. 函数/文件与行号

| 名称 | 位置及行号 | 作用 |
| --- | --- | --- |
| `circuit_architecture.md` | `hardware/afe/circuit_architecture.md:1-82` | 功能草图与信号流 |
| `design_calculations.md` | `hardware/afe/design_calculations.md:1-111` | 分压/RC/电流/NTC 计算 |
| `pin_mapping.csv` | `hardware/afe/pin_mapping.csv:1-33` | 32 引脚逐脚连接 |
| `preliminary_bom.csv` | `hardware/afe/preliminary_bom.csv:1-16` | 15 行器件初选 BOM |
| `bq76922_specifications.csv` | `hardware/device_study/bq76922_specifications.csv:1-29` | 28 项规格 |
| `ina240_specifications.csv` | `hardware/device_study/ina240_specifications.csv:1-21` | 20 项规格 |

## 8. 核心设计逐条解释

### 8.1 BAT 供电路径

BAT（pin1）接组端+，经 100 Ω + 1 µF/0.1 µF 去耦到 VSS。BAT 绝对最大 VSS+60 V，
推荐工作 4.7–27.5 V（p.7），3S 的 7.5–12.75 V 合规。

### 8.2 3S 的真实 VC 映射（最容易出错）

官方 Table 8-3 明确：**cell 1、2、5 必须接真实电芯**，即：

- cell1：VC1–VC0（pin8–pin9）
- cell2：VC2–VC1（pin7–pin8）
- cell3：**VC5–VC4A**（pin2–pin3/4）

因此不能把 N0/N1/N2/N3 顺序映射成 VC0/VC1/VC2/VC3。顶部电芯必须走 VC5 与 VC4A，
VC4A 与 VC4B 在 PCB 上短接。

### 8.3 未用 VC 引脚

VC3A/VC3B（pin5/6）在 3S 中未用。官方允许两种处理：

1. 短接到相邻 VC 引脚（本设计短到 VC2）；
2. 用于互连电阻测量或 Kelvin 连接（需 R+C）。

不允许悬空，也不允许把所有未用高压引脚直接接地。每个 VC 引脚必须接到
“相邻 VC / 真实电芯 / 互连电阻”三者之一（p.62）。

### 8.4 VC0 与 VSS

VC0 是第一节电芯负端，必须经 R+C 接到 VSS（pin10），不能直接把 VC0 与 VSS 大面积短接，
否则均衡电流与地电流会污染采样。

### 8.5 SRP/SRN 与 Kelvin

SRP/SRN 接 10 mΩ 分流电阻两端，各串 100 Ω、差分 0.1 µF。Kelvin 走线从焊盘内侧单独引出。
库仑计输入范围 ±200 mV（p.11），10 mΩ 对应 ±20 A 理论量程。

### 8.6 TS1/TS2

TS1 接 NTC 分压，上拉到 REG18/REG1。TS2 可作第二温度点或 SHUTDOWN 唤醒；
不用时按 Table 8-3 悬空或接 VSS。

### 8.7 基准与 LDO

- REG18 是内部 1.8 V，只放 2.2 µF，不对外供电（p.10）。
- REG1 可编程 1.8/2.5/3.0/3.3/5.0 V，3.3 V 档要求 REGIN ≥4.1 V，最大 45 mA（p.11）。
- VREF1 用于电压 ADC，VREF2 用于 LDO/库仑计（p.11 脚注）。

### 8.8 I2C

SCL/SDA 为 400 kHz I2C，各用 2.2 kΩ 上拉到 REG1 3.3 V。上拉电源必须与 AFE 同域，
避免关机反灌。

### 8.9 开线检测

本设计保留 VC 输入 RC，使 AFE 内部电流源能把开线节点拉偏。官方开线检测功能可识别
VC 引脚异常；本阶段**没有真实开线实验**，仅验证 NTC 开路/短路状态，硬件开线检测为 `NOT_VERIFIED`。

### 8.10 采样地/功率地

采样地与功率地单点连接；分流电阻 Kelvin 走线不承载负载电流；VC/TS/SRP/SRN 与
CHG/DSG/CP1/PACK+ 开关节点保持间距，禁止平行长走线。

## 9. 实际运行命令

本任务是文档/CSV 产物，无独立仿真入口。相关验证命令：

```powershell
conda run -n kaifa_battery python -m scripts.afe_system_demo
conda run -n kaifa_battery python -m scripts.battery_stage4_demo
```

## 10. 实际图表及原始结果路径

- 架构与引脚：`hardware/afe/circuit_architecture.md`、`hardware/afe/pin_mapping.csv`
- 规格：`hardware/device_study/bq76922_specifications.csv`
- BOM：`hardware/afe/preliminary_bom.csv`
- 3S 采集波形：`results/sensing/run_sensing_20261126_135542_6eec7a/plots/29_afe_3s_waveform.png`

## 11. 常见错误

1. 把 N0–N3 直接映射成 VC0–VC3，忽略 VC5–VC4A 顶部电芯。
2. 把 VC3A/VC3B 悬空或直接接地。
3. 把 VC4A 与 VC4B 分别接不同网络，未在 PCB 短接。
4. 把 BQ76922 的 ±5 mV 精度说成 3.3 V/4096 的量化误差。
5. 把 REG18 当外部 1.8 V 电源使用。
6. 把教学 12 位 ADC 与芯片 16 位 ADC 的分辨率/转换时间混用。

## 12. 独立学习练习

1. 画出 4S/5S 时 VC 引脚应如何连接。
2. 计算 3S 顶部电芯 4.25 V 时 VC5 对 VSS 的电压。
3. 解释为什么 VC3A/B 可以短接到 VC2 而不是必须接地。
4. 根据 REG1 45 mA 限额，列出允许的外部负载。

## 13. 面试问题

1. BQ76922 实际功能与教学采集电路有什么区别？
2. 如何根据 Datasheet 选择 VC 输入 RC？
3. 为什么 3S 的顶部电芯接 VC5–VC4A？
4. 未使用的 VC 引脚应该如何处理？
5. 采样地与功率地为什么要单点连接？
6. 库仑计输入范围如何决定分流电阻？
