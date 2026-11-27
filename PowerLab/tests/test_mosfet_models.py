"""MOSFET 教学模型电路构建测试。"""

from __future__ import annotations

import re

import pytest
from PySpice.Spice.Netlist import Circuit

from circuits.mosfet_models import (
    add_educational_nmos,
    add_mosfet_parasitic_capacitors,
    mosfet_metadata,
)
from circuits.nonideal_config import MosfetModelConfig


def _line(netlist: str, prefix: str) -> str:
    match = re.search(rf"^{prefix}\b.*$", netlist, flags=re.MULTILINE)
    assert match is not None, f"element {prefix} not found"
    return match.group(0)


def _base_circuit() -> Circuit:
    circuit = Circuit("mosfet test")
    circuit.V("DD", "drain", circuit.gnd, 5.0)
    circuit.V("GG", "gate", circuit.gnd, 10.0)
    return circuit


def test_nmos_instance_and_model_are_emitted():
    circuit = _base_circuit()
    name = add_educational_nmos(circuit, MosfetModelConfig(), "drain", "gate", circuit.gnd)
    assert name == "NMOS_EDU"
    netlist = str(circuit)
    assert re.search(r"^M1\s+drain\s+gate\s+0\s+0\s+NMOS_EDU", netlist, flags=re.MULTILINE)
    model_line = _line(netlist, ".model NMOS_EDU")
    assert "NMOS" in model_line
    assert "LEVEL=1" in model_line
    assert "VTO=3.0" in model_line
    assert "GAMMA=0" in model_line


def test_bulk_defaults_to_source_node():
    circuit = _base_circuit()
    add_educational_nmos(circuit, MosfetModelConfig(), "drain", "gate", "src", name="7")
    line = _line(str(circuit), "M7")
    assert re.match(r"^M7\s+drain\s+gate\s+src\s+src\s+NMOS_EDU", line)


def test_parasitic_capacitors_are_external_and_optional():
    circuit = _base_circuit()
    written = add_mosfet_parasitic_capacitors(
        circuit, MosfetModelConfig(), "drain", "gate", "src"
    )
    assert written == {"cgs_f": 1e-9, "cgd_f": 2e-10, "cds_f": 3e-10}
    netlist = str(circuit)
    assert re.match(r"^CGS\s+gate\s+src\s+1e-09", _line(netlist, "CGS"))
    assert re.match(r"^CGD\s+gate\s+drain", _line(netlist, "CGD"))
    assert re.match(r"^CDS\s+drain\s+src", _line(netlist, "CDS"))

    no_caps = MosfetModelConfig(external_cgs_f=0.0, external_cgd_f=0.0, external_cds_f=0.0)
    assert add_mosfet_parasitic_capacitors(_base_circuit(), no_caps, "drain", "gate", "src") == {}


def test_metadata_states_model_limitations():
    metadata = mosfet_metadata(MosfetModelConfig())
    assert metadata["model_name"] == "NMOS_EDU"
    assert metadata["spice_parameters"]["GAMMA"] == 0.0
    assert any("not a validated commercial" in note for note in metadata["limitations"])


def test_invalid_types_are_rejected():
    with pytest.raises(ValueError):
        add_educational_nmos("bad", MosfetModelConfig(), "d", "g", "s")
    with pytest.raises(ValueError):
        add_educational_nmos(_base_circuit(), "bad", "d", "g", "s")
    with pytest.raises(ValueError):
        add_mosfet_parasitic_capacitors(_base_circuit(), MosfetModelConfig(), "", "g", "s")
    with pytest.raises(ValueError):
        mosfet_metadata("bad")
