"""容量积分与完整放电工步提取。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from identification.capacity_estimator import (
    compare_capacity_results,
    cumulative_charge_ah,
    estimate_capacity_from_frame,
    integrate_charge_ah,
)
from identification.models import IdentificationError


def _frame(current_a=1.0, duration_s=3600.0, dt_s=1.0, step=6.0, recorded=1.0):
    time = np.arange(0.0, duration_s + dt_s, dt_s)
    current = np.full(time.size, current_a)
    voltage = np.linspace(4.0, 3.2, time.size)
    discharge_counter = recorded * (time - time[0]) / (time[-1] - time[0])
    return pd.DataFrame(
        {
            "time_s": time,
            "current_a": current,
            "voltage_v": voltage,
            "step_index": step,
            "discharge_capacity_ah": discharge_counter,
            "source_file": "synthetic.xls",
            "source_sheet": "Channel_1",
        }
    )


def test_zoh_integration_exact():
    time = np.array([0.0, 10.0, 20.0, 30.0])
    current = np.array([2.0, 2.0, 2.0, 2.0])
    assert integrate_charge_ah(time, current) == pytest.approx(2.0 * 30.0 / 3600.0)


def test_cumulative_monotonic_and_length():
    frame = _frame()
    cumulative = cumulative_charge_ah(frame["time_s"], frame["current_a"])
    assert cumulative.size == len(frame)
    assert cumulative[0] == 0.0
    assert np.all(np.diff(cumulative) >= 0.0)


def test_estimate_capacity_matches_recorded():
    frame = _frame(duration_s=3600.0, recorded=1.0)
    result = estimate_capacity_from_frame(frame, dataset_id="synthetic", rated_capacity_ah=2.0)
    assert result.integrated_capacity_ah == pytest.approx(1.0, rel=1e-9)
    assert result.recorded_capacity_ah == pytest.approx(1.0)
    assert result.capacity_difference_ah == pytest.approx(0.0, abs=1e-9)
    assert result.points == len(frame)


def test_estimate_capacity_rejects_gap():
    frame = _frame()
    frame = frame[frame["time_s"] != 1000.0].reset_index(drop=True)
    with pytest.raises(IdentificationError):
        estimate_capacity_from_frame(frame, dataset_id="gap", maximum_gap_s=1.5)


def test_duplicate_time_rejected():
    frame = _frame()
    frame.loc[5, "time_s"] = frame.loc[4, "time_s"]
    with pytest.raises(IdentificationError):
        integrate_charge_ah(frame["time_s"], frame["current_a"])


def test_compare_capacity_results():
    first = estimate_capacity_from_frame(_frame(), dataset_id="a", rated_capacity_ah=2.0)
    second = estimate_capacity_from_frame(_frame(current_a=0.5), dataset_id="b", rated_capacity_ah=2.0)
    summary = compare_capacity_results([first, second])
    assert summary["count"] == 2
    assert summary["spread_ah"] == pytest.approx(0.5, rel=1e-6)
    assert summary["spread_percent_of_mean"] > 0
