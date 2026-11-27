# 18 Level 1 NMOS 教学模型

## 1. 目的与边界

本阶段需要一个能真实进入 ngspice 求解、又足够透明的 MOSFET 模型，用来替代第三阶段
的电压控制开关 `SW`。选择 SPICE Level 1（Shichman-Hodges）平方律模型，原因是参数少、
行为可手算核对、不会伪装成商业器件。

必须明确：

- 这是**教学假设模型**，不是任何真实功率 MOSFET 的数据手册模型。
- `VTO` 是模型阈值参数，**不等于**“完全导通电压”；栅极必须显著高于 `VTO` 才进入低阻区。
- 本模型没有温度参数、没有击穿、没有安全工作区（SOA）、没有封装热模型。
- 下文所有“RDS(on)”都是从该模型直流扫描得到的**工作点值**，不是器件规格上限。

## 2. 模型参数

配置文件：`configs/device_models.yaml`；数据类：`circuits/nonideal_config.py::MosfetModelConfig`；
网表构建：`circuits/mosfet_models.py::add_educational_nmos`。

| 参数 | 值 | 说明 |
| --- | --- | --- |
| LEVEL | 1 | 平方律 |
| VTO | 3.0 V | 阈值参数 |
| KP | 0.01 A/V² | 跨导参数 |
| W / L | 1000 / 1 µm | 几何比，决定电流量级 |
| LAMBDA | 0.001 1/V | 沟道长度调制 |
| RD / RS | 5 mΩ / 2 mΩ | 漏/源串联电阻 |
| GAMMA | 0 | 无体效应 |
| BULK | 源极 | 三端使用 |
| 外部 Cgs / Cgd / Cds | 1 nF / 0.2 nF / 0.3 nF | 仅 Model E 添加 |

器件实例：`M1 drain gate sw sw NMOS_EDU`。栅极驱动以开关节点 `sw` 为参考，见文档 20。

## 3. 真实直流扫描结果（25 °C）

运行：`conda run -n kaifa_power python -m scripts.mosfet_characterization`

结果目录：`results/devices/run_20261125_130741_*`。

### 3.1 转移特性 `ID-VGS`（VDS = 5 V）

| 指标 | 实测 |
| --- | --- |
| VGS 扫描范围 | 0 – 10 V，步长 0.25 V |
| 最大漏极电流 | **179.27 A** @ VGS = 10 V |
| 最小（截止）电流 | 5.00e-12 A |
| 开关电流比 | 3.58e13 |
| sqrt(ID) 拟合阈值 | **2.932 V**（R² = 0.99990，16 点） |

说明：179 A 是 `W/L = 1000`、`KP = 0.01` 的教学模型外推结果，只用于观察趋势，
不能当作真实器件能力。拟合阈值 2.932 V 与参数 `VTO = 3.0 V` 的差异来自拟合区间与
Lambda 修正，属于正常现象。

### 3.2 输出特性 `ID-VDS`

| VGS | ID max @ VDS=1 V | 低 VDS 拟合 RDS |
| --- | --- | --- |
| 4 V | 4.904 A | 111.14 mΩ |
| 6 V | 21.53 A | 40.76 mΩ |
| 8 V | 34.54 A | 27.15 mΩ |
| 10 V | 45.01 A | 21.36 mΩ |

低 VDS 拟合窗口为 0–0.1 V、5 个点。RDS 随 VGS 上升而下降，符合“栅压越高越接近完全导通”的
定性规律，但绝不意味着 `VTO` 附近就已完全导通。

### 3.3 2 A 工作点与截止漏电

| 指标 | 实测 |
| --- | --- |
| VGS = 10 V、ID = 2 A 时 VDS | 42.65 mV |
| 对应 RDS(on) | **21.32 mΩ** |
| VGS = 0、VDS = 5 V 漏电 | 5.00e-12 A |

该 21.32 mΩ 只用于在损耗分解中**拆分**导通/开关部分（文档 22），不替换真实波形损耗。

## 4. 已知限制

1. 平方律不能复现真实器件的跨导退化、迁移率退化和高场效应。
2. 无温度参数：本模型参数不随温度变化；温度对照中的变化只来自二极管与求解温度设置。
3. 无雪崩、无 SOA、无短路能力，不能用于保护设计。
4. 峰值电流可能包含开关瞬间的孤立数值样本；应力报告同时给出 p99.9（见文档 23）。

## 5. 复现命令

```powershell
$env:PYTHONPATH='PowerLab'
conda run -n kaifa_power python -m scripts.mosfet_characterization
```

输出：转移/输出/截止扫描的 `waveform.csv`、`characteristics.json`、`mosfet_transfer.png`、
`mosfet_output.png`，以及包含全部器件判据的 `results/buck_stage4/.../device_checks.csv`。
