# BatteryLab_BMS_V1 状态

**BLOCKED_NO_KICAD_GUI**：本机未安装 KiCad，本目录没有 `.kicad_pro` /
`.kicad_sch` / `.kicad_pcb`。请不要把本目录当作已完成工程。

已完成的输入（可直接用于绘制原理图）：

- `../requirements/bms_design.yaml`：设计目标与 AFE 配置
- `../requirements/bms_pin_mapping.csv`：33 行（32 引脚 + PAD），逐行标注数据手册页码
- `../requirements/critical_net_rules.csv`：关键网络宽度/间距/层
- `../requirements/interface_definition.csv`：J1–J4、TP1–TP4
- `../../component_selection/`：器件与封装核查

安装 KiCad 后的操作：

1. 新建工程 `BatteryLab_BMS_V1.kicad_pro`；
2. 按引脚映射表放置符号并连线，封装按 `footprint_verification.csv` 核对；
3. 运行 `kicad-cli sch erc --format json ...`；
4. 布局布线后运行 `kicad-cli pcb drc --format json ...`；
5. 回到仓库根目录运行 `python -m scripts.audit_schematic` 与 `audit_pcb`。

详见 `docs/78_kicad_environment.md` 与 `docs/90_stage8_final_validation.md`。
