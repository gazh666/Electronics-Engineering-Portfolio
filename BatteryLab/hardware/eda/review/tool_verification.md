# BatteryLab EDA 工具链核查（Task 2）

核查日期：2026-11-27

## 1. 实际安装
| 项目 | 实际结果 |
|---|---|
| KiCad GUI / CLI | 10.0.8（用户级安装） |
| kicad-cli | `C:\\Users\\<user>\AppData\Local\Programs\KiCad\10.0\bin\kicad-cli.exe` |
| KiCad Python | 同目录 `python.exe`，`import pcbnew` → `pcbnew.GetBuildVersion()` = 10.0.8 |
| 符号 / 封装库 | `...\10.0\share\kicad\symbols`、`...\share\kicad\footprints`（随安装包提供） |
| Conda 环境 | `kaifa`、`kaifa_power`、`kaifa_battery`（不含 pcbnew，EDA 一律使用 KiCad 自带 Python） |

`C:\Program Files\KiCad` 不存在（按用户安装），`Get-Command kicad-cli.exe` 未在 PATH 中，
因此所有命令均使用绝对路径调用。

## 2. CLI 能力核查
```
kicad-cli sch erc          -> 支持 --format json --severity-all
kicad-cli sch export netlist -> 支持 kicadxml
kicad-cli pcb drc          -> 支持 --format json --severity-all --schematic-parity
kicad-cli pcb export       -> gerbers / drill / step / svg / pdf / pos / stats 等
kicad-cli pcb export dsn   -> 不存在（DSN 通过 pcbnew.ExportSpecctraDSN 导出）
```

## 3. 布线方式选择
| 方案 | 结论 |
|---|---|
| A. KiCad GUI 交互布线 | 本 Agent 无法稳定操作 GUI 完成整板布线，未采用 |
| B. pcbnew Python 生成线段/过孔 | **已采用**：主功率通路手工坐标布线（真实 PCB_TRACK） |
| C. Specctra DSN/SES + FreeRouting | **已采用**：`pcbnew.ExportSpecctraDSN` / `ImportSpecctraSES` 可编程调用；FreeRouting 1.9.0（AGPL-3.0）仅本地运行、不随作品集分发 |

## 4. 限制说明
- kicad-cli 不具备“自动布线”能力，未用任何 CLI 命令冒充自动布线；
- 未将工程上传到任何第三方在线布线服务；
- FreeRouting 为辅助布线，功率/模拟关键网络由人工规划（见 `routing_plan.md`）；
- 最终连接性与间距一律以 kicad-cli 真实 DRC 结果为准。
