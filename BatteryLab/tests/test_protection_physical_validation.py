"""保护级建模单元测试：检查真实器件网表结构，不执行瞬态求解。"""

from __future__ import annotations

import pytest

from hardening.protection_physical_validation import (
    MosfetProtectionSpec,
    ProtectionValidationError,
    build_conduction_circuit,
    build_integrated_protection_circuit,
    build_ocp_circuit,
)


def _spec() -> MosfetProtectionSpec:
    return MosfetProtectionSpec()


def test_spec_rejects_non_positive_parameters():
    with pytest.raises(ProtectionValidationError):
        MosfetProtectionSpec(ocp_threshold_a=0.0)
    with pytest.raises(ProtectionValidationError):
        MosfetProtectionSpec(cgs_f=-1e-9)


def test_conduction_circuit_uses_real_mosfet_and_body_diode():
    for mode in ("on_discharge", "off_discharge_block", "on_charge", "off_charge_block"):
        circuit, layout = build_conduction_circuit(mode, _spec())
        text = circuit.raw_spice
        assert "NMOS (LEVEL=1" in text
        assert layout.model_names["mosfet"] in text
        assert layout.model_names["body"] in text


def test_ocp_circuit_contains_switch_comparator_and_peak_hold():
    circuit, layout = build_ocp_circuit(_spec(), fault_time_s=2e-4, end_time_s=4e-4)
    text = circuit.raw_spice
    assert layout.model_names["switch"] in text
    assert layout.model_names["peak"] in text
    assert "SWOCP" in text


def test_integrated_circuit_contains_buck_and_protection_models():
    cells = [{"ocv_v": 3.7, "r0_ohm": 0.02, "rp_ohm": 0.01, "cp_f": 1000.0} for _ in range(3)]
    circuit, meta = build_integrated_protection_circuit(
        _spec(),
        cells=cells,
        fault_time_s=4e-3,
        end_time_s=5e-3,
        inductance_h=68e-6,
        capacitance_f=330e-6,
        inductor_dcr_ohm=0.02,
        capacitor_esr_ohm=0.005,
        load_resistance_ohm=2.5,
        fault_load_resistance_ohm=0.5,
    )
    text = circuit.raw_spice
    assert meta["protection"]["model_names"]["mosfet"] in text
    assert "BLOAD_STEP" in text
    assert meta["load_step_from_ohm"] == 2.5
    assert meta["load_step_to_ohm"] == 0.5
