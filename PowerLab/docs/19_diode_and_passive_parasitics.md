# 19 非理想二极管、电感 DCR 与电容 ESR

## 1. 为什么需要这三项

第三阶段使用理想二极管导通模型与理想 L/C，导致：

- 二极管零压降，低估导通损耗；
- 电感无直流电阻，输出偏高；
- 电容无 ESR，纹波与损耗偏低。

第四阶段用真实 SPICE 元件替换它们。所有参数仍是教学假设值，不对应具体商品型号。

## 2. 非理想续流二极管

配置文件：`configs/device_models.yaml`；构建：`circuits/diode_models.py::add_nonideal_diode`。

| 参数 | 值 |
| --- | --- |
| IS | 1e-6 A |
| N | 1.0 |
| RS | 0.015 Ω |
| CJO | 200 pF |
| VJ | 0.7 V |
| M | 0.5 |
| TT | 0 s |

实测（25 °C，`scripts/diode_characterization.py`）：

| 正向电流 | 正向压降 |
| --- | --- |
| 0.5 A | 0.3439 V |
| 1.0 A | 0.3692 V |
| 2.0 A | **0.4026 V** |

反向 -5 V 时漏电 **1.000 µA**（等于 IS 量级）。

注意：`TT = 0` 意味着没有存储电荷引起的反向恢复尖峰；`CJO = 200 pF` 只提供结电容。
因此本模型**没有**真实二极管的反向恢复电荷，不能用于评估 EMI 或开关尖峰能量。

## 3. 电感 DCR 与电容 ESR

构建：`circuits/passive_models.py`。

- `add_inductor_with_dcr`：`L1 lx l_dcr 47µH` + `RDCR l_dcr out 50mΩ`；
  当 `dcr = 0` 时省略内部节点，退化为 `L1 lx out`。
- `add_capacitor_with_esr`：`RESR out cap_internal 30mΩ` + `C1 cap_internal 0 100µF`；
  当 `esr = 0` 时退化为 `C1 out 0`。

### 3.1 真实瞬态对照

运行：`conda run -n kaifa_power python -m scripts.passive_losses`
（Model E，5 ms，稳态窗口 200 µs）。

| 组合 | Vout | 纹波 | 功率级效率 | DCR 损耗 | ESR 损耗 |
| --- | --- | --- | --- | --- | --- |
| 理想 L/C | 4.760879 V | 8.065 mVpp | 94.8593 % | 0 | 0 |
| 仅 DCR | 4.668156 V | 8.006 mVpp | 92.9449 % | 176.040 mW | 0 |
| DCR + ESR | 4.668158 V | 19.042 mVpp | 92.9356 % | 176.040 mW | 0.999 mW |

解读：

1. 50 mΩ DCR 使输出下降约 **92.7 mV**，效率下降 **1.91 个百分点**，是本阶段最大的无源损耗项。
2. 30 mΩ ESR 对平均效率影响仅 **0.009 个百分点**，但把输出纹波从 8.0 mVpp 抬到 19.0 mVpp。
   纹波主要由 ESR 与电感电流纹波共同决定，不能用平均损耗衡量其重要性。
3. 结果文件：`results/nonideal_buck/run_20261125_130843_45fb2cae/passive_loss_summary.csv`。

## 4. 限制

- DCR 为固定电阻，不含趋肤效应、磁芯损耗和饱和。
- ESR 为固定电阻，不含频率特性与温度特性。
- 二极管参数未与任何真实器件标定；`VF ≈ 0.40 V @ 2 A` 明显高于肖特基，属于普通 PN 结量级。
- 零 DCR/ESR 分支只用于对照，不代表可制造元件。

## 5. 复现命令

```powershell
$env:PYTHONPATH='PowerLab'
conda run -n kaifa_power python -m scripts.diode_characterization
conda run -n kaifa_power python -m scripts.passive_losses
```
