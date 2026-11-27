# 许可证状态（LICENSE STATUS）

**当前状态：已选定。本人原创及 AI 辅助开发的代码、文档与原创工程文件采用 MIT 许可证（见根目录 `LICENSE`）。**
**第三方代码、数据、SPICE 模型、符号/封装库与工具保留各自原始许可证（见根目录 `THIRD_PARTY_NOTICES.md`）。**

## 各项目现状

| 项目 | 许可证 | 说明 |
|---|---|---|
| TestLab | MIT | 原创代码与文档 |
| PowerLab | MIT | 原创代码与文档 |
| BatteryLab | MIT | 原创代码、文档、原创符号；EDA 封装含 CC-BY-SA 4.0 部分（见 §3 of THIRD_PARTY_NOTICES） |

## 边界

- MIT 仅覆盖仓库所有者有权授权的部分。
- PySpice（GPL-3.0）、KiCad（GPL-3.0）、FreeRouting（AGPL-3.0）等**程序本体不分发**。
- KiCad 官方封装图形随 `.kicad_pcb` 内嵌，按 CC-BY-SA 4.0 保留署名。
- CALCE 公开数据不随仓库分发，仅保留派生结果。

## 注意

- 不得将本仓库全部资产统一视为 MIT 授权；
- 若将本项目与 PySpice 等 GPL 组件组合再分发，需自行评估许可证兼容性。
