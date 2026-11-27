# 09 电池等效电路模型总览

> 阶段：BatteryLab 第二阶段（等效电路建模与仿真验证）
> 参数来源：`configs/ecm_parameters.yaml`，标记 `educational_assumption`
> 结论边界：本阶段完成数学模型与电路仿真验证，不代表真实电芯参数辨识，也不代表 BMS 硬件或保护功能已经实现。

## 1. 电路拓扑

三种模型共享同一骨架：一个 OCV 电压源、一个串联欧姆内阻 R0、若干并联 RC 极化支路，外部由理想电流源激励。

```text
        R0            R1              R2
 n_ocv ──/\/\── n1 ──/\/\── n2 ──/\/\── out
   +            │       │        │       │
  OCV          === C1   │       === C2   │
   -            │       │        │       │
  gnd ──────────┴───────┴────────┴───────┴── Iload(t)
```

- Rint：仅 OCV + R0。
- 一阶 RC：OCV + R0 + R1/C1。
- 二阶 RC：OCV + R0 + R1/C1 + R2/C2。

## 2. 专业公式

端电压：

```text
Vterminal(t) = OCV(SOC) - I(t)·R0 - Σj Vj(t)
```

极化状态（每个 RC 支路）：

```text
dVj/dt = -Vj / (Rj·Cj) + I / Cj
```

SOC（安时积分，放电为正）：

```text
SOC(t) = SOC0 - η_eff · ∫I dt / (3600·Qnom)
```

## 3. 变量与单位

| 符号 | 含义 | 单位 |
| --- | --- | --- |
| Vterminal | 单体端电压 | V |
| OCV | 开路电压 | V |
| I | 电流（放电为正） | A |
| R0 | 欧姆内阻 | Ω |
| Rj/Cj | 第 j 个极化电阻/电容 | Ω / F |
| Vj | 第 j 个 RC 支路电压 | V |
| τj | 极化时间常数 Rj·Cj | s |
| Qnom | 额定容量 | Ah |
| SOC | 荷电状态 | 0–1 |

## 4. 公式推导（零阶保持精确离散）

在一个时间步 `[t, t+dt]` 内假设电流恒定 `I`，RC 方程是一阶线性常系数微分方程：

```text
Vj(t+dt) = Vj(t)·exp(-dt/τj) + I·Rj·(1 - exp(-dt/τj))
```

SOC 使用精确电荷积分：

```text
SOCnext = SOC - I·dt / (3600·Qnom)
```

代码用 `-expm1(-dt/τ)` 代替 `1-exp(-dt/τ)`，避免极小时步下的相减抵消。

## 5. 适用条件

- 电流在采样区间内按零阶保持处理；阶跃发生在采样点上。
- 温度、老化、滞回与自放电未建模。
- 参数为教学假设值，不能用于真实电芯精度结论。
- OCV 可以是固定基准（3.8 V）或教学查表曲线。

## 6. 实际代码路径与核心函数

| 功能 | 路径 | 核心函数/类 |
| --- | --- | --- |
| 参数与校验 | `battery_models/parameters.py` | `CellParameters`、`RCBranch`、`ECMModelDefinition`、`load_ecm_models` |
| 状态与更新 | `battery_models/states.py` | `CellState`、`update_soc`、`update_polarization_voltage`、`update_branch_voltages` |
| 统一求解器 | `battery_models/ecm_solver.py` | `simulate_ecm`、`terminal_voltage` |
| 运行落盘 | `simulations/ecm_runner.py` | `run_ecm_case` |
| 电流工况 | `simulations/load_profiles.py` | `LoadProfile`、`sample` |

## 7. 关键代码逐行解释

`battery_models/states.py::update_polarization_voltage`

```python
tau = resistance * capacitance          # 时间常数，单位 s
decay = math.exp(-dt / tau)             # 零输入衰减系数
one_minus_decay = -math.expm1(-dt / tau)  # 1-exp(-dt/tau)，小步长更精确
return previous * decay + current * resistance * one_minus_decay
```

`battery_models/ecm_solver.py::simulate_ecm` 主循环：

```python
current_value = float(current_array[index])     # 区间左端电流（ZOH）
ocv_value = float(ocv_model.voltage(state.soc)) # 当前 OCV
rows.append(_row(...))                          # 先记录当前状态与端电压
next_soc = update_soc(...)                      # 更新 SOC
next_voltages = update_branch_voltages(...)     # 更新所有 RC 支路
```

## 8. 实际运行命令

```powershell
conda run -n kaifa_battery python -m scripts.rint_demo
conda run -n kaifa_battery python -m scripts.first_order_rc_demo
conda run -n kaifa_battery python -m scripts.second_order_rc_demo
```

## 9. 真实结果路径

- `results/ecm/run_ecm_20261126_122858_dadfee/`：三模型统一脉冲对照（含 `waveform.csv`、`event_log.csv`、`energy_balance.json`）。
- 单体运行：`run_ecm_20261126_122856_9e8ca2`（Rint）、`run_ecm_20261126_122856_492c95`（一阶）、`run_ecm_20261126_122857_cdbae7`（二阶）。
- 综合验收：`results/stage2/run_stage2_20261126_123052_b15f65/validation_summary.json`。
## 10. 三个必须理解的问题

### 10.1 为什么端电压不等于 OCV

OCV 只是热力学平衡电位。只要电流不为零，R0 与极化支路都会产生压降：

```text
Vterminal = OCV - I·R0 - V1 - V2
```

2 A 放电时 R0 立即产生 `2×0.03=0.06 V` 压降，随后极化电压继续增大，因此端电压低于 OCV，且随时间缓慢下降。

### 10.2 为什么 R0 瞬时跳变而 RC 渐变

R0 是纯电阻，满足代数关系 `ΔV = I·R0`，电流突变时电压立即跟随。RC 支路含电容，电容电压不能突变，必须按 `exp(-dt/τ)` 连续演化，因此表现为指数渐变。

### 10.3 为什么 RC 电容可以达到数千法拉

等效电容不是真实电容器的物理容量，而是把扩散、双电层等慢过程折算成电路元件的等效参数。用 `C = τ/R` 计算：若 τ=60 s、R=15 mΩ，则 C=4000 F。数值巨大只说明该过程时间常数长、等效阻抗小，不代表真实器件容量。

## 11. 常见错误

- 把等效电容当成真实超级电容容量。
- 用 `I²R1` 计算极化损耗（正确为 `V1²/R1`，因为电流会分流到电容）。
- 认为“60 s 脉冲结束电压”就是积分到 70.000 s 的采样值；实际 0.1 s 采样下最后一点是 69.9 s，差 10 µV。
- 把教学参数直接写成真实 18650 电芯参数。

## 12. 独立练习

1. 将输出步长改为 0.01 s，验证解析误差仍在 1 µV 内。
2. 把 R0 改为 0，观察阶跃跳变是否消失。
3. 用 1 A 充电脉冲，验证端电压高于 OCV。

## 13. 面试题

1. 等效电路模型与电化学模型各自的优缺点是什么？
2. 为什么 RC 支路的状态更新可以用解析解，而不是必须数值积分？
3. 如何从脉冲响应中分离 R0 与极化电阻？
4. 参数随 SOC、温度变化时，模型应如何扩展？
