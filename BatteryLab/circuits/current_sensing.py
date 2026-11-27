"""双向电流检测教学电路（Task 13/15/16）。

低边分流电阻 + 规格参考电流放大器行为模型（INA240A2）。
放电电流为正，充电电流为负；零点参考 1.65 V。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np
from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import u_A, u_F, u_Hz, u_Ohm, u_V

from circuits.opamp_models import CurrentAmplifierSpec, add_spec_reference_current_amplifier
from circuits.spice_utils import run_operating_point, run_transient
from sensing.current_decoder import amplifier_output, shunt_power, shunt_voltage


class CurrentSensingError(ValueError):
    """电流检测参数非法。"""


@dataclass(frozen=True)
class CurrentSenseConfig:
    shunt_ohm: float
    amplifier_gain: float
    reference_v: float
    amplifier_output_low_v: float = 0.1
    amplifier_output_high_v: float = 4.9
    adc_reference_v: float = 3.3

    def __post_init__(self) -> None:
        for label, value in (
            ("分流电阻", self.shunt_ohm),
            ("放大倍数", self.amplifier_gain),
            ("零点参考", self.reference_v),
        ):
            if not math.isfinite(value) or value <= 0.0:
                raise CurrentSensingError(f"{label} 必须为正")
        if self.amplifier_output_low_v >= self.amplifier_output_high_v:
            raise CurrentSensingError("放大器输出范围非法")

    @classmethod
    def from_config(cls, config: dict) -> "CurrentSenseConfig":
        return cls(
            shunt_ohm=float(config["shunt"]["nominal_resistance_ohm"]),
            amplifier_gain=float(config["amplifier"]["gain_v_per_v"]),
            reference_v=float(config["amplifier"]["reference_voltage_v"]),
            amplifier_output_low_v=float(config["amplifier"]["output_low_v"]),
            amplifier_output_high_v=float(config["amplifier"]["output_high_v"]),
            adc_reference_v=float(config["measurement"]["adc_reference_voltage_v"]),
        )

    def output(self, current_a: float) -> float:
        return amplifier_output(
            current_a,
            gain=self.amplifier_gain,
            shunt_ohm=self.shunt_ohm,
            reference_v=self.reference_v,
        )


def build_current_sense_circuit(
    current_a: float,
    config: CurrentSenseConfig,
    *,
    amplifier_spec: CurrentAmplifierSpec | None = None,
    with_output_filter: bool = False,
    filter_resistance_ohm: float = 1000.0,
    filter_capacitance_f: float = 1.0e-7,
) -> Circuit:
    circuit = Circuit("BatteryLab bidirectional current sensing")
    circuit.R("shunt", "srp", circuit.gnd, config.shunt_ohm)
    # 注入正电流：从地经电流源流入 srp，使 SRP 相对 SRN 为正。
    circuit.I("load", circuit.gnd, "srp", float(current_a))
    spec = amplifier_spec or CurrentAmplifierSpec(
        name="ina240",
        gain=config.amplifier_gain,
        reference_voltage_v=config.reference_v,
        output_low_v=config.amplifier_output_low_v,
        output_high_v=config.amplifier_output_high_v,
    )
    output_node = "out"
    add_spec_reference_current_amplifier(
        circuit,
        spec,
        output_node=output_node,
        srp_node="srp",
        srn_node=circuit.gnd,
    )
    if with_output_filter:
        circuit.R("rf", "out", "out_f", filter_resistance_ohm)
        circuit.C("cf", "out_f", circuit.gnd, filter_capacitance_f)
    return circuit


def solve_current(
    current_a: float,
    config: CurrentSenseConfig,
    *,
    amplifier_spec: CurrentAmplifierSpec | None = None,
    with_output_filter: bool = False,
) -> dict[str, float]:
    circuit = build_current_sense_circuit(
        current_a,
        config,
        amplifier_spec=amplifier_spec,
        with_output_filter=with_output_filter,
    )
    output_node = "out_f" if with_output_filter else "out"
    solution = run_operating_point(circuit, ["srp", "out", output_node])
    vout = solution[output_node]
    theory = config.output(current_a)
    return {
        "current_a": float(current_a),
        "shunt_voltage_v": float(solution["srp"]),
        "shunt_power_w": float(shunt_power(current_a, config.shunt_ohm)),
        "vout_v": float(vout),
        "theory_v": float(theory),
        "error_v": float(vout - theory),
        "amplifier_saturated": bool(vout <= config.amplifier_output_low_v or vout >= config.amplifier_output_high_v),
        "adc_saturated": bool(vout <= 0.0 or vout >= config.adc_reference_v),
    }


def sweep_current(
    currents_a: Sequence[float],
    config: CurrentSenseConfig,
    *,
    amplifier_spec: CurrentAmplifierSpec | None = None,
) -> list[dict[str, float]]:
    return [solve_current(value, config, amplifier_spec=amplifier_spec) for value in currents_a]


def build_current_sense_sweep_circuit(
    config: CurrentSenseConfig,
    *,
    amplifier_spec: CurrentAmplifierSpec | None = None,
) -> Circuit:
    circuit = Circuit("BatteryLab bidirectional current sensing sweep")
    circuit.R("shunt", "srp", circuit.gnd, config.shunt_ohm)
    circuit.I("load", circuit.gnd, "srp", 0.0)
    spec = amplifier_spec or CurrentAmplifierSpec(
        name="ina240",
        gain=config.amplifier_gain,
        reference_voltage_v=config.reference_v,
        output_low_v=config.amplifier_output_low_v,
        output_high_v=config.amplifier_output_high_v,
    )
    add_spec_reference_current_amplifier(circuit, spec, output_node="out", srp_node="srp", srn_node=circuit.gnd)
    return circuit


def sweep_current_fast(
    currents_a: Sequence[float],
    config: CurrentSenseConfig,
    *,
    amplifier_spec: CurrentAmplifierSpec | None = None,
) -> list[dict[str, float]]:
    """一次真实 DC 扫描完成双向电流扫描（含饱和区）。"""
    from circuits.spice_utils import run_dc_sweep

    requested = np.asarray([float(value) for value in currents_a], dtype=float)
    start, stop = float(requested.min()), float(requested.max())
    step = (stop - start) / (requested.size - 1) if requested.size > 1 else 0.01
    circuit = build_current_sense_sweep_circuit(config, amplifier_spec=amplifier_spec)
    data = run_dc_sweep(circuit, source_name="Iload", start=start, stop=stop, step=step, nodes=["srp", "out"])
    vsense = np.interp(requested, data["sweep"], data["srp"])
    vout = np.interp(requested, data["sweep"], data["out"])
    rows = []
    for index, current in enumerate(requested):
        theory = config.output(float(current))
        rows.append(
            {
                "current_a": float(current),
                "shunt_voltage_v": float(vsense[index]),
                "shunt_power_w": float(shunt_power(float(current), config.shunt_ohm)),
                "vout_v": float(vout[index]),
                "theory_v": float(theory),
                "error_v": float(vout[index] - theory),
                "amplifier_saturated": bool(vout[index] <= config.amplifier_output_low_v or vout[index] >= config.amplifier_output_high_v),
                "adc_saturated": bool(vout[index] <= 0.0 or vout[index] >= config.adc_reference_v),
            }
        )
    return rows


def _build_output_filter_ac(resistance_ohm: float, capacitance_f: float) -> Circuit:
    circuit = Circuit("BatteryLab current output filter AC")
    circuit.SinusoidalVoltageSource("src", "inp", circuit.gnd, amplitude=0.0 @ u_V, ac_magnitude=1.0 @ u_V)
    circuit.R("rf", "inp", "out", resistance_ohm)
    circuit.C("cf", "out", circuit.gnd, capacitance_f)
    return circuit


def run_output_filter_ac(
    resistance_ohm: float = 1000.0,
    capacitance_f: float = 1.0e-7,
    *,
    start_hz: float = 10.0,
    stop_hz: float = 1.0e6,
    points_per_decade: int = 50,
) -> dict[str, np.ndarray]:
    from circuits.spice_utils import run_ac_sweep

    circuit = _build_output_filter_ac(resistance_ohm, capacitance_f)
    data = run_ac_sweep(
        circuit,
        start_hz=start_hz,
        stop_hz=stop_hz,
        points_per_decade=points_per_decade,
        nodes=["out"],
    )
    transfer = data["out"]
    return {
        "frequency_hz": data["frequency_hz"],
        "transfer": transfer,
        "gain_db": 20.0 * np.log10(np.abs(transfer)),
        "theoretical_cutoff_hz": 1.0 / (2.0 * math.pi * resistance_ohm * capacitance_f),
    }


def run_output_filter_step(
    resistance_ohm: float = 1000.0,
    capacitance_f: float = 1.0e-7,
    *,
    step_v: float = 1.0,
    t_step_s: float = 1.0e-4,
    rise_s: float = 1.0e-7,
    step_s: float = 1.0e-7,
) -> dict[str, object]:
    tau = resistance_ohm * capacitance_f
    duration = t_step_s + 14.0 * tau
    circuit = Circuit("BatteryLab current output filter step")
    values = [(0.0, 0.0), (t_step_s, 0.0), (t_step_s + rise_s, float(step_v)), (duration, float(step_v))]
    circuit.PieceWiseLinearVoltageSource("src", "inp", circuit.gnd, values=values)
    circuit.R("rf", "inp", "out", resistance_ohm)
    circuit.C("cf", "out", circuit.gnd, capacitance_f)
    data = run_transient(
        circuit,
        duration_s=duration,
        step_s=step_s,
        max_step_s=step_s,
        nodes=["out", "inp"],
    )
    time_s = data["time_s"]
    output = data["out"]
    final = float(np.mean(output[time_s >= time_s[-1] - 0.05 * (time_s[-1] - time_s[0])]))

    def crossing(fraction: float) -> float:
        target = fraction * final
        for index in range(1, len(time_s)):
            if (output[index - 1] - target) * (output[index] - target) <= 0.0 and output[index] != output[index - 1]:
                ratio = (target - output[index - 1]) / (output[index] - output[index - 1])
                return float(time_s[index - 1] + ratio * (time_s[index] - time_s[index - 1]))
        return float("nan")

    t10, t90, t63 = crossing(0.1), crossing(0.9), crossing(0.632)
    return {
        "time_s": time_s,
        "output_v": output,
        "final_v": final,
        "tau_s": tau,
        "rise_time_10_90_s": float(t90 - t10),
        "time_63p2_s": float(t63 - t_step_s),
        "theoretical_rise_time_s": 2.197 * tau,
        "theoretical_settling_time_s": 4.605 * tau,
        "steady_state_error_v": float(final - step_v),
    }


def shunt_selection_table(
    currents_a: Sequence[float],
    shunt_values_ohm: Sequence[float],
    *,
    fixed_gain: float,
    reference_v: float,
    adc_reference_v: float,
    fair_gain_by_shunt: dict[float, float] | None = None,
) -> list[dict[str, float | bool]]:
    """比较不同分流电阻的压降、功耗、ADC 量程占用与量化分辨率。"""
    rows: list[dict[str, float | bool]] = []
    max_current = max(abs(float(value)) for value in currents_a)
    for shunt in shunt_values_ohm:
        shunt_value = float(shunt)
        vmax = max_current * shunt_value
        pmax = max_current * max_current * shunt_value
        for label, gain in (
            ("fixed_gain_50", float(fixed_gain)),
            ("fair_range", float((fair_gain_by_shunt or {}).get(shunt_value, fixed_gain))),
        ):
            output_high = reference_v + gain * vmax
            output_low = reference_v - gain * vmax
            saturation = output_high >= adc_reference_v or output_low <= 0.0
            lsb = adc_reference_v / 4096.0
            resolution_a = lsb / (gain * shunt_value)
            offset_error_a = 25e-6 / shunt_value
            tolerance_error_a = 0.005 * max_current
            temp_error_a = 50e-6 * 25.0 * max_current
            rows.append(
                {
                    "shunt_ohm": shunt_value,
                    "gain": gain,
                    "max_drop_v": float(vmax),
                    "max_power_w": float(pmax),
                    "output_low_v": float(output_low),
                    "output_high_v": float(output_high),
                    "adc_range_usage_fraction": float((output_high - output_low) / adc_reference_v),
                    "saturates": bool(saturation),
                    "current_lsb_a": float(resolution_a),
                    "offset_referred_error_a": float(offset_error_a),
                    "resistance_tolerance_error_a": float(tolerance_error_a),
                    "temperature_error_a": float(temp_error_a),
                    "mode": label,
                }
            )
    return rows
