"""频率响应派生指标：dB、截止频率插值、峰值与非有限值序列化。"""

from __future__ import annotations

import math

import numpy as np
import pytest

from analysis.frequency_response import (
    calculate_frequency_response,
    estimate_cutoff_frequency,
    estimate_cutoff_frequency_from_gain,
    gain_to_db,
    interpolate_crossing_log_frequency,
    peak_metrics,
    phase_unwrap,
    resonance_peak,
    sanitize_for_json,
)


def test_gain_to_db_and_zero_magnitude():
    assert gain_to_db([1.0, 0.5]) == pytest.approx([0.0, -6.020599913])
    with pytest.raises(ValueError):
        gain_to_db([-1.0])
    with pytest.raises(ValueError):
        gain_to_db([])


def test_transfer_function_and_complex_input_preserved():
    frequency = np.array([100.0, 1_000.0])
    vin = np.ones(2, dtype=complex)
    vout = np.array([1.0 + 0.0j, 0.5 - 0.5j])
    response = calculate_frequency_response(vin, vout)
    assert response["data_source"] == "derived_from_spice_simulation"
    assert response["magnitude"][1] == pytest.approx(math.sqrt(0.5))
    assert response["phase_deg"][1] == pytest.approx(-45.0)
    with pytest.raises(ValueError):
        calculate_frequency_response([0.0], [1.0])


def test_cutoff_interpolation_in_log_frequency():
    frequency = np.array([100.0, 1_000.0])
    magnitude = np.array([1.0, 0.5])
    result = estimate_cutoff_frequency(frequency, magnitude)
    assert result["found"] is True
    # 线性幅值 0.7071 在 log10(f) 上插值：f = 10^(2 + 0.5858)
    assert result["frequency_hz"] == pytest.approx(10 ** (2 + (1 - 1 / math.sqrt(2)) / 0.5))
    assert result["level_db"] == pytest.approx(-3.0103, abs=1e-4)


def test_cutoff_not_found_is_explicit():
    result = estimate_cutoff_frequency([1.0, 10.0], [0.5, 0.4])
    assert result["found"] is False
    assert "reason" in result
    result_gain = estimate_cutoff_frequency_from_gain([1.0, 10.0], [-1.0, -20.0])
    assert result_gain["found"] is True


def test_peak_metrics_marks_interior_peak():
    frequency = np.array([1.0, 10.0, 100.0])
    interior = peak_metrics(frequency, [1.0, 5.0, 2.0])
    assert interior["is_interior_peak"] is True
    boundary = peak_metrics(frequency, [5.0, 2.0, 1.0])
    assert boundary["is_interior_peak"] is False
    resonant = resonance_peak(frequency, [1.0, 5.0, 2.0])
    assert resonant["found_interior_peak"] is True


def test_phase_unwrap_removes_jumps():
    wrapped = np.array([170.0, -170.0])
    assert phase_unwrap(wrapped) == pytest.approx([170.0, 190.0])


def test_invalid_axes_rejected():
    with pytest.raises(ValueError):
        peak_metrics([1.0], [1.0])
    with pytest.raises(ValueError):
        peak_metrics([1.0, 1.0], [1.0, 2.0])


def test_sanitize_for_json_marks_non_finite():
    payload = {"a": float("nan"), "b": float("inf"), "c": float("-inf"), "d": np.float64(1.5)}
    cleaned = sanitize_for_json(payload)
    assert cleaned == {"a": "NaN", "b": "Infinity", "c": "-Infinity", "d": 1.5}
