"""电感 DCR / 电容 ESR 模型构建测试。"""

from __future__ import annotations

import re

import pytest
from PySpice.Spice.Netlist import Circuit

from circuits.nonideal_config import CapacitorModelConfig, InductorModelConfig
from circuits.passive_models import add_capacitor_with_esr, add_inductor_with_dcr


def _line(netlist: str, prefix: str) -> str:
    match = re.search(rf"^{prefix}\b.*$", netlist, flags=re.MULTILINE)
    assert match is not None, f"element {prefix} not found"
    return match.group(0)


def test_inductor_with_dcr_inserts_internal_node():
    circuit = Circuit("inductor")
    mapping = add_inductor_with_dcr(circuit, InductorModelConfig(), "lx", "out")
    netlist = str(circuit)
    assert re.match(r"^L1\s+lx\s+l_dcr\s+4\.7e-05", _line(netlist, "L1"))
    assert re.match(r"^RDCR\s+l_dcr\s+out\s+0\.05", _line(netlist, "RDCR"))
    assert mapping["dcr_ohm"] == pytest.approx(0.05)
    assert mapping["inductor_output_node"] == "l_dcr"


def test_zero_dcr_collapses_to_direct_inductor():
    circuit = Circuit("inductor ideal")
    mapping = add_inductor_with_dcr(circuit, InductorModelConfig(dcr_ohm=0.0), "lx", "out")
    netlist = str(circuit)
    assert re.match(r"^L1\s+lx\s+out\b", _line(netlist, "L1"))
    assert "RDCR" not in netlist
    assert mapping["inductor_output_node"] == "out"


def test_capacitor_with_esr_inserts_internal_node():
    circuit = Circuit("cap")
    mapping = add_capacitor_with_esr(circuit, CapacitorModelConfig(), "out", circuit.gnd)
    netlist = str(circuit)
    assert re.match(r"^RESR\s+out\s+cap_internal\s+0\.03", _line(netlist, "RESR"))
    assert re.match(r"^C1\s+cap_internal\s+0\s+0\.0001", _line(netlist, "C1"))
    assert mapping["esr_ohm"] == pytest.approx(0.03)


def test_zero_esr_collapses_to_direct_capacitor():
    circuit = Circuit("cap ideal")
    mapping = add_capacitor_with_esr(circuit, CapacitorModelConfig(esr_ohm=0.0), "out", "0")
    netlist = str(circuit)
    assert re.match(r"^C1\s+out\s+0\b", _line(netlist, "C1"))
    assert "RESR" not in netlist
    assert mapping["capacitor_internal_node"] == "out"


def test_internal_node_must_differ_from_terminals():
    with pytest.raises(ValueError):
        add_inductor_with_dcr(
            Circuit("bad"), InductorModelConfig(), "out", "out2", internal_node="out"
        )
    with pytest.raises(ValueError):
        add_capacitor_with_esr(
            Circuit("bad"), CapacitorModelConfig(), "out", "0", internal_node="0"
        )


def test_invalid_configuration():
    with pytest.raises(ValueError):
        InductorModelConfig(inductance_h=0.0)
    with pytest.raises(ValueError):
        InductorModelConfig(dcr_ohm=-0.1)
    with pytest.raises(ValueError):
        CapacitorModelConfig(capacitance_f=-1e-6)
    with pytest.raises(ValueError):
        add_inductor_with_dcr(Circuit("x"), "bad", "a", "b")
