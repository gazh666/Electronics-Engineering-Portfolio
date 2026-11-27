# 30 负载特性与输入特性

本文解释负载调整率、线性调整率、开环负载特性、开环输入特性、恒阻负载与恒流
负载的区别、CCM/DCM 边界、实际输出与设计目标的差异，以及闭环控制为什么能改善
稳压性能。

代码位置：`experiments/load_characteristics.py`（`run_load_characteristic`、
`_simulate`、`_run_and_analyze`）、`experiments/line_characteristics.py`
（`run_line_characteristic`）、`analysis/regulation_analysis.py`
（`load_regulation`、`line_regulation`、`_is_steady`）、
`experiments/performance_benchmark.py`。

真实结果：

- 负载扫描 `results/performance/run_20261125_143608_abbb852d/`
  （`load_characteristic.csv`、`load_regulation.json`）
- 输入扫描 `results/performance/run_20261125_143621_633530cc/`
  （`line_characteristic.csv`、`line_regulation.json`）
- 汇总 `results/buck_stage5/run_20261125_143621_dd15c905/stage5_validation.json`

## 1. 负载调整率与线性调整率

负载调整率描述负载电流变化引起的输出电压变化：

$$
\text{Load Regulation}=\frac{V_{out}(I_{min})-V_{out}(I_{max})}{V_{out,nom}}\times100\%
$$

线性调整率描述输入电压变化引起的输出电压变化：

$$
\text{Line Regulation}=\frac{\Delta V_{out}}{\Delta V_{in}}
$$

两者在数据手册中都要求**闭环稳压**条件。本阶段是开环固定/前馈占空比，
因此只能给出“开环负载特性”和“开环输入特性”，不能冒充 datasheet 指标。

## 2. 扫描方法

| 项目 | 负载扫描 | 输入扫描 |
| --- | --- | --- |
| 变体 | Model E | Model E |
| 扰动变量 | $R_{load}$ = 50, 20, 10, 5, 2.5, 2, 1.667 Ω | $V_{in}$ = 9, 10.8, 12, 14.4, 16 V |
| 占空比 | 配置固定 0.416667 | 前馈 $D=V_{target}/V_{in}$ |
| 结束时间 | 5 ms（轻载可延长） | 5 ms |
| 判定 profile | 重载 `baseline_open_loop`，≥20 Ω `light_load_open_loop` | `baseline_open_loop` |

输入扫描的前馈占空比由 `line_characteristics.py` 计算并写入
`control_note = "feed-forward duty schedule D=Vtarget/Vin; this is not closed-loop regulation"`，
避免读者把开环灵敏度当成闭环线性调整率。

轻载收敛：`_simulate` 按候选最大步长
`(None, 20 ns, 12.5 ns, 10 ns, 6.25 ns, 15 ns)` 依次重试。50 Ω 首次出现
`Timestep too small; trouble with node "m1#source"`，用 20 ns 成功；
16 V 输入用 12.5 ns；其余用默认步长。每次实际步长记录在结果行
`max_step_time_s`。

## 3. 拟合口径

对已稳态的点按输出电流升序拟合：

$$
V_{out}=a+b\,I_{out}
$$

- 负载调整率 span：$\dfrac{\max V_{out}-\min V_{out}}{V_{nom}}$ 或端点法
- CCM 斜率 $b$：只对 CCM 点拟合，单位 mV/A
- 拟合优度：$r^2=1-\dfrac{\sum(y_i-\hat y_i)^2}{\sum(y_i-\bar y)^2}$
- `excluded_not_settled`：未稳态而被剔除的点数

`_is_steady` 的规则：`steady_state` 字段缺失视为可用；显式 false 或字符串
"false" 剔除。这样兼容第四阶段没有该字段的历史结果，又不放过明确的未稳态标记。

## 4. 负载扫描实测

| R (Ω) | Vout (V) | Iout (A) | Pout (W) | 纹波 (mVpp) | 效率 (%) | 模式 | 状态 |
| ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 50 | 7.160348 | 0.143207 | 1.025412 | 15.623 | 96.736 | DCM | PASS |
| 20 | 5.401912 | 0.270096 | 1.459033 | 18.924 | 95.428 | DCM | PASS |
| 10 | 4.788689 | 0.478869 | 2.293154 | 19.701 | 94.749 | CCM | INCOMPLETE |
| 5 | 4.743616 | 0.948723 | 4.500379 | 19.267 | 94.208 | CCM | PASS |
| 2.5 | 4.668158 | 1.867263 | 8.716679 | 19.042 | 92.831 | CCM | PASS |
| 2 | 4.634372 | 2.317186 | 10.738703 | 19.001 | 92.256 | CCM | PASS |
| 1.667 | 4.601676 | 2.761005 | 12.705252 | 19.213 | 91.630 | CCM | PASS |

汇总：span **51.1734 %**，CCM 斜率 **−78.508 mV/A**，$r^2=0.9992$，
CCM 点数 4，`excluded_not_settled = 1`。

10 Ω 点标 `INCOMPLETE` 的原因：其逐周期平均电感电流存在约 3 kHz、峰峰约
1.4 mA 的持续小幅振荡，超过稳态判据 `relative_mean_tolerance = 0.1 %`。
它不是仿真发散，也不是性能 FAIL，而是数据未达到稳态；因此保留原始数据，
但不送入 CCM 斜率拟合。

## 5. 输入扫描实测

| Vin (V) | D | Vout (V) | Iout (A) | 纹波 (mVpp) | 效率 (%) | 状态 |
| ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 9.0 | 0.555556 | 4.714662 | 1.885865 | 15.029 | 93.940 | PASS |
| 10.8 | 0.462963 | 4.683818 | 1.873527 | 17.784 | 93.227 | PASS |
| 12.0 | 0.416667 | 4.668158 | 1.867263 | 19.042 | 92.831 | PASS |
| 14.4 | 0.347222 | 4.647228 | 1.858891 | 21.232 | 92.330 | PASS |
| 16.0 | 0.312500 | 4.636728 | 1.854691 | 22.482 | 92.060 | PASS |

线路调整率：灵敏度 **−10.840 mV/V**，span **1.5587 %**，$r^2=0.9622$。

开环前馈下，Vin 升高 → D 减小 → 导通损耗占比变化，Vout 缓慢下降约 10.8 mV/V。
这不是闭环线性调整率，也不代表稳压器性能。

## 6. 恒阻负载与恒流负载

本项目负载是**恒阻** $R_{load}$：

$$
i_{load}(t)=\frac{v_{out}(t)}{R_{load}}
$$

恒流（电子负载 CC 模式）则是 $i_{load}=I_{set}$，与 $v_{out}$ 无关。两者差异：

| 方面 | 恒阻 | 恒流 |
| --- | --- | --- |
| 小信号负载阻抗 | $R_{load}$ | 理想无穷大 |
| 对环路增益影响 | 与 $R_{load}$ 并联 | 近似不并联，环路增益更高 |
| 输出跌落时电流 | 自动减小 | 保持不变，可能加剧跌落 |
| 启动/限流行为 | 较温和 | 可能触发恒流环 |
| 本项目 | 全部工况使用 | 未建模 |

因此本项目的负载调整率是“阻性负载”结论；换成恒流负载，数值可能不同，
不能直接互换。

## 7. CCM/DCM 边界

CCM/DCM 边界发生在电感电流谷值刚好到零：

$$
I_{out,crit}=\frac{\Delta i_L}{2}
=\frac{(V_{in}-V_{out})D}{2Lf_{sw}}
$$

对应临界电阻：

$$
R_{crit}=\frac{V_{out}}{I_{out,crit}}
=\frac{2Lf_{sw}V_{out}}{(V_{in}-V_{out})D}\approx14.4\ \Omega
$$

代入 $L=47$ µH、$f_{sw}=100$ kHz、$V_{out}\approx4.67$ V、$V_{in}=12$ V、
$D=0.4167$。实测 20 Ω 为 DCM、10 Ω 为 CCM，与 14.4 Ω 的边界一致。
DCM 点不参与 CCM 斜率拟合，因为 DCM 的电压增益关系不是简单线性占空比关系。

## 8. 实际输出与设计目标的差异

设计目标 5 V（`target_output_voltage_v`），基线开环实测 4.668158 V，
误差 −0.331842 V（−6.64 %）。主要来源：

1. MOSFET 导通电阻与二极管正向压降；
2. 电感 DCR 的直流压降；
3. 死区与开关过渡期间的伏秒损失；
4. 固定占空比没有反馈修正。

这是开环物理结果，不是仿真错误。`configs/performance_limits.yaml` 的
`baseline_open_loop` 把 `output_voltage_target` 设为 `enabled: false`，
避免用电压偏差否定纹波、效率等基础指标；若切到 `target_5v_design`
（4.9–5.1 V），基线会 FAIL。两种口径都保留，读者需明确用的是哪一个。

## 9. 为什么闭环控制能改善稳压性能

闭环（电压模式或电流模式）通过误差放大器调节占空比：

$$
D(t)=D_0+K_p e(t)+K_i\int e(t)\,dt
$$

- 负载电流突增 → Vout 下降 → 误差增大 → 占空比增大 → 输入功率增加；
- 输入电压变化 → 前馈或反馈修正占空比 → 抑制 Vout 波动；
- 因此负载调整率、线性调整率可以从“几十 mV/A、十几 mV/V”改善到 datasheet
  量级（具体数值取决于环路增益与带宽，本阶段未实现闭环，不给虚构数字）。

闭环也带来稳定性问题：相位裕度、穿越频率、负载瞬态过冲。这些属于第七阶段
任务，本阶段不展开。

## 10. 面试题

1. 为什么轻载更容易进入 DCM？
   负载电流低于 $\Delta i_L/2$ 时，电感电流在周期结束前降到零，二极管截止。
2. 本例 CCM/DCM 边界大约多少欧姆？如何计算？
   $R_{crit}=2Lf_{sw}V_{out}/((V_{in}-V_{out})D)\approx14.4$ Ω。
3. 为什么 DCM 点不参与 CCM 斜率拟合？
   DCM 的输入输出关系不同，混入会扭曲线性趋势。
4. 开环 −10.84 mV/V 能当 datasheet 线性调整率吗？
   不能。datasheet 指标要求闭环稳压条件。
5. 恒阻负载与恒流负载对环路有什么不同影响？
   恒流负载小信号阻抗近似无穷大，不并联降低环路增益，但输出跌落时电流不减小。
6. 10 Ω 点为什么是 INCOMPLETE 而不是 FAIL？
   稳态判据未通过，属于“无法验证”，不是“性能不达标”。
7. 为什么开环输出低于 $D V_{in}$？
   导通电阻、二极管压降、DCR、死区与开关过渡损失共同造成。
8. 闭环为什么能同时改善负载与线性调整率？
   反馈把输出误差转换为占空比修正，等效提高了直流环路增益。
