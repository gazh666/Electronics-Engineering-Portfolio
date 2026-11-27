"""电压控制开关与续流二极管的 SPICE 模型参数。

本阶段使用 ngspice 内置 ``SW`` 模型与简化 ``D`` 模型：

- ``SW``: 电压控制开关，``RON`` / ``ROFF`` / ``VT`` / ``VH``。
- ``D``: 二极管，``IS`` / ``N`` / ``RS``。

这些是教学用近理想模型，带有非零导通电阻与非零正向压降，
不等同于经过验证的商业 MOSFET / 肖特基二极管模型。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySpice.Spice.Netlist import Circuit

from .validators import finite_number, nonnegative_number, positive_number

#: 默认开关模型名。
SWITCH_MODEL_NAME = "SWMOD"

#: 默认续流二极管模型名。
DEFAULT_DIODE_MODEL_NAME = "DFREE"


@dataclass(frozen=True)
class SwitchConfig:
    """电压控制开关 ``SW`` 模型参数。"""

    on_resistance_ohm: float = 0.001
    off_resistance_ohm: float = 1e6
    threshold_voltage_v: float = 2.5
    hysteresis_voltage_v: float = 0.1

    def __post_init__(self) -> None:
        ron = positive_number(self.on_resistance_ohm, "switch.on_resistance_ohm")
        roff = positive_number(self.off_resistance_ohm, "switch.off_resistance_ohm")
        threshold = finite_number(self.threshold_voltage_v, "switch.threshold_voltage_v")
        hysteresis = positive_number(self.hysteresis_voltage_v, "switch.hysteresis_voltage_v")

        if ron >= roff:
            raise ValueError(
                f"switch.on_resistance_ohm must be smaller than off resistance, got {ron!r} >= {roff!r}"
            )
        if hysteresis >= 2.0 * abs(threshold):
            raise ValueError(
                "switch.hysteresis_voltage_v is too large relative to threshold: "
                f"{hysteresis!r} V"
            )

    @property
    def turn_on_voltage_v(self) -> float:
        """可靠导通所需的最低栅极电压（含迟滞上边界）。"""
        return self.threshold_voltage_v + 0.5 * self.hysteresis_voltage_v

    @property
    def turn_off_voltage_v(self) -> float:
        """可靠关断允许的最高栅极电压（含迟滞下边界）。"""
        return self.threshold_voltage_v - 0.5 * self.hysteresis_voltage_v

    def validate_gate_levels(self, low_voltage_v: float, high_voltage_v: float) -> None:
        """校验 PWM 低电平可关断、高电平可导通。"""
        low = finite_number(low_voltage_v, "pwm.low_voltage_v")
        high = finite_number(high_voltage_v, "pwm.high_voltage_v")
        if high < self.turn_on_voltage_v:
            raise ValueError(
                "pwm.high_voltage_v is below the switch turn-on level: "
                f"{high!r} V < {self.turn_on_voltage_v!r} V"
            )
        if low > self.turn_off_voltage_v:
            raise ValueError(
                "pwm.low_voltage_v is above the switch turn-off level: "
                f"{low!r} V > {self.turn_off_voltage_v!r} V"
            )

    def to_dict(self) -> dict[str, float]:
        return {
            "on_resistance_ohm": self.on_resistance_ohm,
            "off_resistance_ohm": self.off_resistance_ohm,
            "threshold_voltage_v": self.threshold_voltage_v,
            "hysteresis_voltage_v": self.hysteresis_voltage_v,
            "turn_on_voltage_v": self.turn_on_voltage_v,
            "turn_off_voltage_v": self.turn_off_voltage_v,
        }


@dataclass(frozen=True)
class DiodeConfig:
    """续流二极管 ``D`` 模型参数（阳极接 GND，阴极接开关节点）。"""

    model_name: str = DEFAULT_DIODE_MODEL_NAME
    saturation_current_a: float = 1e-6
    ideality_factor: float = 1.0
    series_resistance_ohm: float = 0.001

    def __post_init__(self) -> None:
        if not isinstance(self.model_name, str) or not self.model_name.strip():
            raise ValueError("diode.model_name must be a non-empty string")
        positive_number(self.saturation_current_a, "diode.saturation_current_a")
        positive_number(self.ideality_factor, "diode.ideality_factor")
        nonnegative_number(self.series_resistance_ohm, "diode.series_resistance_ohm")

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "saturation_current_a": self.saturation_current_a,
            "ideality_factor": self.ideality_factor,
            "series_resistance_ohm": self.series_resistance_ohm,
        }


def add_switch_model(
    circuit: Circuit,
    config: SwitchConfig,
    *,
    name: str = SWITCH_MODEL_NAME,
) -> str:
    """把 ``SW`` 模型写入电路，返回模型名。"""
    if not isinstance(circuit, Circuit):
        raise ValueError("circuit must be a PySpice Circuit")
    if not isinstance(config, SwitchConfig):
        raise ValueError("config must be SwitchConfig")
    model_name = str(name).strip()
    if not model_name:
        raise ValueError("switch model name must be a non-empty string")
    circuit.model(
        model_name,
        "SW",
        RON=config.on_resistance_ohm,
        ROFF=config.off_resistance_ohm,
        VT=config.threshold_voltage_v,
        VH=config.hysteresis_voltage_v,
    )
    return model_name


def add_diode_model(circuit: Circuit, config: DiodeConfig) -> str:
    """把续流二极管模型写入电路，返回模型名。"""
    if not isinstance(circuit, Circuit):
        raise ValueError("circuit must be a PySpice Circuit")
    if not isinstance(config, DiodeConfig):
        raise ValueError("config must be DiodeConfig")
    circuit.model(
        config.model_name,
        "D",
        IS=config.saturation_current_a,
        N=config.ideality_factor,
        RS=config.series_resistance_ohm,
    )
    return config.model_name
