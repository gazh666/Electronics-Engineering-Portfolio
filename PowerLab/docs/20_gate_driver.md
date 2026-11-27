# 20 浮动高侧栅极驱动

## 1. 电路结构

Model D/E 用 NMOS 替代 `SW` 后，栅极必须相对**开关节点** `sw` 驱动，而不是相对地。
本阶段使用理想浮动电压源实现：

```text
VDRV drv sw DC 0V PULSE(0 10 10u 20n 20n 4.1466667u 10u)
RG   drv gate 10
RGS  gate sw  100k
```

- 驱动电压 10 V，低电平 0 V，高电平时间由占空比 0.4166667 决定。
- `VGS = V(gate) − V(sw)`。
- 栅极终端电流 `IG = (V(drv) − V(gate)) / RG − V(gate,sw) / RGS`。

这**不是 Bootstrap 电路**：没有自举电容、没有充电二极管、没有 UVLO、没有驱动供电跌落。
它只是把“相对开关节点的高侧驱动”这一必要边界条件真实接入求解器。

## 2. 栅极电阻对照（真实 5 ms 瞬态）

运行：`conda run -n kaifa_power python -m scripts.gate_driver_demo`
（Model E，稳态 2 个周期用于绘图）。

| RG | VGS max | IG 峰值 | RG 损耗 | RGS 损耗 | 开关能量（20 周期） | 功率级效率 | 求解步长 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2.2 Ω | 10.0083 V | 1.107 A | 4.283 mW | 0.416 mW | 2.444 µJ | 93.0063 % | 25 ns |
| 10 Ω | 9.9990 V | 0.616 A | 9.905 mW | 0.415 mW | 4.001 µJ | 92.9356 % | 25 ns |
| 22 Ω | 9.9993 V | 0.320 A | 12.090 mW | 0.413 mW | 6.703 µJ | 92.8335 % | 20 ns（重试 1 次） |

结果目录：`results/nonideal_buck/run_20261125_131243_465a1198/gate_driver_summary.csv`。

观察：

1. RG 越大，栅极电流峰值越小，但开关过程越长，开关能量与 RG 损耗越大，效率下降。
2. RG = 2.2 Ω 时 VGS 峰值 10.0083 V，存在 **8.3 mV 过冲**，来自 Cgd 在漏极快速跳变时的耦合；
   这不是驱动器过冲模型，而是真实寄生反馈。
3. RG = 22 Ω 在 25 ns 最大步长下触发 ngspice `timestep too small`，脚本自动改用 20 ns
   重试并成功；重试记录写入 `metadata.json` 的 `convergence_retries`，没有隐藏失败。

## 3. 损耗边界

- `P_RG = Irms(IRG)² · RG`，其中 `IRG` 是流过 RG 的电流。
- `P_RGS = ⟨VGS² / RGS⟩`。
- 驱动器自身输出功率 `Pdrv = ⟨V(drv) − V(sw) 端口功率⟩`，只进入系统级效率分母，
  **不重复计入** RG/RGS 损耗。

## 4. 限制

- 理想电压源：无输出阻抗、无电流限幅、无欠压锁定。
- 无自举电容充放电，因此不能研究高占空比下的驱动电压跌落。
- 无驱动器 IC 自身损耗模型；`Pdrv` 只是端口功率，不等于芯片功耗。
- `RG = 22 Ω` 的数值收敛需要更小步长，说明模型在该工况下偏“硬”，不能据此断言真实电路会振荡。

## 5. 复现命令

```powershell
$env:PYTHONPATH='PowerLab'
conda run -n kaifa_power python -m scripts.gate_driver_demo
```

输出：`gate_driver_vgs.png`、`gate_driver_current.png`、`gate_driver_summary.csv`。
