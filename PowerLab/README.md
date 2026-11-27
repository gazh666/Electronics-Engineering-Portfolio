# PowerLab — 电源电路仿真与性能验证平台

PowerLab 是基于 PySpice 1.5 与 ngspice 的应用层二次开发项目，面向电源测试、电源硬件、
模拟芯片 AE/FAE 与半导体测试岗位的工程能力训练。

当前进度：**第三阶段（非同步 Buck 开环瞬态仿真）已完成**。
第二阶段的分压、RC、RL、RLC、二极管与半波整流 11 项分析全部保留并通过回归；
第三阶段新增 Buck 电路构建、PWM、开关/二极管模型、真实瞬态仿真、稳态与纹波分析、
CCM/DCM 识别、理论对照验证。仍不包含闭环控制、MOSFET 非理想模型、Web 平台或
TestLab 数据接入。

> 数据性质：所有电压、电流、波形均来自本机 ngspice 真实求解，标签为
> `data_source = spice_simulation`，不是 Python 理论公式冒充的仿真结果。

## 1. 环境

| 项目 | 实际值 |
| --- | --- |
| 操作系统 | Windows 10.0.26200（`platform` 报告），AMD64 |
| Conda | 25.5.1 |
| 环境名 | `kaifa_power` |
| 解释器 | `C:\\Users\\<user>\.conda\envs\kaifa_power\python.exe` |
| Python | 3.11.18（64 bit） |
| PySpice | 1.5（PyPI 安装） |
| ngspice | ngspice-34 64 位共享库（`ngspice-34.dll`） |
| 后端方式 | PySpice `NgSpice.Shared`（CFFI `ffi.dlopen`） |

依赖锁定见 `requirements.txt` 与 `requirements-dev.txt`；ngspice DLL 的安装步骤见
`docs/01_environment_setup.md`（不能只靠 pip 安装系统级仿真器）。

## 2. 安装与验证

```powershell
conda create -n kaifa_power python=3.11 pip -y
conda run -n kaifa_power python -m pip install -r requirements.txt
conda run -n kaifa_power python -m pip install -r requirements-dev.txt
conda run -n kaifa_power pyspice-post-installation --install-ngspice-dll

conda run -n kaifa_power python -m scripts.verify_environment
```

`verify_environment` 必须完成一次真实分压求解才返回 0；只 `import PySpice` 不算通过。

## 3. 运行

```powershell
conda run -n kaifa_power python -m scripts.dc_analysis_demo
conda run -n kaifa_power python -m scripts.rc_ac_demo
conda run -n kaifa_power python -m scripts.rl_transient_demo
conda run -n kaifa_power python -m scripts.rlc_demo
conda run -n kaifa_power python -m scripts.diode_iv_demo
conda run -n kaifa_power python -m scripts.rectifier_demo
conda run -n kaifa_power python -m scripts.basic_circuits_demo

conda run -n kaifa_power python -m scripts.buck_theory_demo
conda run -n kaifa_power python -m scripts.buck_basic_demo
conda run -n kaifa_power python -m scripts.buck_startup_demo
conda run -n kaifa_power python -m scripts.buck_steady_state_demo
conda run -n kaifa_power python -m scripts.buck_duty_demo
conda run -n kaifa_power python -m scripts.buck_ccm_dcm_demo
conda run -n kaifa_power python -m scripts.buck_stage3_demo

conda run -n kaifa_power python -m pytest tests -v
```

`basic_circuits_demo` 串行执行 11 项分析，并在
`results/basic_circuits/summary_<run_id>.json/.csv` 写出汇总；任一分析失败都会标记
`FAILED` 并使退出码非零，不会用理论数据填补。

每次运行都会在 `results/` 下创建唯一目录（时间戳 + 8 位随机码），不覆盖历史结果。

## 4. 目录

```text
PowerLab/
├── circuits/            分压/RC/RL/RLC/二极管/整流 + Buck 配置、PWM、开关/二极管、拓扑
├── simulations/         统一执行器、配置、后端探针、波形提取、Buck 瞬态入口
├── analysis/            理论公式、误差指标、频率响应、稳态、CCM/DCM、Buck 验证
├── storage/             结果目录与固定文件写出
├── visualization/       Matplotlib（Agg）绘图
├── configs/             simulation.yaml、basic_circuits.yaml、buck_config.yaml、buck_validation.yaml
├── scripts/             环境验证、第二阶段 7 个入口、第三阶段 8 个入口
├── tests/               249 项 Pytest（含 118 项第三阶段新增，含真实 ngspice）
├── results/             运行产物（已 gitignore）
└── docs/                01–17 环境、原理、分析与阶段验收文档
```

## 5. 第一阶段真实结果

| 项目 | 结果 |
| --- | --- |
| 分压电路 | 12.000000 V → 6.000000 V，绝对误差 0 V |
| RC 瞬态 | 619 个采样点，0–6 ms，τ = 1 ms |
| 1τ | 仿真 3.159684 V，理论 3.160603 V，误差 0.919 mV |
| 5τ | 仿真 4.966295 V，理论 4.966310 V，误差 0.0157 mV |
| 全区间最大绝对误差 | 2.498 mV（主要来自 1 μs 有限上升时间） |
| RMSE | 0.760 mV |
| Pytest | 22 passed（第一阶段基线，现仍全量保留） |

## 6. 第二阶段真实结果

| 分析 | 关键结果 |
| --- | --- |
| 分压 OP / DC | 6.000000 V；25 点斜率 0.5，最大误差 \(8.88\times10^{-16}\) V |
| RC 充放电 | 1229 点；1τ 误差 -0.919 mV；放电初值 4.986372 V |
| RC 低通 AC | 251 点；fc=159.1482 Hz（误差 -0.00421%）；-3.0105 dB / -44.9988° |
| RL 阶跃 | 619 点；1τ 电流 0.315968 A（误差 -0.0919 mA） |
| RLC 10 Ω | 40017 点；过冲 85.4443%（理论 85.4468%）；调节 7.602 ms |
| RLC 200 Ω | 40017 点；无过冲；调节 0.584 ms |
| RLC 400 Ω | 40017 点；无过冲；调节 1.489 ms |
| RLC AC | 801 点；峰值 10.0069 V @ 1584.893 Hz（理论 1587.566 Hz） |
| 二极管 IV | 181 点；0.8 V 时 24.8795 mA；反偏 -1.0009 nA |
| 半波整流 | 5008 点；平均 2.831794 V / RMS 4.534981 V / 功率 0.020566 W |
| 综合演示 | 11/11 PASS，10 条验收命令退出码均为 0 |
| Pytest | 131 passed（11.99 s） |

## 7. 第三阶段真实结果（默认工况）

| 指标 | 理论（理想 CCM） | 真实 SPICE |
| --- | --- | --- |
| PWM 频率 / 占空比 | 100 kHz / 0.4166667 | 100 kHz / 0.4166667（阈值实测） |
| 输出平均电压 | 5.000 V | 4.7813 V |
| 平均输出电流 | 2.000 A | 1.9126 A |
| 电感峰值 / 谷值 | 2.3103 / 1.6897 A | 2.2327 / 1.5925 A |
| 电感电流纹波 | 0.6206 A | 0.6402 A |
| 输出纹波 | 7.757 mVpp | 8.139 mVpp |
| 伏秒平衡相对误差 | 0 | \(3.39\times10^{-10}\) |
| 电荷平衡相对误差 | 0 | \(2.40\times10^{-6}\) |
| 稳态窗口 | — | 4.790–4.990 ms，20 个周期 |
| 启动峰值 | — | 7.8463 V / 7.7124 A |
| 综合演示 | — | 10 次真实运行，全部检查 PASS |
| Pytest | — | 249 passed（20.04 s） |

不同负载：2.5 Ω 为 CCM；16.1144 Ω 与 50 Ω 为 DCM，50 Ω 输出电压升到 7.2189 V。
不同占空比（0.25/0.4167/0.5/0.6）实测输出 2.7312/4.7814/5.8094/7.0446 V。
时间步长 100/50/25 ns 的输出纹波相对差异为 \(4.45\times10^{-5}\)。

## 8. 边界

- 本阶段没有真实硬件；所有波形均为 ngspice 仿真，不是硬件测量。
- 开关为 ngspice `SW` 近理想模型，二极管为教学参数模型，不含栅极电荷、
  开关损耗、结电容、反向恢复与温度漂移。
- 开环固定占空比，没有闭环、软启动、电流环；负载变化时输出不稳压。
- 器件选型所需的饱和电流、DCR、ESR、耐压、纹波电流额定值尚未建模。
- PySpice 与 ngspice 原始源码未修改；PowerLab 只做应用层封装。
- 理论公式仅用于对照，不作为仿真数据来源。
- Docker、Linux、GitHub Actions、ngspice 精确许可证版本：`NOT_VERIFIED`。
