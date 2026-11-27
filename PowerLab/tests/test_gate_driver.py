"""浮动高侧栅极驱动模型测试。"""

from __future__ import annotations

import re

import pytest
from PySpice.Spice.Netlist import Circuit

from circuits.gate_driver import (
    add_floating_gate_driver,
    add_ground_referenced_gate_drive,
    gate_resistor_current_a,
    pulldown_current_a,
)
from circuits.nonideal_config import GateDriverConfig, load_nonideal_buck_config


def _pwm():
    return load_nonideal_buck_config().pwm


def _line(netlist: str, prefix: str) -> str:
    match = re.search(rf"^{prefix}\b.*$", netlist, flags=re.MULTILINE)
    assert match is not None, f"element {prefix} not found"
    return match.group(0)


def test_floating_driver_references_switch_node():
    circuit = Circuit("driver")
    mapping = add_floating_gate_driver(circuit, _pwm(), GateDriverConfig())
    netlist = str(circuit)
    assert re.match(r"^VDRV\s+drv\s+sw\s+DC\s+0V\s+PULSE\(", _line(netlist, "VDRV"))
    assert re.match(r"^RG\s+drv\s+gate\s+10\b", _line(netlist, "RG"))
    assert re.match(r"^RGS\s+gate\s+sw\s+100000\b", _line(netlist, "RGS"))
    assert mapping["driver_source"] == "VDRV"
    assert mapping["gate_resistor"] == "RG"
    assert mapping["pulldown_resistor"] == "RGS"


def test_ground_referenced_drive_is_explicitly_not_bootstrap():
    circuit = Circuit("ground drive")
    name = add_ground_referenced_gate_drive(circuit, _pwm(), "gate", name="PWM")
    assert name == "VPWM"
    assert re.match(r"^VPWM\s+gate\s+0\s+DC", _line(str(circuit), "VPWM"))


def test_nodes_must_be_distinct_and_nonempty():
    circuit = Circuit("bad")
    with pytest.raises(ValueError):
        add_floating_gate_driver(circuit, _pwm(), GateDriverConfig(), gate_node="sw")
    with pytest.raises(ValueError):
        add_floating_gate_driver(circuit, _pwm(), GateDriverConfig(), drive_node="")
    with pytest.raises(ValueError):
        add_floating_gate_driver("bad", _pwm(), GateDriverConfig())


def test_gate_current_helpers():
    assert gate_resistor_current_a(10.0, 8.0, 10.0) == pytest.approx(0.2)
    assert pulldown_current_a(10.0, 0.0, 100_000.0) == pytest.approx(1e-4)
    with pytest.raises(ValueError):
        gate_resistor_current_a(10.0, 8.0, 0.0)
    with pytest.raises(ValueError):
        pulldown_current_a(10.0, 0.0, -1.0)


def test_driver_metadata_marks_ideal_source():
    payload = GateDriverConfig().to_dict()
    assert payload["driver_type"] == "ideal_floating_source"
    assert "no bootstrap" in payload["note"]
