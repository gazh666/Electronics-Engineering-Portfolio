"""3S 单体电压节点模型与三通道差分采集（Task 6/30）。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import u_F, u_Ohm, u_V

from circuits.differential_amplifier import DifferentialAmplifierConfig
from circuits.opamp_models import OpAmpSpec, add_opamp
from circuits.spice_utils import run_operating_point
from sensing.voltage_decoder import four_resistor_output


class CellSensingError(ValueError):
    """单体电压采集参数非法。"""


DEFAULT_REFERENCE_CELLS = (3.6, 3.8, 4.0)


def node_voltages(cell_voltages: Sequence[float]) -> dict[str, float]:
    if len(cell_voltages) != 3:
        raise CellSensingError("本阶段教学 3S 需要三个单体电压")
    values = [float(value) for value in cell_voltages]
    if not all(math.isfinite(value) and value > 0.0 for value in values):
        raise CellSensingError("单体电压必须为有限正数")
    n1 = values[0]
    n2 = n1 + values[1]
    n3 = n2 + values[2]
    return {"n0": 0.0, "n1": n1, "n2": n2, "n3": n3}


def build_3s_stack(cell_voltages: Sequence[float]) -> Circuit:
    nodes = node_voltages(cell_voltages)
    circuit = Circuit("BatteryLab 3S source stack")
    circuit.V("cell1", "n1", circuit.gnd, nodes["n1"])
    circuit.V("cell2", "n2", "n1", nodes["n2"] - nodes["n1"])
    circuit.V("cell3", "n3", "n2", nodes["n3"] - nodes["n2"])
    return circuit


def solve_3s_stack(cell_voltages: Sequence[float]) -> dict[str, float]:
    nodes = node_voltages(cell_voltages)
    circuit = build_3s_stack(cell_voltages)
    solution = run_operating_point(circuit, ["n1", "n2", "n3"])
    differential = {
        "cell1_v": solution["n1"] - 0.0,
        "cell2_v": solution["n2"] - solution["n1"],
        "cell3_v": solution["n3"] - solution["n2"],
    }
    reconstructed = differential["cell1_v"] + differential["cell2_v"] + differential["cell3_v"]
    return {
        "n0_v": 0.0,
        "n1_v": solution["n1"],
        "n2_v": solution["n2"],
        "n3_v": solution["n3"],
        "theory_n1_v": nodes["n1"],
        "theory_n2_v": nodes["n2"],
        "theory_n3_v": nodes["n3"],
        **differential,
        "pack_voltage_v": solution["n3"],
        "reconstructed_pack_v": reconstructed,
        "kvl_error_v": reconstructed - solution["n3"],
        # 错误接地示例：直接把 n2 对地电压当作第二节电芯电压
        "wrong_cell2_measurement_v": solution["n2"],
        "wrong_cell2_error_v": solution["n2"] - differential["cell2_v"],
    }


def build_3s_sensing_circuit(
    cell_voltages: Sequence[float],
    config: DifferentialAmplifierConfig,
    *,
    input_filter_resistance_ohm: float = 47.0,
    differential_capacitance_f: float = 2.2e-7,
    opamp: OpAmpSpec | None = None,
) -> Circuit:
    nodes = node_voltages(cell_voltages)
    circuit = Circuit("BatteryLab 3S differential sensing")
    circuit.V("cell1", "n1", circuit.gnd, nodes["n1"])
    circuit.V("cell2", "n2", "n1", nodes["n2"] - nodes["n1"])
    circuit.V("cell3", "n3", "n2", nodes["n3"] - nodes["n2"])
    circuit.V("vref", "vref", circuit.gnd, config.reference_v)
    for index in range(1, 4):
        high = f"n{index}"
        low = "n0" if index == 1 else f"n{index - 1}"
        low_source = circuit.gnd if index == 1 else low
        fh = f"fh{index}"
        fl = f"fl{index}"
        circuit.R(f"filt_h{index}", high, fh, input_filter_resistance_ohm)
        circuit.R(f"filt_l{index}", low_source, fl, input_filter_resistance_ohm)
        circuit.C(f"fdiff{index}", fh, fl, differential_capacitance_f)
        circuit.R(f"r1_{index}", fl, f"inm{index}", config.r1_ohm)
        circuit.R(f"r2_{index}", f"out{index}", f"inm{index}", config.r2_ohm)
        circuit.R(f"r3_{index}", fh, f"inp{index}", config.r3_ohm)
        circuit.R(f"r4_{index}", f"inp{index}", "vref", config.r4_ohm)
        template = opamp or OpAmpSpec(
            name="op",
            model_kind="ideal",
            open_loop_gain=1_000_000.0,
            output_low_v=0.0,
            output_high_v=config.supply_v,
        )
        spec = OpAmpSpec(
            name=f"op{index}",
            model_kind=template.model_kind,
            open_loop_gain=template.open_loop_gain,
            output_low_v=template.output_low_v,
            output_high_v=template.output_high_v,
            input_offset_v=template.input_offset_v,
            input_bias_current_a=template.input_bias_current_a,
            gain_bandwidth_hz=template.gain_bandwidth_hz,
        )
        add_opamp(
            circuit,
            spec,
            output_node=f"out{index}",
            non_inverting_node=f"inp{index}",
            inverting_node=f"inm{index}",
        )
    return circuit


def solve_3s_sensing(
    cell_voltages: Sequence[float],
    config: DifferentialAmplifierConfig,
    *,
    input_filter_resistance_ohm: float = 47.0,
    differential_capacitance_f: float = 2.2e-7,
    opamp: OpAmpSpec | None = None,
) -> list[dict[str, float]]:
    circuit = build_3s_sensing_circuit(
        cell_voltages,
        config,
        input_filter_resistance_ohm=input_filter_resistance_ohm,
        differential_capacitance_f=differential_capacitance_f,
        opamp=opamp,
    )
    nodes = ["out1", "out2", "out3", "inp1", "inp2", "inp3", "inm1", "inm2", "inm3"]
    solution = run_operating_point(circuit, nodes)
    rows = []
    for index, cell_voltage in enumerate(cell_voltages, start=1):
        vlow = float(sum(cell_voltages[: index - 1]))
        vhigh = vlow + float(cell_voltage)
        theory_with_filter = four_resistor_output(
            vhigh,
            vlow,
            r1_ohm=config.r1_ohm + input_filter_resistance_ohm,
            r2_ohm=config.r2_ohm,
            r3_ohm=config.r3_ohm + input_filter_resistance_ohm,
            r4_ohm=config.r4_ohm,
            reference_v=config.reference_v,
        )
        theory_no_filter = config.output(vhigh, vlow)
        output = solution[f"out{index}"]
        rows.append(
            {
                "channel": f"cell{index}",
                "cell_voltage_v": float(cell_voltage),
                "vhigh_v": vhigh,
                "vlow_v": vlow,
                "vout_v": float(output),
                "theory_v": float(theory_with_filter),
                "theory_no_filter_v": float(theory_no_filter),
                "filter_loading_error_v": float(theory_with_filter - theory_no_filter),
                "error_v": float(output - theory_with_filter),
                "vinp_v": solution[f"inp{index}"],
                "vinm_v": solution[f"inm{index}"],
                "pin_common_mode_v": 0.5 * (solution[f"inp{index}"] + solution[f"inm{index}"]),
            }
        )
    return rows


def wrong_ground_mapping(cell_voltages: Sequence[float]) -> list[dict[str, float]]:
    """错误方案：把每个节点对地电压直接当作单体电压。"""
    nodes = node_voltages(cell_voltages)
    rows = []
    for index, cell_voltage in enumerate(cell_voltages, start=1):
        measured = nodes[f"n{index}"]
        rows.append(
            {
                "channel": f"cell{index}",
                "cell_voltage_v": float(cell_voltage),
                "node_to_ground_v": measured,
                "error_v": measured - float(cell_voltage),
            }
        )
    return rows
