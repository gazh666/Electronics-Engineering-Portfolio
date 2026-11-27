"""瞬态指标测试：周期均值、恢复时间与事件统计。"""

from __future__ import annotations

import math

import numpy as np
import pytest

from analysis.transient_metrics import (
    DisturbanceEvent,
    analyze_event,
    analyze_events,
    cycle_mean_waveform,
    find_recovery_time,
    summarize_event_metrics,
)


def _step_response(drop: float = 0.3, tau_s: float = 2e-3):
    """事件后先跌落 ``drop``，再按 ``tau_s`` 指数恢复。"""
    time = np.arange(0.0, 20e-3, 1e-6)
    signal = np.where(
        time < 10e-3,
        5.0,
        5.0 - drop * np.exp(-(time - 10e-3) / tau_s),
    )
    return time, signal


def test_cycle_mean_waveform_constant_signal():
    time = np.arange(0.0, 1e-3, 1e-8)
    centers, means = cycle_mean_waveform(time, np.full_like(time, 5.0), 10e-6)
    assert centers.size == pytest.approx(100, abs=2)
    assert np.allclose(means, 5.0)


def test_cycle_mean_waveform_validates_period_and_series():
    time = np.arange(0.0, 1e-3, 1e-7)
    with pytest.raises(ValueError):
        cycle_mean_waveform(time, np.ones_like(time), 0.0)
    with pytest.raises(ValueError):
        cycle_mean_waveform(time[:-1], np.ones_like(time), 10e-6)


def test_find_recovery_time_strict_for_decaying_droop():
    time, signal = _step_response()
    recovery = find_recovery_time(
        time,
        signal,
        event_end_s=10e-3,
        target_v=5.0,
        tolerance_v=0.05,
        period_s=10e-6,
        hold_cycles=20,
        mode="strict",
    )
    assert recovery.status == "OK"
    assert 13e-3 < recovery.recovery_time_s < 15e-3


def test_find_recovery_time_reports_not_recovered():
    time, signal = _step_response(drop=0.5, tau_s=50e-3)
    recovery = find_recovery_time(
        time,
        signal,
        event_end_s=10e-3,
        target_v=5.0,
        tolerance_v=0.05,
        period_s=10e-6,
        hold_cycles=20,
    )
    assert recovery.status == "NOT_RECOVERED"
    assert math.isnan(recovery.recovery_time_s)
    assert recovery.to_dict()["recovery_time_s"] is None


def test_find_recovery_time_insufficient_data():
    time, signal = _step_response()
    recovery = find_recovery_time(
        time[:100],
        signal[:100],
        event_end_s=10e-3,
        target_v=5.0,
        tolerance_v=0.05,
        period_s=10e-6,
    )
    assert recovery.status == "INSUFFICIENT_DATA"


def test_find_recovery_time_rejects_bad_mode():
    time, signal = _step_response()
    with pytest.raises(ValueError):
        find_recovery_time(
            time,
            signal,
            event_end_s=10e-3,
            target_v=5.0,
            tolerance_v=0.05,
            period_s=10e-6,
            mode="magic",
        )


def test_analyze_event_metrics_for_droop():
    time, signal = _step_response()
    event = DisturbanceEvent(
        event_id="load_step_0",
        event_type="load_step",
        start_time_s=10e-3,
        end_time_s=10e-3 + 20e-6,
        initial_value=1.0,
        final_value=2.0,
    )
    metrics = analyze_event(
        time,
        signal,
        event,
        target_v=5.0,
        tolerance_v=0.05,
        period_s=10e-6,
        pre_window_s=1e-3,
        data_source="synthetic_test",
    )
    assert metrics["pre_event_mean_v"] == pytest.approx(5.0)
    assert metrics["post_event_min_v"] == pytest.approx(4.7, abs=5e-3)
    assert metrics["maximum_absolute_deviation_v"] == pytest.approx(0.3, abs=5e-3)
    assert metrics["droop_v"] == pytest.approx(0.3, abs=5e-3)
    assert metrics["final_mean_v"] == pytest.approx(5.0, abs=5e-3)
    assert metrics["data_source"] == "synthetic_test"
    assert metrics["recovery_strict"]["status"] == "OK"


def test_analyze_events_and_summary_table():
    time, signal = _step_response()
    events = [
        DisturbanceEvent("e0", "load_step", 10e-3, 10.02e-3, 1.0, 2.0),
    ]
    metrics = analyze_events(
        time,
        signal,
        events,
        target_v=5.0,
        tolerance_v=0.05,
        period_s=10e-6,
    )
    assert len(metrics) == 1
    frame = summarize_event_metrics(metrics)
    assert "maximum_absolute_deviation_v" in frame.columns
    assert frame.iloc[0]["event_id"] == "e0"


def test_event_validation():
    with pytest.raises(ValueError):
        DisturbanceEvent("", "load_step", 1e-3, 1.1e-3, 1.0, 2.0)
    with pytest.raises(ValueError):
        DisturbanceEvent("e", "load_step", 2e-3, 1e-3, 1.0, 2.0)
    event = DisturbanceEvent("e", "load_step", 1e-3, 1.1e-3, 1.0, 2.0)
    assert event.step_size == pytest.approx(1.0)
