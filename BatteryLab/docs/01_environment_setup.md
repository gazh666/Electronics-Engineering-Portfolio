# 01 环境搭建与验证

## 1. 项目路径

| 项目 | 实际路径 |
| --- | --- |
| BatteryLab | `BatteryLab` |
| 上游只读参考：PyBaMM | `PyBaMM-main` |
| 上游只读参考：PySpice | `PySpice-master` |
| 前置项目：TestLab | `TestLab`（未修改） |
| 前置项目：PowerLab | `PowerLab`（未修改） |

## 2. Conda 环境

```powershell
conda create -n kaifa_battery python=3.11 pip -y
conda run -n kaifa_battery python --version
```

实际结果：`Python 3.11.18`，环境位置 `C:\\Users\\<user>\.conda\envs\kaifa_battery`。
`kaifa` 与 `kaifa_power` 环境未修改。

## 3. 实际安装版本

| 包 | 版本 | 来源 |
| --- | --- | --- |
| pybamm | 26.11.0.0 | PyPI |
| numpy | 2.4.6 | PyPI |
| scipy | 1.17.1 | PyPI |
| pandas | 3.1.1 | PyPI |
| matplotlib | 3.11.2 | PyPI |
| openpyxl | 3.1.5 | PyPI |
| PyYAML | 6.0.4 | PyPI |
| requests | 2.34.2 | PyPI |
| PySpice | 1.5 | PyPI |
| pypdf | 7.1.1 | PyPI（读取 TI 数据手册） |
| pytest | 9.2.0 | PyPI（开发依赖） |

`conda run -n kaifa_battery python -m pip check` 实际输出：`No broken requirements found.`

## 4. ngspice 后端

ngspice 是系统级二进制依赖，不是 Python 包。安装方式（官方 PySpice 提供）：

```powershell
conda run -n kaifa_battery pyspice-post-installation --install-ngspice-dll
```

实际结果：

- 从 SourceForge 备用地址 `ng-spice-rework/old-releases/34/ngspice-34_dll_64.zip` 下载成功；
- DLL 路径：`C:\\Users\\<user>\.conda\envs\kaifa_battery\Lib\site-packages\PySpice\Spice\NgSpice\Spice64_dll\dll-vs\ngspice.dll`；
- `NgSpiceShared.new_instance().ngspice_version` 实际返回 `34`；
- 未修改 Windows 全局 PATH，未安装系统级软件，未请求管理员权限。

## 5. 环境验证脚本

```powershell
conda run -n kaifa_battery python -m scripts.verify_environment
```

真实执行了 PyBaMM SPM 60 秒求解与 ngspice 5V→2.5V 分压求解，结果：

- 18 项检查全部 PASS；
- `pybamm_backend_status = PASS`（SPM 60 s，V_end = 3.765996 V，I = 0.680616 A，求解器 IDAKLUSolver）；
- `ngspice_backend_status = PASS`（分压输出 2.500000000 V，误差 0.000e+00 V）；
- 结果文件：`results/stage1/run_stage1_20261126_113955_238dc6/summary.json`。

两个后端分别判定，未混为一个状态。

## 6. 依赖清单文件

- `requirements.txt`：运行依赖（锁定版本）。
- `requirements-dev.txt`：追加 pytest。
- `environment.yml`：Conda 环境定义，Python 依赖走 pip。
- ngspice DLL 不写入 requirements，安装方式见第 4 节。

## 7. 实际遇到的问题

| 问题 | 处理 |
| --- | --- |
| `SP3_25C_IC_OCV_12_2_2015.zip` 首次下载连接超时 | 下载器内置重试；第二次运行成功（16,022,212 B） |
| 并行执行两条 `conda run` 时临时文件冲突 | 改为串行执行 |
| PyBaMM 26.11 的 `Simulation.solve` 不接受 `show_progress` | 按实际签名调用 |
| 默认 `Cell temperature` 变量长度与时间轴不一致 | 波形提取时按时间轴对齐，长度不符则写 null |
| 中文绘图字体缺失 | 自动选择 Microsoft YaHei 等可用字体 |

## 8. 已知局限

- 没有真实硬件，所有电学数据来自仿真或公开数据集。
- ngspice 版本锁定为 34（PySpice 1.5 官方安装脚本提供），未验证其他版本。
- Windows 专用：未验证 Linux/macOS。
