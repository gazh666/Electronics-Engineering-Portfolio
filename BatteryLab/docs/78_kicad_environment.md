# 78 KiCad 环境取证与安装边界

日期：2026-11-26
结论：本机**没有 KiCad**。`kicad-cli` 不在 PATH，`C:\Program Files\KiCad` 不存在。
winget 源中可以看到 `KiCad.KiCad 10.0.8`，但安装需要管理员/UAC，本阶段未安装、未提权。

## 1. 为什么先写"环境取证"

KiCad 不是 Python 包，而是一套带 GUI、符号库、封装库、3D 模型和 CLI 的桌面软件。
在没有它的情况下，任何 `.kicad_sch`、`.kicad_pcb`、ERC、DRC、Gerber 都只能伪造。
因此本阶段把"有没有 KiCad"当成一条**硬证据**记录，而不是一句口头说明。

取证原则：

- 只记录本机真实命令输出；
- 找不到就写 `KICAD_NOT_FOUND`，不写"大概已安装"；
- 不修改系统 PATH，不请求管理员权限，不擅自安装；
- 安装步骤写给用户手动执行，不由代理代做。

## 2. 本机取证结果

| 检查 | 命令/方法 | 真实结果 |
| --- | --- | --- |
| CLI 是否在 PATH | `Get-Command kicad-cli` | 无输出，未找到 |
| 默认安装目录 | `Test-Path 'C:\Program Files\KiCad'` | `False` |
| 项目脚本探测 | `python -m scripts.verify_kicad` | `KICAD_NOT_FOUND` |
| 版本记录文件 | `results/.../kicad_version.txt` | `KICAD_NOT_FOUND` |
| 元数据 | `results/.../metadata.json` | `"kicad_cli": null`，`"kicad_error": "KiCad CLI not found"` |
| winget 源 | `winget search --id KiCad.KiCad --accept-source-agreements` | `KiCad  KiCad.KiCad  10.0.8  winget` |

winget 的实际输出（2026-11-26 查询）：

```text
名称           ID               版本   源
----------------------------------------------
KiCad          KiCad.KiCad      10.0.8 winget
KiCad Lite EDA KiCad.KiCad.Lite 5.1.9  winget
```

`KiCad.KiCad.Lite 5.1.9` 是另一条包记录，版本很旧，不适合作为本项目的 EDA 环境。
本阶段只把它当作"源里有什么"的证据，不据此安装。

## 3. 项目内的定位逻辑

`eda_tools/kicad_runner.py` 的 `find_kicad_cli()` 按固定顺序查找：

| 顺序 | 依据 | 行为 |
| --- | --- | --- |
| 1 | 显式传入的 `--cli` 路径 | 文件存在则返回绝对路径，否则抛 `FileNotFoundError` |
| 2 | `shutil.which("kicad-cli")` | 在 PATH 中查找 |
| 3 | `C:\Program Files\KiCad\*\bin\kicad-cli.exe` | 只接受唯一匹配；多个版本要求显式指定 |

这段逻辑故意不"猜"路径，也不扫描整个磁盘。原因是：

- 多个 KiCad 版本共存时，自动选择任意一个会让报告不可追溯；
- 显式路径能让 `kicad_env.json` 记录到底用了哪个可执行文件；
- 找不到时直接报错，比静默回退到某个旧版本更安全。

`scripts/verify_kicad.py` 在找不到 CLI 时，会写出 `kicad_env.json`，包含
`status=KICAD_NOT_FOUND`、错误原因、安装步骤和一句关键说明：
"原理图与 PCB 相关任务保留 BLOCKED，不生成虚假完成证据"。

## 4. 为什么不能从 PyPI 安装同名 `pcbnew`

`pcbnew` 是 KiCad 自带的 Python 绑定，依赖 KiCad 的本地动态库、封装库路径和
`PYTHONPATH` 配置。它不是独立可用的 PyPI 包。

| 做法 | 结果 | 结论 |
| --- | --- | --- |
| `pip install pcbnew` | 没有官方维护的同名包；即使装到同名模块也无法加载 KiCad 库 | 禁止 |
| 从源码单独编译 `pcbnew` | 需要完整 KiCad 构建链，远超本项目范围 | 不采用 |
| 使用 KiCad 自带 Python | 与 GUI/CLI 同版本，绑定完整 | 推荐 |

因此项目文档中的规则是：**需要 `pcbnew` 时，使用 KiCad 自带 Python，
不从 PyPI 安装同名包。** 这条规则写在 `verify_kicad.py` 的安装步骤里，
也写进了 FMEA 的"PCB 连接错误"防范措施中。

## 5. 安装步骤（用户手动执行）

以下是写给具备管理员权限的用户的操作，不是本阶段已执行的动作。

```powershell
# 方式一：官方安装程序
# 打开 https://www.kicad.org/download/windows/ 下载安装包

# 方式二：winget
winget install --id KiCad.KiCad --accept-package-agreements --accept-source-agreements
```

安装时注意事项：

1. 勾选符号库、封装库、3D 模型库（默认包含）；
2. 记住安装根目录，通常是 `C:\Program Files\KiCad\<版本>`；
3. 安装过程会触发 UAC，需要管理员确认；
4. 安装完成后重新打开终端，让 PATH 生效；
5. 不要修改系统级 PATH 来"迁就"某个脚本，优先使用 `--cli` 显式路径。

安装后的验证命令：

```powershell
& "C:\Program Files\KiCad\<版本>\bin\kicad-cli.exe" version
conda run -n kaifa_battery python -m scripts.verify_kicad --cli "C:\Program Files\KiCad\<版本>\bin\kicad-cli.exe"
```

## 6. 安装后的探测设计

`scripts/verify_kicad.py` 预置了 11 组 `--help` 探测，目的不是"跑一遍好看"，
而是确认本机版本到底支持哪些子命令与参数：

| 组 | 子命令 | 用途 |
| --- | --- | --- |
| 1 | `version` | 记录精确版本 |
| 2 | `sch erc` | 原理图电气规则检查 |
| 3 | `sch export netlist` | 导出网表，供引脚/网络审计 |
| 4 | `sch export bom` | 导出 BOM |
| 5 | `sch export pdf` | 生成原理图 PDF |
| 6 | `pcb drc` | PCB 设计规则检查 |
| 7 | `pcb export gerbers` | 制造文件 |
| 8 | `pcb export drill` | 钻孔文件 |
| 9 | `pcb export pos` | 贴片坐标 |
| 10 | `pcb export step` | 3D STEP |
| 11 | `pcb export svg` | 版图预览 |

探测结果会写入 `help_*.json`，每条包含命令、返回码、标准输出前 1500 字符。
这样做的原因是：不同 KiCad 大版本的 CLI 参数会变，不能凭记忆写死命令。

## 7. 版本差异与兼容性注意

| 风险 | 说明 | 应对 |
| --- | --- | --- |
| 文件格式版本 | `.kicad_sch`/`.kicad_pcb` 带版本号，高版本文件低版本打不开 | 固定团队使用的 KiCad 大版本，并记录在 manifest |
| CLI 子命令差异 | 8/9/10 的 `export` 参数、报告格式可能不同 | 安装后先跑 `--help` 探测，不照抄旧命令 |
| 报告 JSON 结构 | ERC/DRC 报告字段可能变化 | `report_parser.py` 只做保守解析，未知字段不猜 |
| 符号/封装库版本 | 库更新会改变引脚名或焊盘 | 工程绑定项目库，不直接依赖全局库最新版 |
| Python 绑定 | 只有 GUI 自带 Python 能 import `pcbnew` | 用 KiCad Python 跑布局/指标脚本 |

本阶段没有安装 KiCad，因此以上差异属于**待验证的设计注意**，不是已观察到的现象。

## 8. 当前 BLOCKED 状态

`blocked_items.json` 记录了 8 项产物缺失：

| 产物 | 路径 | 状态 |
| --- | --- | --- |
| 原理图 | `hardware/eda/BatteryLab_BMS_V1/BatteryLab_BMS_V1.kicad_sch` | `BLOCKED_NO_KICAD_GUI` |
| PCB | `hardware/eda/BatteryLab_BMS_V1/BatteryLab_BMS_V1.kicad_pcb` | `BLOCKED_NO_KICAD_GUI` |
| ERC | `results/.../erc_raw.json` | `NOT_PRODUCED` |
| DRC | `results/.../drc_raw.json` | `NOT_PRODUCED` |
| 原理图 PDF | `results/.../schematic.pdf` | `NOT_PRODUCED` |
| Gerber | `results/.../gerbers` | `NOT_PRODUCED` |
| 钻孔 | `results/.../drill` | `NOT_PRODUCED` |
| STEP | `results/.../board.step` | `NOT_PRODUCED` |

加上 `kicad_available` 检查本身，阶段验收中共有 9 项 BLOCKED。
这不是"部分完成"，而是"环境不满足，产物为 0"。

## 9. 用户手动步骤清单

如果希望解除 BLOCKED，需要用户在本机完成：

1. 用管理员权限安装 KiCad 10.0.8 或团队指定版本；
2. 确认 `kicad-cli.exe version` 能输出真实版本字符串；
3. 运行 `python -m scripts.verify_kicad --cli <路径>`，保存 `kicad_env.json`；
4. 在 KiCad GUI 中创建 `BatteryLab_BMS_V1` 工程，按 80 号文档逐脚连线；
5. 完成 ERC，导出网表、BOM、PDF；
6. 创建 PCB，按 79 号文档的关键网络规则布线，完成 DRC；
7. 导出 Gerber、钻孔、贴片坐标、STEP；
8. 把上述产物放入新的 Run ID 目录，再重新运行阶段验收脚本。

在上述 8 步完成之前，任何"原理图已完成"的表述都不成立。

## 10 自测题

1. 为什么 `winget` 能搜到 KiCad，仍然不能证明本机可用？
   答案要点：winget 搜的是软件源，不是本机安装状态；还要检查 PATH、安装目录和
   `kicad-cli version` 的真实输出。
2. 为什么项目不自动扫描全盘找 `kicad-cli.exe`？
   答案要点：多个版本共存会导致报告不可追溯；显式路径或唯一安装目录更可审计。
3. `pip install pcbnew` 为什么不可行？
   答案要点：`pcbnew` 依赖 KiCad 本地库与库路径，不是独立 PyPI 包；必须用 KiCad
   自带 Python。
4. 安装 KiCad 后，为什么要先跑 11 组 `--help` 探测？
   答案要点：不同大版本 CLI 参数和报告格式会变，必须先确认本机支持哪些子命令，
   不能凭记忆写死命令。
5. BLOCKED 与 FAIL 的区别是什么？
   答案要点：FAIL 是检查执行了但未达标；BLOCKED 是检查因环境/权限未执行。

## 11 延伸阅读

- KiCad 官方 Windows 下载页：<https://www.kicad.org/download/windows/>
- KiCad 官方文档（CLI 与工程格式）：<https://docs.kicad.org/>
- KiCad 官方开发者文档（pcbnew Python 绑定）：<https://dev-docs.kicad.org/>
- TI BQ76922 数据手册 SLUSE86A：<https://www.ti.com/lit/ds/symlink/bq76922.pdf>
