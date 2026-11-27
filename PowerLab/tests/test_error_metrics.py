"""误差指标：零参考、非均匀时间加权、插值对齐与异常。"""

from __future__ import annotations

import numpy as np
import pytest

from analysis.error_metrics import (
    aligned_error_metrics,
    calculate_error_metrics,
    cutoff_frequency_error,
    error_near_time_constant,
    format_metrics,
    interpolate_to_time_axis,
    relative_error,
    scalar_relative_error_percent,
    time_weighted_error_metrics,
    zero_reference_count,
)


def test_absolute_and_relative_error_with_zero_reference():
    simulated = np.array([1.0, 2.0, 3.0])
    theoretical = np.array([0.0, 2.0, 4.0])
    relative = relative_error(simulated, theoretical)
    assert np.isnan(relative[0])
    assert relative[1] == pytest.approx(0.0)
    assert relative[2] == pytest.approx(-0.25)
    assert zero_reference_count(theoretical) == 1
    assert scalar_relative_error_percent(1.0, 0.0) is None


def test_calculate_error_metrics():
    metrics = calculate_error_metrics([1.0, 2.0, 3.0], [1.0, 2.0, 4.0])
    assert metrics["sample_count"] == 3
    assert metrics["mae"] == pytest.approx(1.0 / 3.0)
    assert metrics["rmse"] == pytest.approx(np.sqrt(1.0 / 3.0))
    assert metrics["max_absolute_error"] == pytest.approx(1.0)
    assert metrics["max_absolute_error_index"] == 2
    assert metrics["data_source"] == "comparison"


def test_shape_mismatch_and_non_finite_rejected():
    with pytest.raises(ValueError):
        calculate_error_metrics([1.0, 2.0], [1.0])
    with pytest.raises(ValueError):
        calculate_error_metrics([1.0, np.nan], [1.0, 2.0])


def test_time_weighted_metrics_favour_long_intervals():
    # 前半段采样密集误差大，后半段采样稀疏误差为零；
    # 时间加权 RMSE 必须明显小于按点平均的 RMSE。
    time_s = np.array([0.0, 0.1, 0.2, 1.0])
    simulated = np.array([1.0, 1.0, 1.0, 0.0])
    theoretical = np.zeros(4)
    metrics = time_weighted_error_metrics(time_s, simulated, theoretical)
    point_rmse = float(np.sqrt(np.mean((simulated - theoretical) ** 2)))
    assert metrics["rmse_time_weighted"] < point_rmse
    assert metrics["time_span_s"] == pytest.approx(1.0)
    assert metrics["nonuniform_sampling"] is True


def test_time_weighted_rejects_bad_time_axis():
    with pytest.raises(ValueError):
        time_weighted_error_metrics([0.0, 0.0], [1.0, 1.0], [0.0, 0.0])
    with pytest.raises(ValueError):
        time_weighted_error_metrics([0.0], [1.0], [0.0])


def test_interpolation_and_extrapolation_guard():
    source_time = np.array([0.0, 1.0, 2.0])
    values = np.array([0.0, 10.0, 20.0])
    target = np.array([0.5, 1.5])
    assert interpolate_to_time_axis(source_time, values, target) == pytest.approx([5.0, 15.0])
    with pytest.raises(ValueError):
        interpolate_to_time_axis(source_time, values, np.array([-0.1, 1.0]))
    with pytest.raises(ValueError):
        interpolate_to_time_axis(source_time, values, np.array([1.0, 2.1]))


def test_aligned_metrics_interpolates_theory():
    sim_time = np.array([0.0, 1.0, 2.0])
    simulated = np.array([0.0, 1.0, 2.0])
    theory_time = np.array([0.0, 2.0])
    theoretical = np.array([0.0, 2.0])
    metrics = aligned_error_metrics(sim_time, simulated, theory_time, theoretical)
    assert metrics["max_absolute_error"] == pytest.approx(0.0)
    assert metrics["interpolation"].startswith("linear")
    assert "time_weighted" in metrics


def test_cutoff_frequency_error():
    errors = cutoff_frequency_error(159.148, 159.154943)
    assert errors["absolute_error_hz"] < 0.01
    assert errors["relative_error_percent"] < 0.01
    with pytest.raises(ValueError):
        cutoff_frequency_error(1.0, 0.0)


def test_error_near_time_constant_window():
    time_s = np.linspace(0.0, 5e-3, 501)
    simulated = np.zeros_like(time_s)
    theoretical = np.zeros_like(time_s)
    metrics = error_near_time_constant(time_s, simulated, theoretical, 1e-3)
    assert metrics["samples_in_window"] > 0
    assert metrics["max_absolute_error"] == pytest.approx(0.0)
    with pytest.raises(ValueError):
        error_near_time_constant(time_s, simulated, theoretical, 0.0)


def test_format_metrics_skips_non_numeric():
    text = format_metrics({"rmse": 0.1, "note": "x", "count": 2})
    assert "rmse=0.1" in text and "count=2" in text and "note" not in text
