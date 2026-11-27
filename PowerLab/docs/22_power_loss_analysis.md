# 22 功率边界与损耗分解

## 1. 功率边界（互不重叠）

分析模块：`analysis/power_metrics.py`、`analysis/loss_analysis.py`。
所有平均量都按真实非均匀时间网格做时间加权，不使用简单采样平均。

| 项目 | 定义 | 说明 |
| --- | --- | --- |
| 输入功率 | `Pin = ⟨vin · i_in⟩` | `i_in = −i(VIN)` |
| 输出功率 | `Pout = ⟨vout · i_load⟩` | `i_load = vout / R` |
| MOSFET 网络 | `⟨VDS·ID⟩ + ⟨VGS·IG⟩` | IG 为流入栅极终端的电流，不含 RGS |
| 二极管 | `⟨V_AK · I_D⟩` | 含正向导通，反向时电流为负 |
| 电感 DCR | `Irms(IL)² · DCR` | 只用真实电感电流 |
| 电容 ESR | `Irms(IC)² · ESR` | 只用真实电容电流 |
| 栅极电阻 RG | `Irms(IRG)² · RG` | `IRG = (Vdrv − Vgate)/RG − VGS/RGS` |
| 下拉电阻 RGS | `⟨VGS² / RGS⟩` | 与 RG 不重叠 |
| 驱动器输出 | `Pdrv = ⟨(Vdrv − Vsw) · Idrv⟩` | 只进系统级效率分母 |

残差定义为：

```text
residual = Pin + Pdrv − Pout − Pmosfet − Pdiode − Pdcr − Pesr − PRG − PRGS
```

残差**不分配**给任何器件，也不用于“修正”效率。

## 2. Model E 损耗分解（真实 5 ms 瞬态）

运行：`conda run -n kaifa_power python -m scripts.buck_loss_demo`
（稳态窗口 4.780024–4.980023 ms，时长 200 µs）。

| 项目 | 平均功率 | 占总损耗 |
| --- | --- | --- |
| MOSFET 网络 | 51.680 mW | 7.677 % |
| 二极管 | 434.146 mW | 64.491 % |
| 电感 DCR | 176.040 mW | 26.150 % |
| 电容 ESR | 0.999 mW | 0.148 % |
| 栅极电阻 RG | 9.905 mW | 1.471 % |
| 下拉电阻 RGS | 0.415 mW | 0.062 % |
| **合计** | **673.185 mW** | 100 % |

功率层面：

| 指标 | 实测 |
| --- | --- |
| Pin | 9.379280 W |
| Pdrv | 0.010563 W |
| Pout | 8.716695 W |
| 功率级效率 | 92.9356 % |
| 系统效率 | 92.8311 % |
| 残差 | −3.66e-5 W |
| 残差 / (Pin+Pdrv) | −3.90e-6 |

结果目录：`results/nonideal_buck/run_20261125_131441_b6aa6b8d/loss_table.csv`。

## 3. MOSFET 导通 / 开关拆分

用器件扫描得到的 `RDS(on) = 21.32 mΩ @ 2 A` 只做**拆分估算**：

- 导通估算：`Irms² · RDS` = **31.27 mW**；
- 开关能量：19 次开通 + 20 次关断，总计 **4.001 µJ**；
- 折算功率：`4.001 µJ / 200 µs = 20.00 mW`；
- 两者之和 51.27 mW，与真实网络损耗 51.68 mW 相差 0.41 mW（0.8 %）。

这个一致性说明：在该工况下，开关损耗与导通损耗量级相当，不能只算 `I²R`。
但拆分依赖固定 RDS，仍不是器件规格，也不能外推到其他温度/电流。

## 4. 物理解读

1. **二极管是最大损耗项（64.5 %）**：因为 `VF ≈ 0.40 V @ 2 A`，远高于肖特基。
   若要提高效率，首先应更换为低正向压降器件——但本阶段不下载商业模型，也不宣称任何具体型号。
2. **DCR 是第二大项（26.2 %）**：50 mΩ 在 2 A 量级下产生 176 mW。
3. **ESR 平均损耗很小（0.148 %）**，但它决定纹波（文档 19）。
4. **栅极损耗约 1.5 %**，其中 RG 占主导，RGS 可忽略。

## 5. 限制

- 固定 DCR/ESR，无频率与温度特性。
- 二极管无反向恢复电荷（`TT = 0`）。
- MOSFET 为 Level 1 教学模型，导通电阻随电流/温度的变化不代表真实器件。
- 开关能量在粗输出采样下可能只覆盖少量点，已在文档 24 用步长敏感性交叉检查。

## 6. 复现命令

```powershell
$env:PYTHONPATH='PowerLab'
conda run -n kaifa_power python -m scripts.buck_loss_demo
```
