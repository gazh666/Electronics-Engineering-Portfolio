"""第五阶段真实 ngspice 集成测试：开关、比较器、栅极、均衡。"""

from __future__ import annotations

import pytest

from circuits.balancing_circuit import run_balancing_spice
from circuits.gate_driver import analyze_gate_drive, run_gate_driver_spice
from circuits.protection_comparator import run_overvoltage_comparator_spice
from circuits.protection_mosfet import run_switch_case_matrix, run_turn_off_transient
from circuits.spice_utils import get_solve_count, reset_solve_counter
from protection.limits import load_limits


@pytest.fixture(scope="module")
def limits():
    return load_limits()


def test_real_spice_back_to_back_switch_matrix(limits):
    reset_solve_counter()
    cases = {case.case: case for case in run_switch_case_matrix(limits)}
    assert get_solve_count() == 7
    on = cases["CASE_A_BOTH_ON_DISCHARGE"]
    assert on.switch_current_a == pytest.approx(1.0, abs=0.1)
    assert on.switch_drop_v < 0.06
    assert on.switch_resistance_ohm < 0.045
    assert abs(cases["CASE_C_CHG_OFF_BLOCK_CHARGE"].charge_current_a) < 1e-3
    assert abs(cases["CASE_D_DSG_OFF_BLOCK_DISCHARGE"].load_current_a) < 1e-3
    assert abs(cases["CASE_E_BOTH_OFF_LEAKAGE"].switch_current_a) < 1e-6
    assert abs(cases["CASE_F_INPUT_COLLAPSE_BOTH_ON"].switch_current_a) > 1.0
    assert abs(cases["CASE_G_INPUT_COLLAPSE_DSG_OFF"].switch_current_a) < 1e-3


def test_real_spice_turn_off_transient(limits):
    reset_solve_counter()
    waveform = run_turn_off_transient(limits)
    assert get_solve_count() == 1
    assert waveform.current_cutoff_time_s is not None
    assert abs(waveform.discharge_current_a[-1]) < 0.01


def test_real_spice_comparator_threshold_and_delay(limits):
    reset_solve_counter()
    result = run_overvoltage_comparator_spice()
    assert get_solve_count() == 2
    assert result.measured_trip_voltage_v == pytest.approx(result.cell_trip_voltage_v, abs=0.005)
    assert result.measured_hysteresis_v == pytest.approx(result.configured_hysteresis_v, abs=0.010)
    assert result.delay_relative_error is not None
    assert result.delay_relative_error < 0.10


def test_real_spice_gate_driver(limits):
    analysis = analyze_gate_drive(limits, fet_count=2)
    result = run_gate_driver_spice(limits)
    assert result["steady_gate_voltage_v"] == pytest.approx(10.0, abs=0.01)
    assert result["measured_peak_current_a"] == pytest.approx(analysis.peak_gate_current_a, rel=0.05)
    assert result["measured_rise_time_s"] == pytest.approx(
        analysis.theoretical_rise_time_s, rel=0.15
    )


def test_real_spice_balancing_branches(limits):
    result = run_balancing_spice(limits, (4.05, 4.12, 4.18), (False, False, True))
    assert result.channels[2].branch_current_a == pytest.approx(4.18 / 100.04, rel=0.002)
    assert result.channels[2].resistor_power_w < limits.balance_resistor_power_rating_w
    assert result.channels[0].branch_current_a < 1e-6
