# 本地符号/封装库状态

本目录包含 `BatteryLab.kicad_sym`（KiCad 10 格式），为**原创绘制**的符号库：

- `BQ76922`：32 引脚 + PAD，引脚编号与 TI 数据手册一致；
- `BQ24610`：24 引脚 + PAD，引脚编号与 TI 数据手册一致；
- Son 5×6 MOSFET 符号：源极 1/2/3、栅极 4、漏极 5–8 + 散热焊盘。

引脚依据：

- `../requirements/bms_pin_mapping.csv`：BQ76922 32 引脚 + PAD，含页码；
- `../requirements/charger_pin_mapping.csv`：BQ24610 24 引脚 + PAD；
- `../../component_selection/footprint_verification.csv`：封装核查状态。

## 许可

- 本目录的符号图形为原创绘制，按本仓库 **MIT** 授权。
- 符号中引用的封装名（如 `Package_DFN_QFN:Texas_RGE0024H_VQFN-24-1EP_4x4mm_P0.5mm_EP2.7x2.7mm`）
  属于 KiCad 官方封装库，实际封装图形内嵌在 `.kicad_pcb` 中，按 **CC-BY-SA 4.0** 保留署名。
- 详见根目录 `THIRD_PARTY_NOTICES.md`。
