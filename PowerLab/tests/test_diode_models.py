"""非理想续流二极管模型构建测试。"""

from __future__ import annotations

import re

import pytest
from PySpice.Spice.Netlist import Circuit

from circuits.diode_models import add_nonideal_diode, diode_metadata
from circuits.nonideal_config import DiodeModelConfig


def _line(netlist: str, prefix: str) -> str:
    match = re.search(rf"^{prefix}\b.*$", netlist, flags=re.MULTILINE)
    assert match is not None, f"element {prefix} not found"
    return match.group(0)


def _circuit() -> Circuit:
    circuit = Circuit("diode test")
    circuit.V("AA", "anode", circuit.gnd, 0.8)
    return circuit


def test_diode_element_and_model():
    circuit = _circuit()
    name = add_nonideal_diode(circuit, DiodeModelConfig(), "anode", circuit.gnd)
    assert name == "DFREE_NONIDEAL"
    netlist = str(circuit)
    assert re.match(r"^DFREE\s+anode\s+0\s+DFREE_NONIDEAL", _line(netlist, "DFREE"))
    model = _line(netlist, ".model DFREE_NONIDEAL")
    assert ".model DFREE_NONIDEAL D (" in model
    assert "IS=1e-06" in model
    assert "RS=0.015" in model
    assert "CJO=2e-10" in model


def test_diode_reference_connection():
    circuit = Circuit("diode ref")
    add_nonideal_diode(circuit, DiodeModelConfig(), "sw", "0", name="BODY")
    line = _line(str(circuit), "DBODY")
    assert re.match(r"^DBODY\s+sw\s+0\s+DFREE_NONIDEAL", line)


def test_metadata_marks_teaching_model():
    metadata = diode_metadata(DiodeModelConfig())
    assert metadata["model_name"] == "DFREE_NONIDEAL"
    assert metadata["spice_parameters"]["TT"] == 0.0
    assert any("not a validated" in note for note in metadata["limitations"])


def test_invalid_configuration_and_types():
    with pytest.raises(ValueError):
        DiodeModelConfig(saturation_current_a=0.0)
    with pytest.raises(ValueError):
        DiodeModelConfig(series_resistance_ohm=-1.0)
    with pytest.raises(ValueError):
        DiodeModelConfig(grading_coefficient=0.0)
    with pytest.raises(ValueError):
        add_nonideal_diode(_circuit(), "bad", "a", "0")
    with pytest.raises(ValueError):
        diode_metadata("bad")
