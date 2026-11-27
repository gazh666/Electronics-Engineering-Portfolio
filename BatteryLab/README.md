# BatteryLab

3S 锂电池管理、模拟采集与充放电保护电路设计（第一阶段）。

英文名称：BatteryLab — Battery Management, Power Electronics & Engineering Validation。

## 项目定位

- 使用 PyBaMM 官方电化学模型（SPM / Thevenin）进行真实数值仿真。
- 使用 CALCE 官方公开实验数据（INR18650-20R）进行真实数据解析、质量检查与绘图。
- 使用 PySpice + ngspice 验证后续模拟采集电路所需的电路仿真后端。
- 研究 TI BQ76922 官方资料，形成 3S BMS 系统架构与设计计算。

本项目是学习型工程实现，**没有真实硬件实验条件**，不将仿真结果或公开数据描述为本人硬件实测。

## 环境

```powershell
conda create -n kaifa_battery python=3.11 pip -y
conda run -n kaifa_battery python -m pip install -r requirements.txt
conda run -n kaifa_battery python -m pip install -r requirements-dev.txt
conda run -n kaifa_battery pyspice-post-installation --install-ngspice-dll
```

ngspice 为系统级二进制依赖（ngspice-34 64 位 DLL），由 PySpice 安装脚本下载到当前环境，
不修改 Windows 全局 PATH。

## 常用命令

```powershell
conda run -n kaifa_battery python -m scripts.verify_environment
conda run -n kaifa_battery python -m scripts.pybamm_spm_demo
conda run -n kaifa_battery python -m scripts.pybamm_thevenin_demo
conda run -n kaifa_battery python -m scripts.battery_charge_discharge_demo
conda run -n kaifa_battery python -m scripts.spice_environment_demo
conda run -n kaifa_battery python -m scripts.download_calce_data
conda run -n kaifa_battery python -m scripts.calce_data_demo
conda run -n kaifa_battery python -m scripts.battery_stage1_demo
conda run -n kaifa_battery python -m pytest tests -q
```

## 数据来源分类

`pybamm_simulation`、`spice_simulation`、`public_experimental_data`、`analytical_theory`、
`project_assumption`、`datasheet_specification`、`synthetic_test_data`。

结果目录 `results/` 按运行 ID 保存，不覆盖历史结果；JSON 中不允许出现 NaN/Infinity。

## 文档

- docs/01_environment_setup.md
- docs/02_pybamm_upstream_analysis.md
- docs/03_battery_fundamentals.md
- docs/04_battery_simulation_baseline.md
- docs/05_calce_dataset_analysis.md
- docs/06_bms_chip_study.md
- docs/07_battery_system_architecture.md
- docs/08_stage1_validation.md

## 许可与引用

PyBaMM、PySpice、ngspice 为上游开源项目，BatteryLab 只做应用层封装，未修改上游源码。
CALCE 数据引用需遵循官方页面说明；TI 数据手册仅用于设计学习。
