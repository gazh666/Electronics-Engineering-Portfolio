"""CCM / DCM / 临界模式识别测试（人工构造数组）。"""

from __future__ import annotations

import numpy as np
import pytest

from analysis.conduction_mode import (
    ConductionMode,
    classify_conduction_mode,
    mode_from_mapping,
    theoretical_conduction_mode,
    time_fraction_below,
)

PERIOD_S = 10e-6


def _time_and_phase(cycles: int = 3, samples: int = 400):
    time = np.arange(0.0, cycles * PERIOD_S, PERIOD_S / samples)
    phase = np.mod(time, PERIOD_S) / PERIOD_S
    boundaries = [index * PERIOD_S for index in range(cycles + 1)]
    return time, phase, boundaries


def _ccm_current(phase):
    return 2.0 + 2.0 * np.abs(2.0 * phase - 1.0)


def _dcm_current(phase):
    duty = 0.4
    return np.where(phase < duty, 2.0 * phase / duty, 0.0)


def test_time_fraction_below_is_time_weighted():
    time = np.linspace(0.0, 1.0, 1001)
    values = np.where(time < 0.5, 0.0, 5.0)
    ratio, duration = time_fraction_below(time, values, 0.05)
    assert ratio == pytest.approx(0.5, abs=1e-3)
    assert duration == pytest.approx(0.5, abs=1e-3)


def test_time_fraction_below_requires_both_bounds():
    with pytest.raises(ValueError):
        time_fraction_below([0.0, 1.0], [0.0, 1.0], 0.1, start_s=0.0)


def test_heavy_load_identified_as_ccm():
    time, phase, boundaries = _time_and_phase()
    result = classify_conduction_mode(time, _ccm_current(phase), boundaries)
    assert result.mode is ConductionMode.CCM
    assert result.near_zero_time_ratio < 0.005
    assert result.valley_current_a == pytest.approx(2.0, abs=1e-6)
    assert result.cycles_analyzed == 2


def test_light_load_identified_as_dcm_with_evidence():
    time, phase, boundaries = _time_and_phase()
    result = classify_conduction_mode(time, _dcm_current(phase), boundaries)
    assert result.mode is ConductionMode.DCM
    assert result.near_zero_time_ratio > 0.4
    assert result.valley_current_a == pytest.approx(0.0, abs=1e-9)


def test_short_near_zero_window_is_boundary_uncertain():
    time, phase, boundaries = _time_and_phase()
    current = np.where((phase > 0.2) & (phase < 0.215), 0.0, 2.0)
    result = classify_conduction_mode(time, current, boundaries)
    assert result.mode is ConductionMode.BOUNDARY_OR_UNCERTAIN
    assert 0.005 < result.near_zero_time_ratio < 0.02


def test_obvious_reverse_current_is_anomaly_not_dcm():
    time, phase, boundaries = _time_and_phase()
    current = 1.0 + 3.0 * np.abs(2.0 * phase - 1.0)
    current = current - 1.5
    current[phase > 0.1] = np.abs(current[phase > 0.1]) + 0.5
    current[np.argmin(current)] = -0.8
    result = classify_conduction_mode(time, current, boundaries)
    assert result.mode is ConductionMode.INVALID
    assert result.reverse_current_anomaly


def test_missing_cycle_boundaries_return_invalid():
    time, phase, _ = _time_and_phase()
    result = classify_conduction_mode(time, _ccm_current(phase), [])
    assert result.mode is ConductionMode.INVALID
    assert result.cycles_analyzed == 0


def test_boundaries_outside_waveform_return_invalid():
    time, phase, _ = _time_and_phase()
    result = classify_conduction_mode(time, _ccm_current(phase), [10.0, 20.0])
    assert result.mode is ConductionMode.INVALID


def test_invalid_boundary_order_and_ratio_config_are_rejected():
    time, phase, _ = _time_and_phase()
    with pytest.raises(ValueError):
        classify_conduction_mode(time, _ccm_current(phase), [0.0, 2e-5, 1e-5])
    with pytest.raises(ValueError):
        classify_conduction_mode(
            time,
            _ccm_current(phase),
            [0.0, PERIOD_S],
            boundary_ratio=0.05,
            dcm_minimum_near_zero_ratio=0.02,
        )


def test_theoretical_mode_compare_to_boundary_current():
    assert theoretical_conduction_mode(0.31, 2.0) is ConductionMode.CCM
    assert theoretical_conduction_mode(0.31, 0.1) is ConductionMode.DCM
    assert theoretical_conduction_mode(0.31, 0.31) is ConductionMode.BOUNDARY_OR_UNCERTAIN
    with pytest.raises(ValueError):
        theoretical_conduction_mode(0.0, 1.0)
    with pytest.raises(ValueError):
        theoretical_conduction_mode(0.31, 1.0, relative_tolerance=1.0)


def test_mode_from_mapping():
    assert mode_from_mapping({"mode": "DCM"}) is ConductionMode.DCM
    assert mode_from_mapping({"conduction_mode": ConductionMode.CCM}) is ConductionMode.CCM
    with pytest.raises(ValueError):
        mode_from_mapping({"mode": "unknown"})
    with pytest.raises(ValueError):
        mode_from_mapping({"mode": 1})


def test_result_serialization():
    time, phase, boundaries = _time_and_phase()
    payload = classify_conduction_mode(time, _dcm_current(phase), boundaries).to_dict()
    assert payload["mode"] == "DCM"
    assert payload["data_source"] == "spice_simulation"
    assert payload["cycles_analyzed"] == 2
