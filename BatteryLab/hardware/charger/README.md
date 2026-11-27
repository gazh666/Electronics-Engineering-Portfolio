# hardware/charger 说明

本目录是第六阶段充电器的**硬件参考研究**，不是已完成的设计文件。

- `bq24610_specifications.csv`：TI BQ24610 的标称规格，全部标记 `datasheet_specification`。
- `charger_pin_mapping.csv`：按功能信号整理，引脚号仍需按数据手册复核。
- `charger_preliminary_bom.csv`：初步选型，全部为 `preliminary` 或 `datasheet_specification`。
- `design_comparison.md`：与本阶段 SPICE 教学模型的差异与不可外推结论。

约束：

1. 本目录任何数值都不是实测值，不得写入"已验证"结论；
2. 不得用本目录参数替代 `configs/` 中的仿真参数；
3. 进入 PCB 设计前必须完成数据手册复核、热设计与保护器件选型评审。
