# 17 第三阶段验收报告：非同步 Buck 开环瞬态仿真

日期：2026-11-25。环境：Windows，`kaifa_power` conda 环境，Python 3.11，
PySpice 1.5.0，ngspice-34 DLL，25 °C。所有数据来自真实 ngspice 运行。

## 1. 阶段目标与完成情况

| 任务书要求 | 状态 | 证据 |
| --- | --- | --- |
| 非同步 Buck 拓扑与可配置参数 | 完成 | `circuits/buck.py`、`configs/buck_config.yaml` |
| PWM（频率/占空比/边沿/延迟） | 完成 | `circuits/pwm.py`，阈值实测占空比 |
| 开关与二极管模型 | 完成 | `circuits/switch_models.py` |
| 真实瞬态仿真 | 完成 | `simulations/buck_runner.py`，118512 点 |
| 启动过程 | 完成 | `buck_startup_demo`，峰值 7.8463 V |
| 稳态与纹波 | 完成 | 20 周期窗口，`buck_steady_state_demo` |
| 占空比影响 | 完成 | 4 个占空比真实运行 |
| CCM / DCM / 临界 | 完成 | 2.5 / 16.1144 / 50 Ω，识别有证据 |
| 理论对照与验证 | 完成 | 10 项检查 PASS |
| 测试 | 完成 | 新增 118 项，总 249 项通过 |
| 文档 11–17 | 完成 | 本文及 `docs/11`–`docs/16` |
| 闭环 / 电流环 / MOSFET / Web / AI | **未做（按要求暂停）** | — |

## 2. 验收命令与退出码

以下命令均在 `PowerLab` 下顺序执行，使用
`conda run -n kaifa_power python ...`：

| # | 命令 | 退出码 | 关键结果 |
| --- | --- | --- | --- |
| 1 | `python -m scripts.verify_environment` | 0 | `status: OK`，读取/写入探测通过 |
| 2 | `python -m scripts.buck_theory_demo` | 0 | Vout=5.000 V、ΔIL=0.620567 A、ΔV=7.757 mV |
| 3 | `python -m scripts.buck_basic_demo` | 0 | Vout 纹波 8.139 mVpp、IL 纹波 0.640233 A、validation PASS |
| 4 | `python -m scripts.buck_startup_demo` | 0 | 峰值电流 7.712358 A、Vout 稳定 1.4136 ms、IL 稳定 1.7150 ms |
| 5 | `python -m scripts.buck_steady_state_demo` | 0 | 伏秒 3.390e-10、电荷 2.395e-06、checks PASS |
| 6 | `python -m scripts.buck_duty_demo` | 0 | D=0.5 → 5.8094 V；D=0.6 → 7.0446 V；全部 CCM/稳态/PASS |
| 7 | `python -m scripts.buck_ccm_dcm_demo` | 0 | 16.114 Ω 与 50 Ω 均为 DCM；50 Ω 近零占比 35.04% |
| 8 | `python -m scripts.buck_stage3_demo` | 0 | 10 次真实运行，7 项检查全部 PASS |
| 9 | `python -m pytest tests -v` | 0 | `249 passed in 20.04s` |
| 10 | `python -m pip check` | 0 | `No broken requirements found.` |

## 3. 测试覆盖

原有 131 项测试全部保留且通过；新增 118 项，分布如下：

| 文件 | 内容 |
| --- | --- |
| `tests/test_pwm.py` | PWM 派生量、非法占空比/频率/边沿、时间分辨率 |
| `tests/test_buck_config.py` | YAML 加载、缺字段、跨字段一致性 |
| `tests/test_buck_theory.py` | 理想 CCM/DCM 公式、反推公式、边界负载 |
| `tests/test_buck_builder.py` | 网表元件、节点连接、参数变化、类型检查 |
| `tests/test_buck_waveforms.py` | 列转换、电流符号、阈值插值、PWM 统计 |
| `tests/test_steady_state.py` | 时间加权平均、切窗、稳态判定、伏秒/电荷平衡、稳定时间 |
| `tests/test_conduction_mode.py` | CCM/DCM/临界/反向异常、理论模式比较 |
| `tests/test_buck_validation.py` | 状态优先级、DCM 的 NOT_APPLICABLE、未稳态 |
| `tests/test_buck_integration.py` | 真实 ngspice 5 ms / 20 ms / 占空比对比、失败传播 |

集成测试对以下行为做了真实校验：

- 时间轴严格递增、数值有限、点数 > 10000；
- gate 为 0/5 V，开关节点在 0 V 与 12 V 之间切换；
- PWM 频率 100 kHz、占空比 5/12 由阈值交点测得；
- 重载 CCM、轻载 DCM，轻载输出不强行等于 5 V；
- 占空比 0.25 → 0.5 时真实输出电压上升超过 1 V；
- 后端异常时抛出 `RuntimeError`，失败记录中不存在 `waveform.csv`。

## 4. 综合演示结果

最新综合运行：`results/buck_stage3/stage3_20261125_115941_72bb5f07/`，
基础运行：`results/buck/run_20261125_115857_c3aac141/`。

| 检查 | 状态 |
| --- | --- |
| default_case_steady | PASS |
| default_validation | PASS |
| duty_sweep_all_steady | PASS |
| mode_heavy_ccm | PASS |
| mode_light_dcm | PASS |
| time_step_respected | PASS |
| timestep_ripple_sensitivity | PASS |

默认工况：`CCM`、`STEADY_STATE`、`Vout=4.7813 V`、纹波 `8.139 mVpp`、
`validation=PASS`。时间步长 100/50/25 ns 的输出纹波相对差异
\(4.45\times10^{-5}\)，最大步长约束均遵守。

## 5. 验证限值与实测

| 检查 | 实测 | 参考 | 误差 | 限值 | 状态 |
| --- | --- | --- | --- | --- | --- |
| PWM 频率 | 100 kHz | 100 kHz | ~1e-16 | 1% | PASS |
| PWM 占空比 | 0.4166667 | 0.4166667 | ~7e-15 | 0.005 | PASS |
| 理想 CCM 电压 | 4.7813 V | 5.000 V | -4.37% | 10% | PASS |
| 电感纹波 | 0.6402 A | 0.6206 A | +3.17% | 15% | PASS |
| 输出纹波 | 8.139 mV | 7.757 mV | +4.92% | 25% | PASS |
| 导通模式 | CCM | CCM | — | — | PASS |
| 伏秒平衡 | 3.39e-10 | 0 | 3.39e-10 | 15% | PASS |
| 电荷平衡 | 2.40e-6 | 0 | 2.40e-6 | 15% | PASS |
| 纹波设计目标 | 8.139 mVpp | ≤50 mVpp | -41.9 mV | 50 mV | PASS |
| 波形质量 | — | — | — | — | PASS |

## 6. 关键真实数据

| 项目 | 数值 |
| --- | --- |
| 默认稳态窗口 | 4.79001–4.99001 ms，20 个完整周期 |
| 输出平均电压 / 电流 | 4.7813 V / 1.9126 A |
| 电感峰值 / 谷值 / 纹波 | 2.2327 A / 1.5925 A / 0.6402 A |
| 输出纹波 | 8.139 mVpp |
| 输入平均电流 | 0.79695 A |
| 启动输出峰值 / 超调 | 7.8463 V / 64.1% |
| 启动电感峰值 | 7.7124 A（3.86× 额定） |
| 启动稳定时间 | Vout 1.4136 ms，IL 1.7150 ms |
| 占空比 0.25 / 0.4167 / 0.5 / 0.6 | 2.7312 / 4.7814 / 5.8094 / 7.0446 V |
| 负载 2.5 / 16.1144 / 50 Ω | CCM / DCM / DCM；50 Ω 时 7.2189 V |
| 时间步长 100 / 50 / 25 ns | 69518 / 118512 / 217018 点 |

## 7. 已知限制

1. 全部为仿真数据，不是硬件测量，不构成实验验证。
2. 开关为 `SW` 压控电阻模型，无栅极电荷、开关损耗、Coss、体二极管。
3. 二极管无结电容与反向恢复。
4. 开环固定占空比，负载变化时输出不稳压；无软启动与保护。
5. 未做器件应力、效率、热、EMI 与环路稳定性分析。
6. 临界负载附近（16.1144 Ω）对数值误差敏感，识别为 DCM 而非强行判临界。
7. 单次 20 ms 轻载运行波形约 55–60 MB，未做结果裁剪策略。

## 8. 暂停声明

第三阶段按要求在此暂停：

- 未实现闭环电压控制、电流环、软启动、保护逻辑；
- 未实现 MOSFET 非理想模型与驱动电路；
- 未实现 Web 界面、AI 助手、TestLab 数据接入；
- 未修改 `kaifa`、TestLab、PySpice 或 ngspice 源码；
- 未删除第二阶段的任何结果。

下一阶段需等待新的任务书。
