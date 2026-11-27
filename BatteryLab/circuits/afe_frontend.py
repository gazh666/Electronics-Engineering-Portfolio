"""完整 3S 模拟前端：三路单体差分采集 + 双向电流 + NTC。

接口说明：电池侧电压/电流波形由第三阶段辨识模型预先计算，再作为 PWL 激励
驱动 SPICE，这属于"单向波形驱动仿真"，不是完整实时双向联合仿真。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np
from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import u_Hz

from circuits.current_sensing import CurrentSenseConfig, build_current_sense_circuit
from circuits.differential_amplifier import DifferentialAmplifierConfig
from circuits.opamp_models import CurrentAmplifierSpec, OpAmpSpec, add_opamp, add_spec_reference_current_amplifier
from circuits.spice_utils import run_operating_point, run_transient
from sensing.temperature_decoder import ntc_resistance


class AFEError(ValueError):
    """AFE 参数非法。"""


DEFAULT_FILTER_R_OHM = 47.0
DEFAULT_FILTER_C_F = 2.2e-7


def _opamp_spec(template: OpAmpSpec | None, index: int, supply_v: float) -> OpAmpSpec:
    base = template or OpAmpSpec(
        name="op",
        model_kind="ideal",
        open_loop_gain=1_000_000.0,
        output_low_v=0.0,
        output_high_v=supply_v,
    )
    return OpAmpSpec(
        name=f"op{index}",
        model_kind=base.model_kind,
        open_loop_gain=base.open_loop_gain,
        output_low_v=base.output_low_v,
        output_high_v=base.output_high_v,
        input_offset_v=base.input_offset_v,
        input_bias_current_a=base.input_bias_current_a,
        gain_bandwidth_hz=base.gain_bandwidth_hz,
    )


def _add_cell_channel(
    circuit: Circuit,
    index: int,
    high_node: str,
    low_node: str,
    config: DifferentialAmplifierConfig,
    *,
    filter_r_ohm: float,
    filter_c_f: float,
    opamp_template: OpAmpSpec | None,
) -> None:
    fh = f"fh{index}"
    fl = f"fl{index}"
    circuit.R(f"filt_h{index}", high_node, fh, filter_r_ohm)
    circuit.R(f"filt_l{index}", low_node, fl, filter_r_ohm)
    circuit.C(f"fdiff{index}", fh, fl, filter_c_f)
    circuit.R(f"r1_{index}", fl, f"inm{index}", config.r1_ohm)
    circuit.R(f"r2_{index}", f"out{index}", f"inm{index}", config.r2_ohm)
    circuit.R(f"r3_{index}", fh, f"inp{index}", config.r3_ohm)
    circuit.R(f"r4_{index}", f"inp{index}", "vref", config.r4_ohm)
    add_opamp(
        circuit,
        _opamp_spec(opamp_template, index, config.supply_v),
        output_node=f"out{index}",
        non_inverting_node=f"inp{index}",
        inverting_node=f"inm{index}",
    )


def _add_current_channel(
    circuit: Circuit,
    current_a: float | None,
    current_config: CurrentSenseConfig,
    *,
    amplifier_spec: CurrentAmplifierSpec | None = None,
    current_pwl: Sequence[tuple[float, float]] | None = None,
) -> None:
    circuit.R("shunt", "srp", circuit.gnd, current_config.shunt_ohm)
    if current_pwl is None:
        circuit.I("load", circuit.gnd, "srp", float(current_a or 0.0))
    else:
        circuit.PieceWiseLinearCurrentSource("load", circuit.gnd, "srp", values=list(current_pwl))
    spec = amplifier_spec or CurrentAmplifierSpec(
        name="ina240",
        gain=current_config.amplifier_gain,
        reference_voltage_v=current_config.reference_v,
        output_low_v=current_config.amplifier_output_low_v,
        output_high_v=current_config.amplifier_output_high_v,
    )
    add_spec_reference_current_amplifier(
        circuit,
        spec,
        output_node="out_i",
        srp_node="srp",
        srn_node=circuit.gnd,
    )


def _add_ntc_channel(circuit: Circuit, temperature_c: float, ntc_config) -> None:
    resistance = ntc_resistance(
        temperature_c,
        r25_ohm=ntc_config.r25_ohm,
        beta_k=ntc_config.beta_k,
    )
    circuit.V("vcc", "vcc", circuit.gnd, ntc_config.excitation_v)
    circuit.R("pullup", "vcc", "temp", ntc_config.pullup_ohm)
    circuit.R("ntc", "temp", circuit.gnd, resistance)


def build_afe_static_circuit(
    cell_voltages: Sequence[float],
    current_a: float,
    temperature_c: float,
    amp_config: DifferentialAmplifierConfig,
    current_config: CurrentSenseConfig,
    ntc_config,
    *,
    opamp_template: OpAmpSpec | None = None,
    amplifier_spec: CurrentAmplifierSpec | None = None,
    filter_r_ohm: float = DEFAULT_FILTER_R_OHM,
    filter_c_f: float = DEFAULT_FILTER_C_F,
) -> Circuit:
    if len(cell_voltages) != 3:
        raise AFEError("需要三个单体电压")
    circuit = Circuit("BatteryLab 3S AFE static")
    v1, v2, v3 = (float(value) for value in cell_voltages)
    circuit.V("cell1", "n1", circuit.gnd, v1)
    circuit.V("cell2", "n2", "n1", v2)
    circuit.V("cell3", "n3", "n2", v3)
    circuit.V("vref", "vref", circuit.gnd, amp_config.reference_v)
    _add_cell_channel(circuit, 1, "n1", circuit.gnd, amp_config, filter_r_ohm=filter_r_ohm, filter_c_f=filter_c_f, opamp_template=opamp_template)
    _add_cell_channel(circuit, 2, "n2", "n1", amp_config, filter_r_ohm=filter_r_ohm, filter_c_f=filter_c_f, opamp_template=opamp_template)
    _add_cell_channel(circuit, 3, "n3", "n2", amp_config, filter_r_ohm=filter_r_ohm, filter_c_f=filter_c_f, opamp_template=opamp_template)
    _add_current_channel(circuit, current_a, current_config, amplifier_spec=amplifier_spec)
    _add_ntc_channel(circuit, temperature_c, ntc_config)
    return circuit


def solve_afe_static(
    cell_voltages: Sequence[float],
    current_a: float,
    temperature_c: float,
    amp_config: DifferentialAmplifierConfig,
    current_config: CurrentSenseConfig,
    ntc_config,
    **kwargs,
) -> dict[str, object]:
    circuit = build_afe_static_circuit(
        cell_voltages,
        current_a,
        temperature_c,
        amp_config,
        current_config,
        ntc_config,
        **kwargs,
    )
    nodes = [
        "n1",
        "n2",
        "n3",
        "out1",
        "out2",
        "out3",
        "out_i",
        "srp",
        "temp",
        "inp1",
        "inp2",
        "inp3",
    ]
    solution = run_operating_point(circuit, nodes)
    return {
        "cell_voltages_v": [float(value) for value in cell_voltages],
        "current_a": float(current_a),
        "temperature_c": float(temperature_c),
        "node_voltages_v": {key: solution[key] for key in ("n1", "n2", "n3")},
        "cell_outputs_v": [solution["out1"], solution["out2"], solution["out3"]],
        "cell_pin_common_mode_v": [solution["inp1"], solution["inp2"], solution["inp3"]],
        "current_output_v": solution["out_i"],
        "shunt_voltage_v": solution["srp"],
        "ntc_voltage_v": solution["temp"],
    }


def _pwl_from_frames(time_s: np.ndarray, values: np.ndarray) -> list[tuple[float, float]]:
    times = np.asarray(time_s, dtype=float)
    data = np.asarray(values, dtype=float)
    if times.size != data.size or times.size < 2:
        raise AFEError("PWL 时间与数值必须等长且至少两点")
    return [(float(t), float(v)) for t, v in zip(times, data)]


def build_afe_transient_circuit(
    cell_waveforms_v: Sequence[Sequence[float]],
    time_s: Sequence[float],
    current_waveform_a: Sequence[float],
    temperature_c: float,
    amp_config: DifferentialAmplifierConfig,
    current_config: CurrentSenseConfig,
    ntc_config,
    *,
    opamp_template: OpAmpSpec | None = None,
    amplifier_spec: CurrentAmplifierSpec | None = None,
    filter_r_ohm: float = DEFAULT_FILTER_R_OHM,
    filter_c_f: float = DEFAULT_FILTER_C_F,
    common_mode_interference_v: float = 0.0,
    differential_interference_v: float = 0.0,
    interference_hz: float = 100_000.0,
) -> Circuit:
    if len(cell_waveforms_v) != 3:
        raise AFEError("需要三条单体电压波形")
    time_array = np.asarray(time_s, dtype=float)
    circuit = Circuit("BatteryLab 3S AFE transient")
    if common_mode_interference_v:
        circuit.SinusoidalVoltageSource(
            "cm", "n0", circuit.gnd, amplitude=common_mode_interference_v, frequency=interference_hz @ u_Hz
        )
    else:
        circuit.V("cm", "n0", circuit.gnd, 0.0)
    circuit.PieceWiseLinearVoltageSource("cell1", "n1", "n0", values=_pwl_from_frames(time_array, cell_waveforms_v[0]))
    circuit.PieceWiseLinearVoltageSource("cell2", "n2", "n1", values=_pwl_from_frames(time_array, cell_waveforms_v[1]))
    circuit.PieceWiseLinearVoltageSource("cell3", "n3", "n2", values=_pwl_from_frames(time_array, cell_waveforms_v[2]))
    circuit.V("vref", "vref", circuit.gnd, amp_config.reference_v)
    _add_cell_channel(circuit, 1, "n1", "n0", amp_config, filter_r_ohm=filter_r_ohm, filter_c_f=filter_c_f, opamp_template=opamp_template)
    if differential_interference_v:
        circuit.SinusoidalVoltageSource(
            "vint2", "n2", "n2i", amplitude=differential_interference_v, frequency=interference_hz @ u_Hz
        )
        _add_cell_channel(circuit, 2, "n2i", "n1", amp_config, filter_r_ohm=filter_r_ohm, filter_c_f=filter_c_f, opamp_template=opamp_template)
    else:
        _add_cell_channel(circuit, 2, "n2", "n1", amp_config, filter_r_ohm=filter_r_ohm, filter_c_f=filter_c_f, opamp_template=opamp_template)
    _add_cell_channel(circuit, 3, "n3", "n2", amp_config, filter_r_ohm=filter_r_ohm, filter_c_f=filter_c_f, opamp_template=opamp_template)
    _add_current_channel(
        circuit,
        None,
        current_config,
        amplifier_spec=amplifier_spec,
        current_pwl=_pwl_from_frames(time_array, current_waveform_a),
    )
    _add_ntc_channel(circuit, temperature_c, ntc_config)
    return circuit


def run_afe_transient(
    cell_waveforms_v: Sequence[Sequence[float]],
    time_s: Sequence[float],
    current_waveform_a: Sequence[float],
    temperature_c: float,
    amp_config: DifferentialAmplifierConfig,
    current_config: CurrentSenseConfig,
    ntc_config,
    *,
    step_s: float = 1.0e-3,
    max_step_s: float | None = None,
    **kwargs,
) -> dict[str, np.ndarray]:
    time_array = np.asarray(time_s, dtype=float)
    circuit = build_afe_transient_circuit(
        cell_waveforms_v,
        time_array,
        current_waveform_a,
        temperature_c,
        amp_config,
        current_config,
        ntc_config,
        **kwargs,
    )
    nodes = ["n1", "n2", "n3", "out1", "out2", "out3", "out_i", "srp", "temp"]
    return run_transient(
        circuit,
        duration_s=float(time_array[-1]),
        step_s=step_s,
        max_step_s=max_step_s or step_s,
        nodes=nodes,
    )
