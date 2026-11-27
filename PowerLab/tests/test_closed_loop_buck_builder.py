"""闭环/开环 Buck 构建器测试（网表结构，不运行仿真）。"""

from __future__ import annotations

import pytest

from circuits.closed_loop_buck import build_closed_loop_buck
from circuits.closed_loop_config import load_closed_loop_config


def _build(variant: str, mode: str = "closed_loop"):
    config = load_closed_loop_config().with_variant(variant)
    return build_closed_loop_buck(config, mode=mode)


def test_closed_loop_e_contains_behavioral_controller():
    circuit, layout = _build("E")
    netlist = str(circuit)
    assert layout.mode == "closed_loop"
    assert layout.controller is not None
    assert "V(ref)-V(out)" in netlist
    assert "0.5*(1+sin(" in netlist
    assert "V(duty)-V(ramp)" in netlist
    assert layout.elements["main_switch"] == "M1"
    assert layout.elements["gate_resistor"] == "RCG"


def test_closed_loop_nodes_include_control_and_load():
    _, layout = _build("E")
    for key in (
        "input",
        "drain",
        "gate",
        "switch",
        "output",
        "load",
        "reference",
        "error",
        "integral",
        "limited_duty",
        "pwm",
    ):
        assert layout.nodes[key]
    assert layout.nodes["load"] == "load_node"
    assert layout.features["uses_parasitic_capacitors"] is True


def test_open_loop_e_uses_fixed_pulse_and_no_controller():
    circuit, layout = _build("E", mode="open_loop")
    netlist = str(circuit)
    assert layout.controller is None
    assert "PULSE" in netlist
    assert "V(ref)-V(out)" not in netlist
    assert layout.elements["gate_driver"] == "VDRV"
    assert layout.features["uses_behavioral_controller"] is False


def test_sw_closed_loop_drives_control_node():
    circuit, layout = _build("SW")
    netlist = str(circuit)
    assert layout.elements["main_switch"] == "S1"
    assert layout.elements["switch_control"] == "BCCTRL"
    assert "5*V(pwm)" in netlist
    assert layout.controller is not None


def test_sw_open_loop_drives_gate():
    circuit, layout = _build("SW", mode="open_loop")
    netlist = str(circuit)
    assert layout.controller is None
    assert layout.elements["switch_control"] == ""
    assert layout.elements["gate_driver"] == "VPWM"
    assert "PULSE" in netlist


def test_variant_d_uses_nmos_without_parasitic_capacitors():
    _, layout = _build("D")
    assert layout.features["uses_parasitic_capacitors"] is False
    assert layout.elements["main_switch"] == "M1"


def test_invalid_mode_and_config_rejected():
    config = load_closed_loop_config()
    with pytest.raises(ValueError):
        build_closed_loop_buck(config, mode="magic")
    with pytest.raises(ValueError):
        build_closed_loop_buck("not a config")  # type: ignore[arg-type]


def test_layout_payload_is_json_ready():
    _, layout = _build("E")
    payload = layout.to_dict()
    assert payload["variant"] == "E"
    assert payload["mode"] == "closed_loop"
    assert payload["controller"]["expressions"]["error"] == "V(ref)-V(out)"
