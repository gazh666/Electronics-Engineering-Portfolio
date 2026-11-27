"""第八阶段 EDA 辅助工具包。

Engineering Prototype Design — Not Hardware Validated.

本包只提供可复算的设计计算、KiCad CLI 调用、网表/BOM/报告解析与审计工具。
任何函数返回值都是**计算结果**，不是硬件实测值。
"""

__all__ = [
    "design_calculations",
    "thermal_calculations",
    "feedback_design",
    "inductor_design",
    "copper_calculations",
    "kicad_runner",
    "netlist_parser",
    "pin_mapping_audit",
    "bom_validator",
    "board_metrics",
    "report_parser",
    "release_manifest",
    "board_placement",
]
