"""模型误差计算测试。"""

from __future__ import annotations

import numpy as np
import pytest

from analysis.model_comparison import (
    ComparisonError,
    align_series,
    compare_frames,
    error_metrics,
    time_weighted_metrics,
)


def test_error_metrics_known_values() -> None:
    reference = [3.0, 3.0, 3.0]
    model = [3.0, 4.0, 1.0]
    metrics = error_metrics(reference, model, reference_name="theory")
    assert metrics["mae_v"] == pytest.approx(1.0)
    assert metrics["rmse_v"] == pytest.approx(np.sqrt(5.0 / 3.0))
    assert metrics["max_abs_error_v"] == pytest.approx(2.0)
    assert metrics["mean_signed_error_v"] == pytest.approx(-1.0 / 3.0)
    assert metrics["reference"] == "theory"


def test_time_weighted_metrics() -> None:
    time = [0.0, 1.0, 3.0]
    reference = [0.0, 0.0, 0.0]
    model = [1.0, 1.0, 3.0]
    metrics = time_weighted_metrics(time, reference, model)
    assert metrics["weighted_mae_v"] == pytest.approx((1.0 * 1.0 + 2.0 * 1.0) / 3.0)
    assert metrics["weighted_rmse_v"] == pytest.approx(np.sqrt((1.0 + 2.0) / 3.0))


def test_alignment_does_not_extrapolate() -> None:
    time_s, reference, model = align_series(
        [0.0, 1.0, 2.0],
        [3.0, 3.1, 3.2],
        [0.0, 0.5, 1.0],
        [3.0, 3.05, 3.1],
    )
    assert time_s[-1] == pytest.approx(1.0)
    assert model[-1] == pytest.approx(3.1)


def test_alignment_exclusion_window() -> None:
    time_s, _, _ = align_series(
        [0.0, 10.0, 10.05, 20.0],
        [3.8, 3.74, 3.74, 3.74],
        [0.0, 10.0, 10.05, 20.0],
        [3.8, 3.74, 3.74, 3.74],
        exclude_times_s=(10.0,),
        exclude_window_s=0.1,
    )
    assert set(time_s.tolist()) == {0.0, 20.0}


def test_alignment_rejects_no_overlap() -> None:
    with pytest.raises(ComparisonError):
        align_series([0.0, 1.0], [1.0, 1.0], [5.0, 6.0], [1.0, 1.0])


def test_compare_frames_reports_window() -> None:
    import pandas as pd

    reference = pd.DataFrame({"time_s": [0.0, 1.0, 2.0], "terminal_voltage_v": [3.8, 3.7, 3.6]})
    model = pd.DataFrame({"time_s": [0.0, 1.0, 2.0], "terminal_voltage_v": [3.8, 3.7005, 3.5995]})
    metrics = compare_frames(reference, model, reference_name="spice")
    assert metrics["max_abs_error_v"] == pytest.approx(0.0005)
    assert metrics["aligned_points"] == 3
    assert metrics["window_start_s"] == pytest.approx(0.0)
