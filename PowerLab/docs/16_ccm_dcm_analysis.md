# 16 CCM、DCM 与临界模式分析

本文用三种真实负载工况解释电感电流导通模式。全部数据来自 ngspice 瞬态仿真，
仿真时长 20 ms，其余参数与默认工况一致。

## 1. 三种模式

- **CCM（连续导通模式）**：整个开关周期内 `IL > 0`，电流为连续三角波。
- **DCM（断续导通模式）**：电感电流在周期结束前降到零，并保持为零一段时间；
  二极管截止，开关节点出现高阻段。
- **BCM（临界导通模式）**：电感电流恰好在周期结束时降到零，是 CCM/DCM 的分界。

理想临界电流与临界电阻：

```
Iboundary = ΔIL / 2
Rboundary = Vout / Iboundary
```

默认参数：`ΔIL=0.620567 A`，`Iboundary=0.310284 A`，`Rboundary=16.114 Ω`。

## 2. 识别算法

实现位置：[conduction_mode.py](file:///PowerLab/analysis/conduction_mode.py)
`classify_conduction_mode()`。

不能只用 `min(IL) == 0` 判断 DCM，因为真实波形存在二极管漏电、关断电阻和数值误差。
算法使用：

- 近零阈值 `max(0.02 A, 2% × 峰值电流)`；
- 时间加权近零占比（梯形积分，不按采样点数）；
- 占比 ≥ 2% 判 DCM，≤ 0.5% 判 CCM，中间判 `BOUNDARY_OR_UNCERTAIN`；
- 明显反向电流（低于 `-max(3×0.02 A, 2%×峰值)`）记为 `INVALID` 异常，不强行贴标签。

只使用稳态窗口内的完整周期，避免启动大电流把谷值抬高造成误判。

## 3. 三种真实工况

| 工况 | 负载 | 平均输出电压 | 峰值电流 | 谷值电流 | 近零占比 | 识别结果 |
| --- | --- | --- | --- | --- | --- | --- |
| 重载 | 2.5 Ω | 4.7814 V | 2.2326 A | 1.5926 A | 0% | CCM |
| 临界附近 | 16.1144 Ω | 4.9316 V | 0.6269 A | 3.85e-6 A | 5.53% | DCM |
| 轻载 | 50 Ω | 7.2189 V | 0.4240 A | -2.92e-6 A | 35.04% | DCM |

三者均达到预设稳态条件并通过验证。

图：[inductor_current_modes.png](file:///PowerLab/results/buck/run_20261125_115042_d4dd77aa/plots/inductor_current_modes.png)。

## 4. 临界点的处理

理想计算给出 `Rboundary=16.114 Ω`。实测 16.1144 Ω 时：

- 谷值电流约 3.85 µA，接近零；
- 近零时间占比 5.53%，超过 2% 的 DCM 阈值；
- 因此识别为 DCM，而不是强行判为「临界」。

这说明理想临界点附近对参数、数值误差和纹波非常敏感。验证模块对临界/不确定模式
输出 `NOT_APPLICABLE`，不假装 CCM 理论仍然成立。

## 5. 轻载输出电压升高

50 Ω 轻载实测 `Vout=7.2189 V`，明显高于 5 V。原因是开环固定占空比：

- CCM 下 `Vout = D·Vin`；
- 进入 DCM 后，占空比与输出电压的关系变为
  `M = 2 / (1 + sqrt(1 + 4K/D²))`，其中 `K = 2L/(R·T)`；
- 负载电阻增大 → K 减小 → M 增大 → 输出电压升高。

理想 DCM 公式给出约 7.25 V，实测 7.2189 V，趋势与量级一致。这验证了
「轻载输出升高」是 DCM 的真实物理现象，而不是仿真错误。

## 6. 理想 CCM 公式的局限性

在 DCM 下以下公式不再成立：

```
Vout = D * Vin
ΔIL = (Vin - Vout) * D / (L * fsw)
```

因为电感电流在每个周期内归零，平均电流与负载、L、f 的关系改变。验证模块因此：

- 当识别为 DCM 时，将 `ideal_ccm_output_voltage`、`inductor_current_ripple`、
  `output_voltage_ripple` 标记为 `NOT_APPLICABLE`；
- 仍检查频率、占空比、能量平衡、数据质量与输出纹波设计目标；
- 不把 DCM 工况判成 CCM 理论失败。

## 7. 复现方式

```powershell
conda run -n kaifa_power python -m scripts.buck_ccm_dcm_demo
```

输出目录：`results/buck_stage3/ccm_dcm_<timestamp>_<uuid8>/`，包含
`ccm_dcm.json`、`ccm_dcm.csv`，以及三次独立运行的完整结果目录。
