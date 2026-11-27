"""二极管半波整流电路。

拓扑::

    正弦源 vin ── Rs ── anode ── D1 ── out ── Rload ── gnd

本阶段只实现基础半波整流，不涉及滤波电容或开关电源拓扑。
"""

from __future__ import annotations

from PySpice.Spice.Netlist import Circuit

from .diode_circuit import DIODE_MODEL_NAME, add_diode_model
from .models import DiodeParameters, RectifierParameters
from .validators import positive_number


def build_half_wave_rectifier(
    parameters: RectifierParameters | None = None,
    *,
    name: str = "Half Wave Rectifier",
) -> Circuit:
    """构建半波整流电路（50 Hz、10 V 峰值默认参数）。"""
    parameters = parameters or RectifierParameters()
    if not isinstance(parameters, RectifierParameters):
        raise ValueError("parameters must be RectifierParameters")

    peak_v = positive_number(parameters.input_peak_v, "rectifier.input_peak_v")
    frequency_hz = positive_number(parameters.frequency_hz, "rectifier.frequency_hz")
    source_r = positive_number(parameters.source_resistance_ohm, "rectifier.source_resistance_ohm")
    load_r = positive_number(parameters.load_resistance_ohm, "rectifier.load_resistance_ohm")

    circuit = Circuit(name)
    circuit.SinusoidalVoltageSource(
        "input",
        "vin",
        circuit.gnd,
        amplitude=peak_v,
        frequency=frequency_hz,
    )
    circuit.R("source", "vin", "anode", source_r)
    add_diode_model(circuit, parameters.diode, model_name=DIODE_MODEL_NAME)
    circuit.D(1, "anode", "out", model=DIODE_MODEL_NAME)
    circuit.R("load", "out", circuit.gnd, load_r)
    return circuit


def default_parameters() -> RectifierParameters:
    """返回默认整流参数（含默认二极管模型）。"""
    return RectifierParameters(diode=DiodeParameters())
