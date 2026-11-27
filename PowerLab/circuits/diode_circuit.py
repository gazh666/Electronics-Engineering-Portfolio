"""二极管直流伏安特性电路（教学用 SPICE 模型）。

拓扑::

    Vbias ── anode ── D1 ── gnd

模型参数 IS / N / RS 为通用教学参数，不对应任何经过验证的商业器件。
外部端电压与内部结电压在 RS ≠ 0 时不相等。
"""

from __future__ import annotations

from PySpice.Spice.Netlist import Circuit

from .models import DiodeParameters

DIODE_MODEL_NAME = "DTEST"


def add_diode_model(
    circuit: Circuit,
    parameters: DiodeParameters,
    *,
    model_name: str = DIODE_MODEL_NAME,
) -> None:
    """向电路注册教学二极管模型。"""
    if not isinstance(parameters, DiodeParameters):
        raise ValueError("parameters must be DiodeParameters")
    circuit.model(
        model_name,
        "D",
        IS=parameters.saturation_current_a,
        N=parameters.ideality_factor,
        RS=parameters.series_resistance_ohm,
    )


def build_diode_iv_circuit(
    parameters: DiodeParameters | None = None,
    *,
    name: str = "Diode IV Curve",
) -> Circuit:
    """构建二极管直流扫描电路（偏置源初值 0 V，由扫描命令改写）。"""
    parameters = parameters or DiodeParameters()
    if not isinstance(parameters, DiodeParameters):
        raise ValueError("parameters must be DiodeParameters")

    circuit = Circuit(name)
    circuit.V("bias", "anode", circuit.gnd, 0.0)
    add_diode_model(circuit, parameters)
    circuit.D(1, "anode", circuit.gnd, model=DIODE_MODEL_NAME)
    return circuit
