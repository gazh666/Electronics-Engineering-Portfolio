# 01 环境说明

## 1. 目标

本文记录 TestLab 在 Windows 本机上的真实开发环境、依赖版本与验证命令，
便于复现实验。当前所有仪器均为 PyVISA-sim 虚拟仪器，不连接真实硬件。

## 2. 操作系统与工作区

- 操作系统：Windows
- 工作区：`<repo-root>`
- 上游源码目录（只读参考，不修改）：
  - `pyvisa-main/`
  - `pyvisa-sim-main/`
  - `PyBaMM-main/`
  - `PySpice-master/`
- 自主应用目录：`TestLab`
- TestLab 是独立 Git 仓库，避免污染上游仓库。

## 3. Python 环境

使用独立 Conda 环境 `kaifa`，不修改其他 Python 环境。

```text
环境路径：C:\\Users\\<user>\.conda\envs\kaifa
Python：3.11.18
pip：26.2.2
```

验证命令：

```powershell
conda run -n kaifa python --version
conda run -n kaifa python -c "import sys; print(sys.executable)"
conda run -n kaifa python -m pip check
conda run -n kaifa python -c "import pyvisa; print(pyvisa.__version__)"
```

实际结果：

```text
Python 3.11.18
C:\\Users\\<user>\.conda\envs\kaifa\python.exe
No broken requirements found.
1.16.2
```

## 4. 关键依赖

| 包 | 版本 | 用途 |
| --- | --- | --- |
| PyVISA | 1.16.2 | VISA 资源管理与 SCPI 通信 |
| PyVISA-sim | 0.7.1 | 基于 YAML 的虚拟仪器后端 |
| PyYAML | 6.0.4 | 读取仪器定义与测试用例 |
| numpy | 2.4.6 | 数值计算（报告/分析依赖） |
| pandas | 3.1.1 | 结果表格处理 |
| plotly | 7.1.0 | 后续可视化图表 |
| streamlit | 1.67.0 | 后续可视化平台 |
| pytest | 9.2.0 | 单元与端到端测试 |

安装入口：`TestLab/requirements.txt`。

## 5. 运行方式

所有 Python 命令在 `TestLab` 目录下执行：

```powershell
conda run -n kaifa python -m pytest tests -v
conda run -n kaifa python -m scripts.power_supply_demo
conda run -n kaifa python -m scripts.demo
```

后续 Streamlit 平台启动方式（阶段九实现后）：

```powershell
conda run --no-capture-output -n kaifa python -m streamlit run app.py
```

浏览器访问 `http://localhost:8501`。

## 6. 注意事项

1. PowerShell 中若 `conda` 不在 PATH，可使用完整路径
   `D:\miniconda3\Library\bin\conda.bat`。
2. PyVISA-sim 的虚拟仪器之间**不会自动共享物理状态**，业务层必须显式桥接。
3. 仪器回读值是**设定参数**，不是真实电气测量值；报告中必须使用
   `pyvisa-sim SCPI` 等来源标签区分。
4. 不要为了调试而修改上游 `pyvisa` / `pyvisa_sim` 源码。
