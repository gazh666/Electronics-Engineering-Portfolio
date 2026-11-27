"""纹波、逐周期统计与 ESR 分解测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from analysis.ripple_analysis import (
    analyze_ripple,
    cycle_ripple_statistics,
    cycle_ripple_values,
    decompose_output_ripple,
    theoretical_ripple_components,
)

PERIOD_S = 10e-6


def _ripple_waveform(offset: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    time = np.linspace(0.0, 20 * PERIOD_S, 4001)
    phase = 2.0 * np.pi * time / PERIOD_S
    values = 5.0 + offset + 0.01 * np.sin(phase)
    return time, values


def test_analyze_ripple_separates_dc_and_ac():
    time, values = _ripple_waveform()
    result = analyze_ripple(time, values)
    assert result.mean_value == pytest.approx(5.0, abs=1e-6)
    assert result.peak_to_peak == pytest.approx(0.02, rel=2e-3)
    assert result.minimum_value == pytest.approx(4.99, abs=1e-4)
    assert result.maximum_value == pytest.approx(5.01, abs=1e-4)
    assert result.total_rms == pytest.approx(np.sqrt(25.0 + 0.005**2), rel=1e-6)
    assert result.ac_rms == pytest.approx(0.01 / np.sqrt(2.0), rel=2e-3)
    assert result.ripple_percent == pytest.approx(0.02 / 5.0 * 100.0, rel=2e-3)
    assert result.sample_count == time.size
    assert result.data_source == "spice_derived"
    assert result.to_dict()["unit"] == "V"


def test_analyze_ripple_sets_percent_none_near_zero_mean():
    time = np.linspace(0.0, 1e-3, 101)
    result = analyze_ripple(time, np.zeros_like(time))
    assert result.ripple_percent is None
    assert result.peak_to_peak == 0.0


def test_analyze_ripple_rejects_invalid_arrays():
    with pytest.raises(ValueError):
        analyze_ripple([0.0], [1.0])
    with pytest.raises(ValueError):
        analyze_ripple([0.0, 1.0], [1.0, float("nan")])


def test_cycle_ripple_values_per_cycle():
    time = np.array([0.0, 0.5, 1.0, 1.5, 2.0])
    values = np.array([0.0, 1.0, 0.0, 1.0, 0.0])
    assert cycle_ripple_values(time, values, [0.0, 1.0, 2.0]) == pytest.approx([1.0, 1.0])
    with pytest.raises(ValueError):
        cycle_ripple_values(time, values, [0.0])
    with pytest.raises(ValueError):
        cycle_ripple_values(time, values, [0.0, 2.0, 1.0])


def test_cycle_ripple_statistics_flags_drift():
    time, values = _ripple_waveform(offset=0.0)
    boundaries = [index * PERIOD_S for index in range(21)]
    stats = cycle_ripple_statistics(time, values, boundaries)
    assert stats["cycle_count"] == 20
    assert stats["cycle_ripple_mean"] == pytest.approx(0.02, rel=5e-2)
    assert stats["window_ripple"] == pytest.approx(0.02, rel=5e-2)
    assert stats["drift_warning"] is False

    drifting = values + np.linspace(0.0, 0.5, values.size)
    drift_stats = cycle_ripple_statistics(time, drifting, boundaries)
    assert drift_stats["drift_warning"] is True


def test_decompose_output_ripple_reconstructs_identity():
    time = np.linspace(0.0, 20 * PERIOD_S, 2001)
    phase = 2.0 * np.pi * time / PERIOD_S
    capacitor = 5.0 + 0.004 * np.sin(phase)
    esr = 0.01 * np.cos(phase) * 0.5
    frame = pd.DataFrame(
        {
            "time_s": time,
            "vout_v": capacitor + esr,
            "capacitor_internal_voltage_v": capacitor,
            "capacitor_esr_voltage_v": esr,
        }
    )
    decomposition = decompose_output_ripple(frame)
    assert decomposition.output_vpp_v == pytest.approx(np.ptp(capacitor + esr), rel=1e-9)
    assert decomposition.capacitor_internal_vpp_v == pytest.approx(np.ptp(capacitor), rel=1e-9)
    assert decomposition.esr_vpp_v == pytest.approx(np.ptp(esr), rel=1e-9)
    assert decomposition.reconstruction_max_abs_v < 1e-12
    assert decomposition.to_dict()["data_source"] == "spice_derived"


def test_decompose_output_ripple_requires_columns():
    frame = pd.DataFrame({"time_s": [0.0, 1.0], "vout_v": [1.0, 2.0]})
    with pytest.raises(ValueError):
        decompose_output_ripple(frame)
    with pytest.raises(ValueError):
        decompose_output_ripple("not-a-frame")


def test_theoretical_ripple_components_are_labelled_theory():
    payload = theoretical_ripple_components(0.4, 100e3, 100e-6, 0.03)
    assert payload["capacitor_voltage_ripple_vpp"] == pytest.approx(0.005, rel=1e-12)
    assert payload["esr_voltage_ripple_vpp"] == pytest.approx(0.012, rel=1e-12)
    assert payload["data_source"] == "analytical_theory"
    with pytest.raises(ValueError):
        theoretical_ripple_components(0.4, 0.0, 100e-6, 0.03)
    with pytest.raises(ValueError):
        theoretical_ripple_components(0.4, 100e3, 0.0, 0.03)
    with pytest.raises(ValueError):
        theoretical_ripple_components(0.4, 100e3, 100e-6, -0.01)
