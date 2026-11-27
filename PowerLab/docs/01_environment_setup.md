# 01 环境搭建与复现记录

> 记录时间：2026-11-25。以下均为本机实际执行结果，不是示例值。

## 1. 系统与工具链

| 项目 | 实际值 | 获取方式 |
| --- | --- | --- |
| 操作系统 | Windows-10-10.0.26200-SP0 | `platform.platform()` |
| 架构 | 64bit WindowsPE / AMD64 | `platform.architecture()`、`platform.machine()` |
| Conda | 25.5.1 | `conda --version` |
| Git | 可用（用于源码参考，未提交本项目） | `git --version` |
| 默认 base Python | 3.9.23 | `python --version` |
| 本项目环境 | `kaifa_power` | `conda env list` |
| 环境路径 | `C:\\Users\\<user>\.conda\envs\kaifa_power` | `sys.executable` |

## 2. 创建独立环境

```powershell
conda create -n kaifa_power python=3.11 pip -y
conda run -n kaifa_power python --version
conda run -n kaifa_power python -c "import sys; print(sys.executable)"
conda run -n kaifa_power python -c "import platform; print(platform.architecture())"
```

实际输出：

```text
Python 3.11.18
C:\\Users\\<user>\.conda\envs\kaifa_power\python.exe
('64bit', 'WindowsPE')
```

原 TestLab 使用的 `kaifa` 环境未安装任何本项目依赖，也未修改 TestLab 文件。

## 3. Python 依赖

```powershell
conda run -n kaifa_power python -m pip install numpy==1.26.4 scipy matplotlib pandas pytest pyyaml cffi ply PySpice==1.5
conda run -n kaifa_power python -m pip check
```

实际安装版本：

| 包 | 版本 |
| --- | --- |
| PySpice | 1.5 |
| numpy | 1.26.4 |
| scipy | 1.17.1 |
| matplotlib | 3.11.2 |
| pandas | 3.0.6 |
| PyYAML | 6.0.4 |
| cffi | 2.1.1 |
| ply | 3.11 |
| requests | 2.34.2 |
| pytest | 9.2.0 |

`pip check` 输出：`No broken requirements found.`（退出码 0）。

### 安装问题记录

- 第一次安装命令中写了 `"numpy<2"`。PowerShell 把 `<` 当成重定向符，pip 实际没有收到
  该参数，命令以 “The system cannot find the file specified.” 失败。
- 解决方式：改用精确版本 `numpy==1.26.4`，不依赖 shell 的 `<` 语义。
- 固定 numpy 1.x 的原因：PySpice 1.5 发布早于 NumPy 2.0，先选择已验证兼容的组合；
  22 项测试全部通过，`pip check` 无冲突。

## 4. ngspice 后端

PySpice 只提供 Python 封装，真正的求解器是 ngspice。本机使用 PySpice 官方提供的
Windows 64 位共享库安装工具：

```powershell
conda run -n kaifa_power pyspice-post-installation --help
conda run -n kaifa_power pyspice-post-installation --install-ngspice-dll
```

实际安装位置：

```text
C:\\Users\\<user>\.conda\envs\kaifa_power\Lib\site-packages\PySpice\Spice\NgSpice\Spice64_dll\
├── dll-vs\ngspice-34.dll      7,358,976 bytes   ← 当前使用
├── dll-vs\ngspice.dll         7,358,976 bytes
├── dll-vs\vcomp140.dll          185,152 bytes
├── dll-mingw\libngspice-0.dll 9,319,818 bytes   ← 备选（未使用）
└── share\ngspice\scripts\spinit
```

- 版本依据：共享库文件名为 `ngspice-34.dll`，大小 7,358,976 字节。
- 采用方式：PySpice 1.5 的 `NgSpice.Shared` 接口，通过 CFFI `ffi.dlopen` 加载 DLL
  （见 `PySpice/Spice/NgSpice/Shared.py` L92、L539）。
- 未使用 ngspice 命令行子进程，也未使用 `libngspice-0.dll`。
- 没有修改系统 PATH，没有申请管理员权限；DLL 只存在于 conda 环境内部。

## 5. 环境验证

```powershell
conda run -n kaifa_power python -m scripts.verify_environment
```

实际结果（节选）：

```json
{
  "environment": {
    "python": "3.11.18",
    "architecture": "64bit WindowsPE",
    "machine": "AMD64",
    "packages": {"PySpice": "1.5", "numpy": "1.26.4", "scipy": "1.17.1",
                 "matplotlib": "3.11.2", "pandas": "3.0.6", "PyYAML": "6.0.4"}
  },
  "backend_probe": {
    "backend": "PySpice 1.5 + ngspice-34 shared DLL",
    "simulated_vin_v": 12.0,
    "simulated_vout_v": 6.0,
    "status": "OK"
  },
  "status": "OK"
}
```

退出码 0。验证脚本不仅 import，还真实求解了 12 V 分压电路。

## 6. 复现步骤

```powershell
conda create -n kaifa_power python=3.11 pip -y
conda run -n kaifa_power python -m pip install -r requirements.txt
conda run -n kaifa_power python -m pip install -r requirements-dev.txt
conda run -n kaifa_power pyspice-post-installation --install-ngspice-dll
conda run -n kaifa_power python -m scripts.verify_environment
conda run -n kaifa_power python -m scripts.voltage_divider_demo
conda run -n kaifa_power python -m scripts.rc_transient_demo
conda run -n kaifa_power python -m pytest tests -v
```

注意：`requirements.txt` 只能安装 Python 包，**不能**安装 ngspice 共享库；
必须单独执行 `pyspice-post-installation` 或按官方说明配置 DLL。

## 7. 未验证项

| 项目 | 状态 |
| --- | --- |
| Linux / macOS 运行 | NOT_VERIFIED |
| Docker 镜像 | NOT_VERIFIED |
| GitHub Actions | NOT_VERIFIED |
| ngspice 精确许可证版本 | NOT_VERIFIED（发行包未附独立 LICENSE 文件） |
| PySpice Git commit | NOT_VERIFIED（`PySpice-master` 无 `.git` 元数据，`__version__ = '1.5'`） |
