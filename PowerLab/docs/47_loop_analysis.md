# 47 环路分析与稳定性判定

## 1. 分析对象与边界

第七阶段只对**平均模型的线性化环路**做频域分析：

- 被控对象：`control/averaged_buck.py` 在稳态工作点附近数值雅可比线性化；
- 控制器：PI（`Kp`、`Ki`）；
- 调制器增益：正弦载波小信号增益 `g(d)`；
- 反馈：单位增益（输出电压直接反馈）。

这不是对开关电路做 SPICE AC 分析，也不包含 PWM 采样效应、数字延迟与死区。

## 2. 源码路径与真实接口

| 内容 | 路径 | 真实函数 |
| --- | --- | --- |
| 传递函数 | `control/transfer_functions.py` | `TransferFunction`、`ideal_buck_control_to_output`、`nonideal_buck_control_to_output`、`frequency_grid` |
| 环路 | `control/loop_analysis.py` | `loop_gain`、`analyze_loop`、`closed_loop_characteristic`、`closed_loop_poles`、`classify_poles`、`bandwidth_hz` |
| 工作点与载波增益 | `analysis/stability_analysis.py` | `solve_operating_duty`、`carrier_small_signal_gain`、`stability_report`、`judge_stability_limits` |
| 演示 | `scripts/loop_analysis_demo.py` | 生成 Bode CSV/JSON |

## 3. 公式

### 3.1 环路增益

```text
T(s) = [Kp + Ki/s] · Gp(s) · Gpwm · H
```

`Gp(s)` 由平均模型线性化得到；`Gpwm = (2/π)/sqrt(1−(2d−1)²)`；`H = 1`。

### 3.2 相位裕度与增益裕度

```text
PM = 180° + ∠T(jωc)，其中 |T(jωc)| = 1
GM = −20·log10|T(jω180)|，其中 ∠T(jω180) = −180°
```

若在分析频段内没有 −180° 穿越，则 `GM = NaN`，判定为 `NOT_RESOLVED`，
不能写成“无穷大裕度”或“通过”。

### 3.3 闭环极点

```text
1 + T(s) = 0
```

`classify_poles` 依据最大实部判定 `STABLE / MARGINAL / UNSTABLE / NOT_RESOLVED`。

## 4. 实际实验结果

来源：`results/stage7/demos/loop_analysis_demo.json` 与
`results/stage7/experiments/controller_tuning.json`（真实运行）。

| 指标 | 数值 |
| --- | --- |
| 工作点有效占空比 | 0.4448006 |
| 载波小信号增益 | 0.6463 |
| 0 dB 穿越次数 | 3 |
| 穿越频率 / 相位裕度 | 165.74 Hz / 115.94°；1902.96 Hz / 128.58°；2527.98 Hz / 63.49° |
| 最小相位裕度 | 63.49° |
| 增益裕度 | `NaN`（无 −180° 穿越）→ `NOT_RESOLVED` |
| 闭环极点状态 | `STABLE`，最大实部 −637.3 |
| 闭环带宽 | 113.9 Hz |

三个 0 dB 穿越来自 LC 双极点、ESR 零点与 PI 零点的组合；不能只看最后一个穿越，
报告取最小相位裕度作为保守结论。

## 5. 图表

- `results/stage7/experiments/selected_loop_bode.csv`：频率、幅值 dB、相位°
- `results/stage7/figures/loop_gain_bode.png`：报告脚本生成的双子图
- `results/stage7/experiments/selected_closed_loop_poles.csv`：闭环极点
- `results/stage7/experiments/controller_tuning_matrix.csv`：9 组参数的 PM/GM/带宽/评分

## 6. 适用条件

1. 小信号、线性化、连续时间近似。
2. 工作点由平均模型解出；大信号阶跃必须回到 SPICE 验证。
3. 载波增益取稳态占空比处的一阶导数。

## 7. 局限性

- 不含采样保持与 PWM 边沿，数字控制的相位损失未建模。
- 多个 0 dB 穿越使“单一穿越频率”叙述不严谨；本阶段显式报告全部穿越。
- 无 −180° 穿越时 `GM` 无定义，验收保留 `NOT_RESOLVED`。
- 线性化基于教学级器件参数，不能替代器件级环路实测。

## 8. 技术面试题

1. 为什么本阶段会出现三个 0 dB 穿越？每个穿越由什么造成？
2. 相位裕度 63.49° 看起来很好，为什么 SPICE 负载阶跃仍有约 0.55 V 偏差？
3. 没有 −180° 穿越时，增益裕度应该写“无穷大”还是“未解决”？为什么？
4. 载波小信号增益 0.646 与设计值 1 的差异，会把穿越频率拉低多少？
5. 闭环极点最大实部 −637.3 对应的时间常数是多少？与 258 Hz 带宽是否一致？
6. 如果加入 1 拍数字延迟，相位裕度大约下降多少？如何估算？
