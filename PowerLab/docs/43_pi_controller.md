# 43 PI 控制器设计与实现

## 1. 控制律

第七阶段使用电压模式 PI + 输入前馈，控制律在离散仿真与 SPICE 行为源中完全一致：

```text
e[k]      = Vref[k] − Vout[k]
d_ff[k]   = Vref[k] / max(Vin[k], Vin_min)          （前馈，可关闭）
d_p[k]    = Kp · e[k]
d_raw[k]  = d_ff[k] + d_p[k] + xI[k]
d[k]      = clamp(d_raw[k], d_min, d_max)
xI[k+1]   = xI[k] + (Ki·e[k] + 抗饱和修正[k]) · Δt
```

- `Kp` 单位：占空比 / V；`Ki` 单位：占空比 / (V·s)。
- 默认 `Kp = 0.0585`、`Ki = 117.66`、`d_min = 0.02`、`d_max = 0.90`。
- 前馈使稳态占空比接近 `Vref/Vin`，积分只负责消除残差。

## 2. 源码路径与真实接口

| 内容 | 路径 | 真实类/函数 |
| --- | --- | --- |
| 数据模型 | `control/models.py` | `ControllerConfig`、`ControlSample`、`ControllerDiagnostics`、`SoftStartConfig`、`CarrierConfig` |
| 离散控制器 | `control/pi_controller.py` | `PIController.update`、`feedforward_duty`、`reset`、`state_dict` |
| 抗饱和 | `control/anti_windup.py` | `clamp_duty`、`integral_increment`、`saturation_direction`、`back_calculation_correction` |
| SPICE 行为控制器 | `control/spice_controller.py` | `add_behavioral_pi_controller` |
| 配置文件 | `configs/controller_config.yaml` | `controller`、`soft_start`、`carrier`、`design` |

## 3. 参数来源（不是拍脑袋）

设计流程见 `control/controller_tuning.py::design_pi`：

```text
Kp = 1 / (|Gp(jωc)| · Gpwm · H · sqrt(1 + (fz/fc)²))
Ki = 2π·fz·Kp
```

- 目标穿越频率 `fc = 600 Hz`，PI 零点 `fz = 80 Hz`。
- 设计基准 `Gpwm = 1`；实际 sine 载波小信号增益约 `0.646`，因此真实穿越频率低于设计值。
- 线性化校验见文档 47，SPICE 复核见文档 48。

## 4. 与 SPICE 行为源的对应关系

`add_behavioral_pi_controller` 生成的行为源（节点顺序与极性经过实测修正）：

```text
BERR  err 0 V = V(ref) − V(out)
BFF   ff  0 V = V(ref)/max(V(vin), vin_min)
BPROP prop 0 V = kp·V(err)
BRAW  raw 0 V = V(ff) + V(prop) + V(integ)
BLIM  duty 0 V = min(max(V(raw), dmin), dmax)
CINT  integ 0 1 ic=0
BINT  0 integ I = ki·V(err) + kaw·(V(duty) − V(raw))
RILEAK integ 0 1e9
```

积分电流源必须写成 `BINT 0 integ ...`：节点顺序反了会变成正反馈，实测会发散。

## 5. 实际实验结果

### 5.1 离散控制器演示

来源：`results/stage7/demos/pi_controller_demo.json`（简单平均 LC 被控对象，非 SPICE）。

| 抗饱和 | 终值 Vout | 最大积分状态 | 占空比饱和比例 |
| --- | --- | --- | --- |
| none | 4.2012 V | 0.2623 | 61.41 % |
| conditional | 4.2000 V | 0.0000 | 43.27 % |
| back_calculation | 4.2000 V | 0.0000 | 45.92 % |

三种方法都能跟踪 4.2 V 参考，但 `none` 在参考下阶跃后积分储能更大，
说明抗饱和不是“可选装饰”。

### 5.2 开关级闭环

来源：`results/stage7/demos/closed_loop_buck_demo.json`（E 变体，25 ns）。

- 闭环稳态 4.9991 V，纹波 27.5 mV，平均占空比约 0.445。
- 开环（固定 0.4448）稳态 5.0059 V，纹波 19.3 mV。
- 开环 25 ns 出现 `Timestep too small`，显式回退到 50 ns 并写入
  `metadata["step_fallback"]`；没有把回退结果冒充原始步长。

## 6. 适用条件

1. 电压模式控制，输出电压直接反馈；不含电流环。
2. 开关频率 100 kHz，采样率按 1 µs 记录；控制更新在 SPICE 中连续时间执行。
3. 占空比限幅 0.02～0.90，前馈输入下限 2 V。

## 7. 局限性

- 没有数字 PWM 的采样保持与一拍延迟；SPICE 行为源是连续比较。
- 没有输出电容 ESR 零点补偿、没有输入电压前馈的滤波。
- 参数是教学级设计，不代表量产控制器鲁棒性。
- 积分器使用理想电容 + 1 GΩ 泄漏，长期直流精度仍受数值误差影响。

## 8. 技术面试题

1. 为什么 PI 控制器的零点要放在穿越频率以下？如果放在穿越频率以上会怎样？
2. 前馈项 `Vref/Vin` 与积分项的分工是什么？去掉前馈后稳态误差如何变化？
3. 为什么 `Kp` 的量纲是占空比/V，而 `Ki` 多了一个 1/s？
4. SPICE 行为源 PI 与离散 PI 在“采样”上有什么区别？哪种更接近真实数字控制？
5. 积分器电流源节点顺序写反为什么会导致发散？如何从网表上判断极性？
6. 占空比上限 0.90 是保护还是设计约束？接近上限时环路会发生什么？
7. 如果把 `Ki` 提高 10 倍，预计穿越频率、相位裕度和启动超调如何变化？
