# 49 闭环 Buck SPICE 网表逐行解析

本文以第七阶段真实运行目录中的网表为对象：

`results/stage7/runs/run_20261125_152933_d6e8ff60/circuit.cir`

该运行为 E 变体（Level-1 MOSFET + 寄生电容）、闭环、标称负载 2.5 Ω、12 V 输入、
25 ns 步长、12 ms 窗口。网表由 `circuits/closed_loop_buck.py::build_closed_loop_buck`
与 `control/spice_controller.py::add_behavioral_pi_controller` 生成，不是手写贴入。

## 1. 完整网表

```spice
.title PowerLab Stage-7 Buck E (closed_loop)
VVIN vin 0 12.0
VDSENSE vin drain 0.0
M1 drain gate sw sw NMOS_EDU l=1e-06 w=0.001
CGS gate sw 1e-09
CGD gate drain 2e-10
CDS drain sw 3e-10
VDIOSENSE 0 diode_a 0.0
DFREE diode_a sw DFREE_NONIDEAL
VLSENSE sw lx 0.0
L1 lx l_dcr 4.7e-05
RDCR l_dcr out 0.05
VCSENSE out c_esr 0.0
RESR c_esr cap_internal 0.03
C1 cap_internal 0 0.0001
VLOADSENSE out load_node 0.0
RLOAD load_node 0 2.5
VCREF ref 0 PWL(0.0s 0.0V 0.002s 5.0V 0.012s 5.0V)
BCERR err 0 v=V(ref)-V(out)
BCFF ff 0 v=V(ref)/max(V(vin),2)
BCPROP prop 0 v=0.0585*V(err)
BCRAW raw 0 v=V(ff)+V(prop)+V(integ)
BCLIM duty 0 v=min(max(V(raw),0.02),0.9)
CCINT integ 0 1.0 ic=0
BCIINT 0 integ i=117.66*V(err)+2000*(V(duty)-V(raw))
RCILEAK integ 0 1000000000.0
BCRAMP ramp 0 v=0.5*(1+sin(628318.530718*time))
BCPWM pwm 0 v=min(max((V(duty)-V(ramp))/0.02+0.5,0),1)
ECDRV drv sw pwm 0 10.0
RCG drv gate 10.0
RCGS gate sw 100000.0
.model NMOS_EDU NMOS (GAMMA=0 KP=0.01 LAMBDA=0.001 LEVEL=1 RD=0.005 RS=0.002 VTO=3.0)
.model DFREE_NONIDEAL D (CJO=2e-10 IS=1e-06 M=0.5 N=1.0 RS=0.015 TT=0.0 VJ=0.7)
.options TEMP = 25.0C
.options TNOM = 25.0C
.tran 2.5e-08s 0.012s 0.0s 2.5e-08s uic
.end
```

## 2. 逐行解释

| 行 | 含义 | 建模要点 |
| --- | --- | --- |
| `.title` | 运行标题 | 记录变体与模式，便于追溯 |
| `VVIN vin 0 12.0` | 输入源 | 线阶跃实验会替换为 PWL；标称工况为 12 V DC |
| `VDSENSE vin drain 0.0` | 0 V 电流检测 | 让 `i(VDSENSE)` 可直接读取输入支路电流，不影响电路 |
| `M1 drain gate sw sw NMOS_EDU` | 主开关 | Level-1 NMOS，源极接 `sw`，衬底同源 |
| `CGS/ CGD/ CDS` | MOSFET 寄生电容 | 与栅极驱动电阻共同决定开关边沿；E 变体才添加 |
| `VDIOSENSE 0 diode_a 0.0` | 二极管支路电流检测 | 0 V 源，读取续流电流 |
| `DFREE diode_a sw` | 续流二极管 | 非理想：`IS`、`RS`、`CJO`、`VJ`，方向为地→sw |
| `VLSENSE sw lx 0.0` | 电感电流检测 | 物理上串联在电感前，0 V 不影响 |
| `L1 lx l_dcr 47u` | 功率电感 | 47 µH，含 DCR 子节点 |
| `RDCR l_dcr out 0.05` | 电感直流电阻 | 与 L 分离，便于测量 DCR 损耗 |
| `VCSENSE out c_esr 0.0` | 输出电流检测 | 读取电容支路电流 |
| `RESR c_esr cap_internal 0.03` | ESR | 30 mΩ，产生输出纹波与瞬时压降 |
| `C1 cap_internal 0 100u` | 输出电容 | 100 µF，内部节点电压 `vC` |
| `VLOADSENSE out load_node 0.0` | 负载电流检测 | 动态/电阻负载接在 `load_node` 与地之间 |
| `RLOAD load_node 0 2.5` | 标称负载 | 2 A @ 5 V；实验会替换为动态负载 |
| `VCREF ref 0 PWL(...)` | 参考电压 | 软启动 0→5 V / 2 ms，之后保持 5 V |
| `BCERR err 0 v=V(ref)-V(out)` | 误差 | 直接读输出电压，闭环反馈的起点 |
| `BCFF ff 0 v=V(ref)/max(V(vin),2)` | 输入前馈 | `vin_min=2 V` 防止除零；`feedforward_enabled=false` 时该源写为 `0` |
| `BCPROP prop 0 v=0.0585*V(err)` | 比例项 | `Kp = 0.0585` |
| `BCRAW raw 0 v=V(ff)+V(prop)+V(integ)` | 未限幅占空比 | 三项求和，与离散控制律一致 |
| `BCLIM duty 0 v=min(max(V(raw),0.02),0.9)` | 限幅 | 占空比 0.02～0.90 |
| `CCINT integ 0 1.0 ic=0` | 积分电容 | 单位电容，`ic=0` 保证从零开始 |
| `BCIINT 0 integ i=117.66*V(err)+2000*(V(duty)-V(raw))` | 积分电流 | 第一项是 `Ki·e`，第二项是反算抗饱和；**节点顺序必须是 0→integ** |
| `RCILEAK integ 0 1e9` | 积分泄漏 | 防止理想积分器浮空导致 DC 工作点失败 |
| `BCRAMP ramp 0 v=0.5*(1+sin(2π·fs·t))` | 正弦载波 | `628318.530718 = 2π×100k` |
| `BCPWM pwm 0 v=clamp((d−ramp)/0.02+0.5,0,1)` | 平滑比较器 | 宽度 0.02；避免不连续导致收敛失败 |
| `ECDRV drv sw pwm 0 10` | 栅极驱动器 | 以 `sw` 为参考的 10 V 压控源，高边浮动驱动 |
| `RCG drv gate 10` | 栅极电阻 | 10 Ω，限制栅极电流 |
| `RCGS gate sw 100k` | 栅极下拉 | 保证关断状态确定 |
| `.model NMOS_EDU` | MOSFET 模型 | `VTO=3`、`KP=0.01`、`W/L=1000`（`l=1u, w=1m`） |
| `.model DFREE_NONIDEAL` | 二极管模型 | `IS=1e-6`、`RS=0.015`、`CJO=200p` |
| `.options TEMP/TNOM` | 温度 | 25 °C，与配置快照一致 |
| `.tran ... uic` | 瞬态 | 最大步长 25 ns，12 ms；`uic` 跳过 DC 工作点 |

## 3. 关键实现细节

### 3.1 为什么必须 `uic`

PWL 参考源在 `t=0` 没有 DC 值，直接求工作点会报
`vcref: no DC value`。使用 `uic` 后从初始条件（电容 0 V、电感 0 A）开始，
警告仍会出现但不影响结果；运行元数据保留原始警告，不隐藏。

### 3.2 积分器极性

`BCIINT 0 integ i=...` 表示电流从地流入 `integ`，给电容充电，`V(integ)` 上升。
若写成 `BCIINT integ 0 i=...`，误差为正时反而给电容反向充电，形成正反馈并发散。
这是实测踩过的坑，`tests/test_spice_controller.py` 有专门断言。

### 3.3 正弦载波与有效占空比

`ramp` 在 0～1 之间正弦变化，比较器阈值 `d` 与实际占空比的关系为

```text
D = 0.5 + asin(2d − 1)/π
```

稳态 5 V 时 `D ≈ 0.4448`，对应 `d ≈ 0.4137`。

### 3.4 SW 变体的差异

`build_closed_loop_buck(..., variant="SW")` 把 `M1` 换成电压控制开关 `S1`
（`RON=1e-3`、`ROFF=1e6`、`VT=2.5`、`VH=0.02`），并添加

```spice
BCCTRL ctrl 0 v=5*V(pwm)
S1 drain sw ctrl 0 SWMOD
```

闭环时开关控制节点是 `ctrl`；开环时 PULSE 直接驱动 `gate`。
SW 变体仍保留 DCR/ESR：没有这些无源阻尼时，实测出现约 2 V、6 kHz 的持续极限环，
属于真实不稳定，而不是数值噪声。

### 3.5 开环网表

开环模式移除 `BCERR/BCFF/BCPROP/BCRAW/BCLIM/CCINT/BCIINT/BCRAMP/BCPWM`，
改用固定占空比 PULSE 驱动栅极（E/D）或 `gate`（SW）。固定占空比来自平均模型
离线校准（0.4448），不是实时搜索。开环在 25 ns 下可能出现
`Timestep too small`，运行器会显式回退到 50 ns 并记录 `step_fallback`。

## 4. 适用条件与局限

- 适用于 12 V→5 V、100 kHz、CCM 的教学级 Buck。
- 行为源 PI 是连续时间实现，不等价于数字控制器的采样保持。
- 平滑比较器不是理想比较器；`w=0.02` 是可调建模参数。
- 二极管与 MOSFET 均为教学模型，不能用于器件选型。

## 5. 技术面试题

1. `VDSENSE`、`VLSENSE`、`VCSENSE` 为什么用 0 V 源而不是普通导线？
2. `uic` 跳过了什么？为什么本网表必须使用它？会带来什么副作用？
3. `BCIINT` 的节点顺序写反后，仿真会出现什么现象？如何快速定位？
4. `ECDRV drv sw pwm 0 10` 为什么以 `sw` 为参考，而不是以地为参考？
5. `RCGS = 100k` 的作用是什么？去掉后会发生什么？
6. SW 变体为什么在无 DCR/ESR 时出现极限环？这算数值问题还是真实不稳定？
7. 如果要把这个网表改成峰值电流模式控制，至少需要增加哪些节点与元件？
