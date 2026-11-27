# 25 第四阶段验收报告

## 1. 验收范围

本阶段在 `PowerLab` 中引入 Level 1 NMOS、浮动高侧驱动、非理想二极管、电感 DCR 与电容 ESR，
完成非理想 Buck 的真实瞬态、五模型对照、功率/损耗/能量平衡/应力/温度/时间步长分析。

**已暂停**：未开发第五阶段工程指标体系、第六阶段扫描、第七阶段闭环、第九阶段 Web、
第十阶段 TestLab；未修改 TestLab、`kaifa` 环境、PySpice/ngspice 源码；未删除前三阶段任何内容。

## 2. 交付物

| 类别 | 文件 |
| --- | --- |
| 配置 | `configs/nonideal_buck_config.yaml`、`configs/device_models.yaml`、`configs/nonideal_validation.yaml` |
| 电路 | `circuits/nonideal_config.py`、`mosfet_models.py`、`diode_models.py`、`passive_models.py`、`gate_driver.py`、`device_testbench.py`、`nonideal_buck.py` |
| 仿真 | `simulations/nonideal_buck_runner.py`、`simulations/device_runner.py` |
| 分析 | `analysis/buck_waveforms.py`（扩展）、`power_metrics.py`、`loss_analysis.py`、`energy_balance.py`、`device_stress.py`、`model_comparison.py`、`device_characteristics.py` |
| 绘图 | `visualization/plots.py`（新增 7 个第四阶段函数） |
| 脚本 | `scripts/nonideal_common.py` 及 9 个第四阶段脚本 |
| 测试 | 12 个新增测试文件 |
| 文档 | `docs/18`–`docs/25` |

## 3. 最终验收命令（13 条，全部 exit 0）

| # | 命令 | 退出码 |
| --- | --- | --- |
| 1 | `python -m scripts.verify_environment` | 0 |
| 2 | `python -m pytest tests -q` | 0（323 passed） |
| 3 | `python -m scripts.buck_stage3_demo` | 0（PASS） |
| 4 | `python -m scripts.mosfet_characterization` | 0 |
| 5 | `python -m scripts.diode_characterization` | 0 |
| 6 | `python -m scripts.passive_losses` | 0 |
| 7 | `python -m scripts.gate_driver_demo` | 0 |
| 8 | `python -m scripts.nonideal_buck_demo` | 0 |
| 9 | `python -m scripts.buck_loss_demo` | 0 |
| 10 | `python -m scripts.buck_model_comparison` | 0 |
| 11 | `python -m scripts.temperature_demo` | 0 |
| 12 | `python -m scripts.buck_stage4_demo` | 0 |
| 13 | `python -m scripts.basic_circuits_demo` | 0 |

第三阶段基线回归：`Vout = 4.781334 V`、`ripple = 8.139 mVpp`、`CCM`、`PASS`，未受影响。

## 4. 关键结果

### 4.1 器件

| 项目 | 实测 |
| --- | --- |
| VTH 拟合（VDS=5 V） | 2.932 V（R²=0.99990） |
| ID max（VGS=10 V, VDS=5 V） | 179.27 A（教学模型外推） |
| VGS=10 V 时 RDS（低压拟合） | 21.36 mΩ |
| ID=2 A 时 RDS | 21.32 mΩ（VDS=42.65 mV） |
| 关断漏电 | 5.00e-12 A |
| 二极管 VF @ 0.5 / 1 / 2 A | 0.3439 / 0.3692 / 0.4026 V |
| 二极管反向漏电 @ −5 V | 1.000 µA |

### 4.2 五模型（5 ms，稳态 200 µs）

| 指标 | A | B | C | D | E |
| --- | --- | --- | --- | --- | --- |
| Vout (V) | 4.781374 | 4.687962 | 4.673238 | 4.665075 | 4.668158 |
| 纹波 (mVpp) | 8.102 | 19.049 | 19.090 | 19.039 | 19.042 |
| 总损耗 (W) | 0.41853 | 0.58815 | 0.61372 | 0.64431 | 0.67318 |
| 功率级效率 (%) | 95.6179 | 93.7285 | 93.4353 | 93.1140 | 92.9356 |
| 系统效率 (%) | 95.6179 | 93.7285 | 93.4353 | 93.1099 | 92.8311 |

### 4.3 Model E 损耗与能量

- 总损耗 673.185 mW：二极管 434.146 mW（64.49 %）、DCR 176.040 mW（26.15 %）、
  MOSFET 51.680 mW（7.68 %）、RG 9.905 mW、ESR 0.999 mW、RGS 0.415 mW。
- 功率级效率 92.9356 %，系统效率 92.8311 %。
- 能量平衡残差 −3.66e-5 W，比例 −3.90e-6，状态 `ok`。
- 导通估算 31.27 mW + 开关折算 20.00 mW = 51.27 mW，与实测网络 51.68 mW 相差 0.8 %。

### 4.4 应力（Model E）

VDS max 12.4108 V；ID 峰值 = p99.9 = 2.1854 A；VGS max 9.9990 V；
二极管反向峰值 11.9669 V；开关节点最低 −0.4108 V。

## 5. 一致性与交叉检查

| 检查 | 结果 |
| --- | --- |
| Model B/C 节点 KCL `IL = Iin + Idiode` | 残差 ≤ 1e-15 A |
| Model B/C `Icap = IL − Iload` | 残差 ≤ 1e-15 A |
| Model D/E 同一 KCL（含位移电流） | 残差 < 5e-3 A |
| 功率残差比例 | A 5.86e-5、B 5.9e-6、C 5.5e-6、D −1.3e-4、E −3.9e-6 |
| 步长 50 ns vs 25 ns（1 ms） | Vout 差 0.53 mV（0.011 %） |
| 最大步长约束 | 全部模型 `max_step_respected = True` |
| Model C 6.689 A 峰值 | 定位为开关瞬间数值样本；p99.9 与持续电流一致 |

## 6. 25 道面试题

**Q1. 为什么用 Level 1 MOS 而不是商业模型？**
参数透明、可手算核对、适合教学；缺点是缺少真实温度、击穿与 SOA，不能替代器件选型。

**Q2. VTO 等于“完全导通电压”吗？**
不等于。VTO 只是阈值参数；本模型拟合阈值 2.93 V，但 VGS=10 V 时 RDS 才降到 21 mΩ。

**Q3. 为什么 RDS(on) 不能写成固定常数？**
它随 VGS、ID、温度变化；本阶段只把它当作某个工作点的拆分工具，不替换真实波形损耗。

**Q4. 浮动驱动为什么必要？**
NMOS 源极在开关节点上，栅源电压必须以 `sw` 为参考；对地驱动会随 `sw` 跳变而失去 VGS。

**Q5. 这是 Bootstrap 吗？**
不是。这里是理想浮动电压源，没有自举电容、充电二极管与 UVLO。

**Q6. 为什么不把 VDRV 的功率算进效率分子？**
VDRV 是驱动功耗，属于系统输入；功率级效率用 `Pout/Pin`，系统效率用 `Pout/(Pin+Pdrv)`，两者分开。

**Q7. 功率边界为什么要互不重叠？**
避免同一能量被重复计数。MOSFET 网络只取漏极与栅极终端，DCR/ESR/RG/RGS 各自独立。

**Q8. 残差为什么不塞给某个器件？**
残差包含数值积分误差与未建模效应；强行分配会伪造物理结论。本阶段只报告残差及其比例。

**Q9. 为什么二极管是最大损耗项？**
`VF ≈ 0.40 V @ 2 A` 属普通 PN 结量级，远高于肖特基；平均电流大，故导通损耗占 64.5 %。

**Q10. DCR 对效率和纹波各有什么影响？**
50 mΩ 使效率降 1.91 个百分点、Vout 降 92.7 mV；对纹波影响很小。

**Q11. ESR 损耗只有 1 mW，为什么还重要？**
它决定纹波：ESR 把纹波从 8.0 mVpp 抬到 19.0 mVpp；平均损耗不能衡量其作用。

**Q12. 为什么 Model D 的开关能量不可信？**
D 没有 Cgs/Cgd，栅极电流几乎为零，开关过程由数值步长决定；必须在 E 中评估开关损耗。

**Q13. Model C 的 6.69 A 峰值是真实电流吗？**
不是持续电流，是 `CJO` 与理想开关在跳变点的数值尖峰；相邻点仅约 2 A，p99.9 约 2.19 A。

**Q14. 为什么时间步长会小到 1e-16 s？**
开关跳变导致节点电压剧烈变化，ngspice 自动缩小步长保证收敛；这是正常行为，不代表采样错误。

**Q15. 50 ns 与 25 ns 结果差多少？**
1 ms 窗口内 Vout 差 0.53 mV（0.011 %），纹波差 0.046 mV；25 ns 已足够。

**Q16. 12.5 ns 为什么失败？**
`timestep too small`，属于个别采样点的数值偶然性；脚本如实记录失败，不修改参数掩盖。

**Q17. 温度升高为什么效率下降？**
二极管损耗随温度从 434 mW 升到 497 mW；MOSFET 的 Level 1 参数本身无温度系数，
其损耗波动来自工作点变化，不是真实温度特性。

**Q18. 这是自热仿真吗？**
不是。温度是求解器固定值，没有热阻网络与损耗反馈。

**Q19. 如何验证功率守恒？**
`Pin + Pdrv − Pout − ΣPloss = residual`；Model E 残差比例 −3.9e-6，状态 `ok`。

**Q20. 为什么 A 的残差比 B–E 大？**
A 复用第三阶段理想二极管模型，端口定义与 B–E 的统一测量口径略有差异；比例仍只有 5.9e-5。

**Q21. 五模型为什么按 A→E 排列？**
逐项隔离非理想因素：无源寄生 → 二极管 → 开关器件与驱动 → 寄生电容，便于归因。

**Q22. 为什么 Model A 必须复用第三阶段构建器？**
保证基线与已验收结果完全一致，避免“重写基线”导致不可比。

**Q23. 电感 DCR 的损耗为什么用 Irms²·R？**
电阻损耗是电流平方的时间积分；非均匀步长下必须做时间加权 RMS，不能简单平均电流。

**Q24. 栅极电阻增大有什么代价？**
IG 峰值下降、RG 损耗与开关能量上升、效率下降；RG=2.2/10/22 Ω 时效率 93.006/92.936/92.833 %。

**Q25. 本阶段结论能直接用于选型吗？**
不能。模型为教学假设，缺少真实温度、反向恢复、封装热与 SOA；只能用于趋势与机理分析。

## 7. 限制声明

1. MOSFET 为 Level 1 教学模型，ID=179 A 等数值是外推结果，不是器件能力。
2. 二极管 `TT = 0`，无反向恢复电荷；不能用于 EMI/尖峰能量评估。
3. DCR/ESR 为固定值，无频率与温度特性。
4. 固定温度不是自热，不能给出结温或热设计结论。
5. 浮动驱动是理想源，不是 Bootstrap，不含 UVLO 与驱动供电模型。
6. 峰值应力不是 SOA，不能作为硬件保护依据。
7. 目标 5 V 未被钳位，Vout 偏差是真实结果，没有为凑 5 V 修改数据。

## 8. 暂停

第四阶段到此完成并暂停，等待下一阶段任务书。
