"""统一波形字段名与仿真层次标记。

充电器输出电流、电感电流与真实电池电流不得混用，因此字段名必须显式区分。
"""

from __future__ import annotations

# Task 4 规定的统一波形字段（顺序即 CSV 列顺序的一部分）。
WAVEFORM_FIELDS = (
    "time_s",
    "inductor_current_a",
    "charging_current_a",
    "ecm_current_a",
    "charger_output_voltage_v",
    "battery_pack_voltage_v",
    "input_voltage_v",
    "input_current_a",
    "duty",
    "current_reference_a",
    "voltage_reference_v",
)

# 仿真层次：不同层次结果不得混为开关级验证。
METHODS = (
    "analytical_theory",
    "averaged_simulation",
    "spice_simulation",
    "behavioral_charging_simulation",
    "ecm_charge_envelope",
    "software_test",
    "datasheet_specification",
)

# 充电会话状态。
CHARGE_STATES = (
    "IDLE",
    "SOFT_START",
    "CC",
    "CV",
    "COMPLETE",
    "FAULT",
    "TIMEOUT",
)


def validate_method(method: str) -> str:
    if method not in METHODS:
        raise ValueError(f"未知仿真层次: {method!r}")
    return method
