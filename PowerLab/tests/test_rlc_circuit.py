"""串联 RLC：三种阻尼瞬态与谐振交流（真实 ngspice）。"""

from __future__ import annotations

import numpy as np
import pytest

from analysis.frequency_response import resonance_peak
from analysis.theory import (
    rlc_critical_resistance,
    rlc_damping_ratio,
    rlc_natural_frequency,
    rlc_peak_frequency,
    rlc_step_overshoot_percent,
)
from circuits.rlc_circuit import build_rlc_ac, build_rlc_transient
from simulations.runner import SimulationRunner

L_H = 0.01
C_F = 1e-6
INPUT_V = 5.0


@pytest.fixture(scope="module")
def runner() -> SimulationRunner:
    return SimulationRunner(25.0)


@pytest.fixture(scope="module")
def transient_cases(runner):
    cases = {}
    for resistance in (10.0, 200.0, 400.0):
        circuit = build_rlc_transient(resistance, L_H, C_F, input_v=INPUT_V)
        result = runner.run_transient(circuit, 5e-7, 20e-3)
        cases[resistance] = result.data
    return cases


@pytest.fixture(scope="module")
def ac_result(runner):
    circuit = build_rlc_ac(10.0, L_H, C_F)
    return runner.run_ac(circuit, 10.0, 100_000.0, 200)


def test_natural_frequency_and_critical_resistance():
    assert rlc_natural_frequency(L_H, C_F) == pytest.approx(1591.5494309)
    assert rlc_critical_resistance(L_H, C_F) == pytest.approx(200.0)


def test_damping_ratios_match_design(transient_cases):
    assert rlc_damping_ratio(10.0, L_H, C_F) == pytest.approx(0.05)
    assert rlc_damping_ratio(200.0, L_H, C_F) == pytest.approx(1.0)
    assert rlc_damping_ratio(400.0, L_H, C_F) == pytest.approx(2.0)
    assert all(len(frame) > 1000 for frame in transient_cases.values())


def test_underdamped_overshoot_matches_theory(transient_cases):
    frame = transient_cases[10.0]
    voltage = frame["out_v"].to_numpy()
    final_value = float(voltage[-1])
    overshoot = (float(np.max(voltage)) - final_value) / abs(final_value) * 100.0
    assert overshoot == pytest.approx(
        rlc_step_overshoot_percent(10.0, L_H, C_F), abs=2.0
    )
    assert overshoot > 80.0


def test_critical_and_overdamped_have_no_overshoot(transient_cases):
    for resistance in (200.0, 400.0):
        voltage = transient_cases[resistance]["out_v"].to_numpy()
        final_value = float(voltage[-1])
        assert float(np.max(voltage)) <= final_value + 1e-6


def test_all_cases_settle_to_input(transient_cases):
    for resistance, frame in transient_cases.items():
        voltage = frame["out_v"].to_numpy()
        tolerance = 0.5 if resistance == 10.0 else 0.01
        assert float(voltage[-1]) == pytest.approx(INPUT_V, abs=tolerance)


def test_inductor_current_is_continuous_and_nonnegative(transient_cases):
    current = transient_cases[10.0]["l1_branch_current_a"].to_numpy()
    assert np.all(np.isfinite(current))
    assert current[0] == pytest.approx(0.0, abs=1e-9)
    assert np.all(np.abs(np.diff(current)) < 0.01)


def test_ac_resonance_peak_matches_theory(ac_result):
    frequency = ac_result.data["frequency_hz"].to_numpy()
    real = ac_result.data["out_real_v"].to_numpy()
    imag = ac_result.data["out_imag_v"].to_numpy()
    magnitude = np.abs(real + 1j * imag)
    peak = resonance_peak(frequency, magnitude)
    assert peak["is_interior_peak"] is True
    theoretical = rlc_peak_frequency(10.0, L_H, C_F)
    assert theoretical is not None
    assert peak["peak_frequency_hz"] == pytest.approx(theoretical, rel=0.03)
    assert peak["peak_value"] == pytest.approx(10.0, rel=0.10)


def test_ac_result_keeps_complex_columns(ac_result):
    assert "out_real_v" in ac_result.data.columns
    assert "out_imag_v" in ac_result.data.columns
    assert ac_result.point_count == 801


def test_invalid_rlc_parameters_raise():
    with pytest.raises(ValueError):
        build_rlc_transient(0.0, L_H, C_F)
    with pytest.raises(ValueError):
        build_rlc_ac(10.0, -L_H, C_F)
