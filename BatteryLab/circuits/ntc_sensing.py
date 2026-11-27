"""NTC 分压采集真实 SPICE 验证（Task 21/22/23）。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np
from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import u_Ohm, u_V

from circuits.spice_utils import run_operating_point
from sensing.temperature_decoder import (
    divider_voltage,
    ntc_power_w,
    ntc_resistance,
    ntc_temperature,
    resistance_from_voltage,
)


class NtcSensingError(ValueError):
    """NTC 采集参数非法。"""


@dataclass(frozen=True)
class NtcConfig:
    r25_ohm: float = 10000.0
    beta_k: float = 3950.0
    pullup_ohm: float = 10000.0
    excitation_v: float = 3.3
    adc_reference_v: float = 3.3
    minimum_temperature_c: float = 0.0
    maximum_temperature_c: float = 60.0

    def __post_init__(self) -> None:
        for label, value in (
            ("R25", self.r25_ohm),
            ("B 值", self.beta_k),
            ("上拉电阻", self.pullup_ohm),
            ("激励电压", self.excitation_v),
            ("ADC 参考", self.adc_reference_v),
        ):
            if not math.isfinite(value) or value <= 0.0:
                raise NtcSensingError(f"{label} 必须为正")
        if self.minimum_temperature_c >= self.maximum_temperature_c:
            raise NtcSensingError("温度范围非法")

    @classmethod
    def from_config(cls, config: dict) -> "NtcConfig":
        ntc = config["ntc"]
        divider = config["divider"]
        temperature_range = config["temperature_range"]
        return cls(
            r25_ohm=float(ntc["nominal_resistance_ohm"]),
            beta_k=float(ntc["beta_k"]),
            pullup_ohm=float(divider["pullup_resistance_ohm"]),
            excitation_v=float(divider["excitation_voltage_v"]),
            adc_reference_v=float(divider["adc_reference_voltage_v"]),
            minimum_temperature_c=float(temperature_range["minimum_c"]),
            maximum_temperature_c=float(temperature_range["maximum_c"]),
        )

    def resistance(self, temperature_c: float) -> float:
        return ntc_resistance(temperature_c, r25_ohm=self.r25_ohm, beta_k=self.beta_k)

    def voltage(self, temperature_c: float) -> float:
        return divider_voltage(
            self.resistance(temperature_c),
            pullup_ohm=self.pullup_ohm,
            excitation_v=self.excitation_v,
        )


def build_ntc_divider(resistance_ohm: float, config: NtcConfig) -> Circuit:
    circuit = Circuit("BatteryLab NTC divider")
    circuit.V("vcc", "vcc", circuit.gnd, config.excitation_v)
    circuit.R("pullup", "vcc", "temp", config.pullup_ohm)
    circuit.R("ntc", "temp", circuit.gnd, float(resistance_ohm))
    return circuit


def solve_ntc_voltage(resistance_ohm: float, config: NtcConfig) -> float:
    circuit = build_ntc_divider(resistance_ohm, config)
    solution = run_operating_point(circuit, ["temp", "vcc"])
    return float(solution["temp"])


def sweep_temperatures(temperatures_c: Sequence[float], config: NtcConfig) -> list[dict[str, float]]:
    rows = []
    for temperature in temperatures_c:
        resistance = config.resistance(temperature)
        spice_voltage = solve_ntc_voltage(resistance, config)
        theory_voltage = config.voltage(temperature)
        recovered_resistance = resistance_from_voltage(
            spice_voltage,
            pullup_ohm=config.pullup_ohm,
            excitation_v=config.excitation_v,
        )
        recovered_temperature = ntc_temperature(
            recovered_resistance,
            r25_ohm=config.r25_ohm,
            beta_k=config.beta_k,
        )
        rows.append(
            {
                "temperature_c": float(temperature),
                "resistance_ohm": float(resistance),
                "spice_voltage_v": float(spice_voltage),
                "theory_voltage_v": float(theory_voltage),
                "voltage_error_v": float(spice_voltage - theory_voltage),
                "recovered_temperature_c": float(recovered_temperature),
                "temperature_error_c": float(recovered_temperature - temperature),
                "ntc_power_w": float(
                    ntc_power_w(
                        temperature,
                        r25_ohm=config.r25_ohm,
                        beta_k=config.beta_k,
                        pullup_ohm=config.pullup_ohm,
                        excitation_v=config.excitation_v,
                    )
                ),
            }
        )
    return rows


def run_open_short(config: NtcConfig) -> dict[str, dict[str, float | str]]:
    open_resistance = 1.0e12
    short_resistance = 1.0e-3
    open_voltage = solve_ntc_voltage(open_resistance, config)
    short_voltage = solve_ntc_voltage(short_resistance, config)
    return {
        "open": {
            "resistance_ohm": open_resistance,
            "voltage_v": open_voltage,
            "voltage_fraction_of_excitation": open_voltage / config.excitation_v,
            "expected_status": "SENSOR_OPEN",
        },
        "short": {
            "resistance_ohm": short_resistance,
            "voltage_v": short_voltage,
            "voltage_fraction_of_excitation": short_voltage / config.excitation_v,
            "expected_status": "SENSOR_SHORT",
        },
    }


def build_ntc_behavioral_sweep_circuit(
    *,
    r25_ohm: float,
    beta_k: float,
    pullup_ohm: float,
    excitation_v: float,
) -> Circuit:
    """用行为电流源模拟 R(T)，使温度可用真实 SPICE 直流扫描遍历。

    节点 tctl 的 1 mV 代表 1 ℃（表达式内乘 1000）。
    """
    circuit = Circuit("BatteryLab NTC behavioral temperature sweep")
    circuit.V("tctl", "tctl", circuit.gnd, 0.0)
    circuit.V("vcc", "vcc", circuit.gnd, float(excitation_v))
    circuit.R("pullup", "vcc", "temp", float(pullup_ohm))
    expression = (
        f"V(temp)/({float(r25_ohm)!r}*exp({float(beta_k)!r}*(1/(V(tctl)*1000+273.15)-1/298.15)))"
    )
    circuit.B("ntc", "temp", circuit.gnd, i=expression)
    return circuit


def sweep_temperatures_fast(temperatures_c: Sequence[float], config: NtcConfig) -> list[dict[str, float]]:
    """一次真实 DC 扫描遍历全部实验温度点。"""
    from circuits.spice_utils import run_dc_sweep

    requested = np.asarray([float(value) for value in temperatures_c], dtype=float)
    start = float(requested.min()) / 1000.0
    stop = float(requested.max()) / 1000.0
    # 使用 200 点以上的细网格，避免对非线性阻温曲线做粗线性插值引入假误差。
    step = (stop - start) / 240.0 if requested.size > 1 else 1e-4
    circuit = build_ntc_behavioral_sweep_circuit(
        r25_ohm=config.r25_ohm,
        beta_k=config.beta_k,
        pullup_ohm=config.pullup_ohm,
        excitation_v=config.excitation_v,
    )
    data = run_dc_sweep(circuit, source_name="Vtctl", start=start, stop=stop, step=step, nodes=["temp", "vcc"])
    spice_voltages = np.interp(requested / 1000.0, data["sweep"], data["temp"])
    rows = []
    for index, temperature in enumerate(requested):
        resistance = config.resistance(float(temperature))
        theory_voltage = config.voltage(float(temperature))
        recovered_resistance = resistance_from_voltage(
            float(spice_voltages[index]),
            pullup_ohm=config.pullup_ohm,
            excitation_v=config.excitation_v,
        )
        recovered_temperature = ntc_temperature(
            recovered_resistance,
            r25_ohm=config.r25_ohm,
            beta_k=config.beta_k,
        )
        rows.append(
            {
                "temperature_c": float(temperature),
                "resistance_ohm": float(resistance),
                "spice_voltage_v": float(spice_voltages[index]),
                "theory_voltage_v": float(theory_voltage),
                "voltage_error_v": float(spice_voltages[index] - theory_voltage),
                "recovered_temperature_c": float(recovered_temperature),
                "temperature_error_c": float(recovered_temperature - temperature),
                "ntc_power_w": float(
                    ntc_power_w(
                        float(temperature),
                        r25_ohm=config.r25_ohm,
                        beta_k=config.beta_k,
                        pullup_ohm=config.pullup_ohm,
                        excitation_v=config.excitation_v,
                    )
                ),
            }
        )
    return rows
