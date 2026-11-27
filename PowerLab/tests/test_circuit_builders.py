"""电路构建器与参数模型测试（不运行仿真）。"""

from __future__ import annotations

import pytest

from circuits.diode_circuit import DIODE_MODEL_NAME, add_diode_model, build_diode_iv_circuit
from circuits.models import (
    DiodeParameters,
    RCParameters,
    RectifierParameters,
    RLCParameters,
    RLParameters,
    VoltageDividerParameters,
    damping_cases,
)
from circuits.rc_circuit import build_rc_lowpass, build_rc_transient
from circuits.rectifier import build_half_wave_rectifier
from circuits.rlc_circuit import build_rlc_ac, build_rlc_transient
from circuits.rl_circuit import build_rl_transient
from circuits.voltage_divider import build_voltage_divider, divider_transfer_slope


def test_voltage_divider_netlist_and_slope():
    circuit = build_voltage_divider(12.0, 1_000.0, 1_000.0)
    netlist = str(circuit)
    assert "R1" in netlist and "R2" in netlist and "Vinput" in netlist
    assert divider_transfer_slope(1_000.0, 1_000.0) == pytest.approx(0.5)


def test_voltage_divider_rejects_invalid_resistors():
    with pytest.raises(ValueError):
        build_voltage_divider(12.0, 0.0, 1_000.0)
    with pytest.raises(ValueError):
        build_voltage_divider(12.0, 1_000.0, float("nan"))


def test_rc_transient_netlist_and_pulse_constraint():
    circuit = build_rc_transient(5.0, 1_000.0, 1e-6)
    assert circuit.title == "RC Transient"
    netlist = str(circuit)
    assert "Vinput" in netlist and "R1" in netlist and "C1" in netlist
    assert "PULSE" in netlist.upper()
    with pytest.raises(ValueError):
        build_rc_transient(5.0, 1_000.0, 1e-6, pulse_width_s=1e-3, period_s=1e-3)


def test_rc_lowpass_netlist_contains_ac_excitation():
    circuit = build_rc_lowpass(1_000.0, 1e-6)
    netlist = str(circuit)
    assert "SIN" in netlist.upper()
    assert "AC" in netlist.upper()
    with pytest.raises(ValueError):
        build_rc_lowpass(1_000.0, 1e-6, ac_magnitude_v=0.0)


def test_rl_transient_netlist():
    circuit = build_rl_transient(5.0, 10.0, 0.01)
    netlist = str(circuit)
    assert "R1" in netlist and "L1" in netlist and "Vinput" in netlist
    with pytest.raises(ValueError):
        build_rl_transient(5.0, 10.0, 0.0)


def test_rlc_transient_and_ac_netlists():
    transient = build_rlc_transient(10.0, 0.01, 1e-6)
    ac = build_rlc_ac(10.0, 0.01, 1e-6)
    assert "L1" in str(transient) and "C1" in str(transient)
    assert "AC" in str(ac).upper()
    with pytest.raises(ValueError):
        build_rlc_transient(10.0, 0.01, -1e-6)


def test_diode_model_registration_and_circuit():
    parameters = DiodeParameters()
    circuit = build_diode_iv_circuit(parameters)
    netlist = str(circuit)
    assert DIODE_MODEL_NAME in netlist
    assert ".model" in netlist.lower()
    assert "D1" in netlist
    with pytest.raises(ValueError):
        add_diode_model(circuit, "not-parameters")


def test_half_wave_rectifier_netlist():
    circuit = build_half_wave_rectifier(RectifierParameters())
    netlist = str(circuit)
    assert "SIN" in netlist.upper()
    assert "D1" in netlist and "Rload" in netlist
    with pytest.raises(ValueError):
        build_half_wave_rectifier(RectifierParameters(load_resistance_ohm=0.0))


def test_parameter_models_to_dict_and_validation():
    divider = VoltageDividerParameters()
    assert divider.to_dict()["vin_v"] == 12.0
    with pytest.raises(ValueError):
        VoltageDividerParameters(r1_ohm=0.0)
    with pytest.raises(ValueError):
        RCParameters(capacitance_f=float("inf"))
    with pytest.raises(ValueError):
        RLParameters(inductance_h=-0.01)
    with pytest.raises(ValueError):
        RLCParameters(capacitance_f=0.0)
    with pytest.raises(ValueError):
        DiodeParameters(temperature_c=-300.0)


def test_damping_case_labels():
    cases = damping_cases((10.0, 200.0, 400.0))
    assert [case.label for case in cases] == ["underdamped", "critical", "overdamped"]
    assert cases[0].to_dict()["resistance_ohm"] == 10.0
