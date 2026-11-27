"""Buck 电路构建与网表连接关系测试。"""

from __future__ import annotations

import re
from dataclasses import replace

import pytest

from circuits.buck import (
    build_buck_circuit,
    build_buck_from_parameters,
)
from circuits.buck_config import load_buck_config


def _circuit():
    return build_buck_from_parameters(load_buck_config())


def _line(netlist: str, prefix: str) -> str:
    match = re.search(rf"^{prefix}\b.*$", netlist, flags=re.MULTILINE)
    assert match is not None, f"element {prefix} not found in netlist"
    return match.group(0)


def test_netlist_contains_required_elements():
    netlist = str(_circuit())
    for element in ("VIN", "VPWM", "S1", "DFREE", "VSENSE", "L1", "C1", "RLOAD"):
        _line(netlist, element)
    assert "SWMOD" in netlist


def test_input_source_connects_vin_to_ground():
    line = _line(str(_circuit()), "VIN")
    assert re.match(r"^VIN\s+vin\s+0\s+12", line)


def test_pwm_source_drives_gate():
    line = _line(str(_circuit()), "VPWM")
    assert re.match(r"^VPWM\s+gate\s+0\s+DC\s+0V\s+PULSE\(", line)


def test_switch_connects_vin_sw_gate():
    line = _line(str(_circuit()), "S1")
    assert re.match(r"^S1\s+vin\s+sw\s+gate\s+0\s+SWMOD", line)


def test_freewheeling_diode_points_from_ground_to_switch_node():
    line = _line(str(_circuit()), "DFREE")
    # 阳极 GND、阴极 sw：开关关断时提供续流通路。
    assert re.match(r"^DFREE\s+0\s+sw\s+DFREE", line)


def test_current_sense_source_is_series_between_sw_and_inductor():
    line = _line(str(_circuit()), "VSENSE")
    assert re.match(r"^VSENSE\s+sw\s+lx\s+0", line)


def test_inductor_capacitor_and_load_connections():
    netlist = str(_circuit())
    assert re.match(r"^L1\s+lx\s+out\b", _line(netlist, "L1"))
    assert re.match(r"^C1\s+out\s+0\b", _line(netlist, "C1"))
    assert re.match(r"^RLOAD\s+out\s+0\b", _line(netlist, "RLOAD"))


def test_parameter_changes_are_reflected_in_netlist():
    parameters = load_buck_config()
    modified = replace(
        parameters,
        circuit=replace(
            parameters.circuit,
            input_voltage_v=24.0,
            inductance_h=100e-6,
            capacitance_f=47e-6,
            load_resistance_ohm=10.0,
        ),
    )
    netlist = str(build_buck_from_parameters(modified))
    assert re.match(r"^VIN\s+vin\s+0\s+24", _line(netlist, "VIN"))
    assert float(_line(netlist, "L1").split()[-1]) == pytest.approx(100e-6)
    assert float(_line(netlist, "C1").split()[-1]) == pytest.approx(47e-6)
    assert re.match(r"^RLOAD\s+out\s+0\s+10\b", _line(netlist, "RLOAD"))


def test_pwm_parameters_are_reflected_in_netlist():
    parameters = load_buck_config()
    modified = replace(parameters, pwm=replace(parameters.pwm, duty_cycle=0.5))
    line = _line(str(build_buck_from_parameters(modified)), "VPWM")
    assert "PULSE(" in line


def test_build_buck_circuit_rejects_wrong_types():
    parameters = load_buck_config()
    with pytest.raises(ValueError):
        build_buck_circuit("bad", parameters.pwm, parameters.switch, parameters.diode)
    with pytest.raises(ValueError):
        build_buck_circuit(parameters.circuit, "bad", parameters.switch, parameters.diode)
    with pytest.raises(ValueError):
        build_buck_circuit(
            parameters.circuit, parameters.pwm, parameters.switch, parameters.diode, title="  "
        )
    with pytest.raises(ValueError):
        build_buck_from_parameters("bad")


def test_circuit_title_defaults_to_config_name():
    parameters = load_buck_config()
    netlist = str(build_buck_from_parameters(parameters))
    assert netlist.splitlines()[0].strip() == f".title {parameters.circuit_name}"
