"""电阻分压：真实求解结果与理论值一致性。"""

from __future__ import annotations

import pytest

from circuits.divider import build_voltage_divider, theoretical_output_voltage
from scripts.voltage_divider_demo import simulate_voltage_divider


def test_voltage_divider_matches_theory():
    result = simulate_voltage_divider()
    assert result["vin"] == pytest.approx(12.0, abs=1e-6)
    assert result["vout"] == pytest.approx(6.0, abs=1e-6)
    assert result["theoretical_vout"] == pytest.approx(6.0, abs=1e-12)
    assert result["data_source"] == "spice_simulation"


def test_voltage_divider_error_is_negligible():
    result = simulate_voltage_divider()
    assert result["metrics"]["absolute_error_v"] < 1e-6
    assert abs(result["metrics"]["relative_error_percent"]) < 1e-6


def test_netlist_contains_expected_elements():
    netlist = str(build_voltage_divider())
    assert "R1" in netlist
    assert "R2" in netlist
    assert "Vinput" in netlist


def test_theoretical_output_scales_with_input():
    assert theoretical_output_voltage(24.0) == pytest.approx(12.0, abs=1e-12)


@pytest.mark.parametrize("bad", [0.0, -1.0, float("nan"), float("inf")])
def test_invalid_divider_parameters_raise(bad):
    with pytest.raises(ValueError):
        build_voltage_divider(vin_v=bad)
    with pytest.raises(ValueError):
        build_voltage_divider(r1_ohm=bad)


def test_bool_is_rejected_as_parameter():
    with pytest.raises(ValueError):
        build_voltage_divider(vin_v=True)  # type: ignore[arg-type]
