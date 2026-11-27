"""第五阶段统一时域计算测试（合成数组，不调用 SPICE）。"""

from __future__ import annotations

import numpy as np
import pytest

from analysis.time_domain import (
    clip_time_window,
    maximum_value,
    minimum_value,
    peak_to_peak,
    time_integral,
    time_step_statistics,
    time_weighted_ac_rms,
    time_weighted_mean,
    time_weighted_rms,
    time_weighted_std,
    validate_time_series,
)


def _sine(amplitude: float = 0.1, frequency: float = 1000.0, duration: float = 5e-3):
    time = np.linspace(0.0, duration, 5001)
    values = 5.0 + amplitude * np.sin(2.0 * np.pi * frequency * time)
    return time, values


def test_validate_time_series_rejects_bad_input():
    with pytest.raises(ValueError):
        validate_time_series([0.0, 1.0], [1.0])
    with pytest.raises(ValueError):
        validate_time_series([0.0], [1.0])
    with pytest.raises(ValueError):
        validate_time_series([0.0, 1.0], [1.0, float("nan")])
    with pytest.raises(ValueError):
        validate_time_series([0.0, 0.0], [1.0, 2.0])


def test_validate_reports_named_waveform_in_message():
    with pytest.raises(ValueError, match="vout_v"):
        validate_time_series([0.0, 1e-3], [1.0, float("inf")], "vout_v")


def test_time_weighted_mean_on_nonuniform_samples():
    time = [0.0, 1.0, 3.0]
    values = [0.0, 0.0, 4.0]
    assert time_weighted_mean(time, values) == pytest.approx(4.0 / 3.0)
    assert time_integral(time, values) == pytest.approx(4.0)


def test_rms_and_ac_rms_on_sine():
    time, values = _sine(amplitude=0.2, frequency=1000.0)
    expected_rms = 0.2 / np.sqrt(2.0)
    assert time_weighted_mean(time, values) == pytest.approx(5.0, abs=1e-6)
    assert time_weighted_ac_rms(time, values) == pytest.approx(expected_rms, rel=1e-3)
    assert time_weighted_std(time, values) == pytest.approx(expected_rms, rel=1e-3)
    assert time_weighted_rms(time, values) == pytest.approx(
        np.sqrt(25.0 + expected_rms**2), rel=1e-6
    )


def test_clip_time_window_interpolates_and_validates():
    time = np.array([0.0, 1.0, 2.0])
    values = np.array([0.0, 10.0, 20.0])
    window_time, window_values = clip_time_window(time, values, 0.5, 1.5)
    assert window_time[0] == pytest.approx(0.5)
    assert window_time[-1] == pytest.approx(1.5)
    assert window_values.tolist() == pytest.approx([5.0, 10.0, 15.0])
    with pytest.raises(ValueError):
        clip_time_window(time, values, -0.1, 1.0)
    with pytest.raises(ValueError):
        clip_time_window(time, values, 1.0, 0.5)
    with pytest.raises(ValueError):
        clip_time_window(time, values, 0.0, float("inf"))


def test_peak_min_max_use_raw_samples():
    values = np.array([3.0, -1.0, 2.5])
    assert peak_to_peak(values) == pytest.approx(4.0)
    assert minimum_value(values) == pytest.approx(-1.0)
    assert maximum_value(values) == pytest.approx(3.0)
    with pytest.raises(ValueError):
        peak_to_peak([])
    with pytest.raises(ValueError):
        peak_to_peak([1.0, float("nan")])


def test_time_step_statistics_reports_gaps():
    time = [0.0, 1e-9, 5e-9, 6e-9]
    stats = time_step_statistics(time)
    assert stats["sample_count"] == 4
    assert stats["duration_s"] == pytest.approx(6e-9)
    assert stats["min_step_s"] == pytest.approx(1e-9)
    assert stats["max_step_s"] == pytest.approx(4e-9)
    assert stats["mean_step_s"] == pytest.approx(2e-9)
    assert stats["median_step_s"] == pytest.approx(1e-9)
    with pytest.raises(ValueError):
        time_step_statistics([0.0])
    with pytest.raises(ValueError):
        time_step_statistics([0.0, 0.0])
