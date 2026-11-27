"""第六阶段充电功率级器件模型：教学开关、续流二极管与寄生。

所有参数来自 ``configs/charger_config.yaml``；模型只用于真实 ngspice 求解，
不在 Python 侧生成任何"电路输出"。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from PySpice.Spice.Netlist import Circuit

from charging.config import PowerStageConfig

SWITCH_MODEL_NAME = "SW_CHARGER"
DIODE_MODEL_NAME = "D_CHARGER"


@dataclass(frozen=True)
class ChargerDeviceModels:
    switch_on_resistance_ohm: float
    switch_off_resistance_ohm: float = 1.0e8
    switch_threshold_voltage_v: float = 2.5
    switch_hysteresis_voltage_v: float = 0.1
    diode_saturation_current_a: float = 1.0e-6
    diode_emission_coefficient: float = 1.0
    diode_series_resistance_ohm: float = 0.02
    switch_gate_high_v: float = 5.0

    def __post_init__(self) -> None:
        for name in (
            "switch_on_resistance_ohm",
            "switch_off_resistance_ohm",
            "switch_threshold_voltage_v",
            "diode_saturation_current_a",
            "diode_emission_coefficient",
            "diode_series_resistance_ohm",
            "switch_gate_high_v",
        ):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} 必须为正")
        if self.switch_hysteresis_voltage_v < 0.0:
            raise ValueError("迟滞不能为负")

    @classmethod
    def from_power_stage(cls, power_stage: PowerStageConfig) -> "ChargerDeviceModels":
        return cls(switch_on_resistance_ohm=power_stage.mosfet_rds_on_target_ohm)

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


def add_device_models(
    circuit: Circuit,
    models: ChargerDeviceModels,
    *,
    suffix: str = "",
) -> tuple[str, str]:
    """向网表注入 SW 与二极管模型，返回实际使用的模型名。"""
    switch_name = f"{SWITCH_MODEL_NAME}{suffix}"
    diode_name = f"{DIODE_MODEL_NAME}{suffix}"
    circuit.raw_spice += (
        f".model {switch_name} SW(RON={models.switch_on_resistance_ohm:g} "
        f"ROFF={models.switch_off_resistance_ohm:g} "
        f"VT={models.switch_threshold_voltage_v:g} "
        f"VH={models.switch_hysteresis_voltage_v:g})\n"
        f".model {diode_name} D(IS={models.diode_saturation_current_a:g} "
        f"N={models.diode_emission_coefficient:g} "
        f"RS={models.diode_series_resistance_ohm:g})\n"
    )
    return switch_name, diode_name
