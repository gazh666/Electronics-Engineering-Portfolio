"""脉冲/阶跃检测与表观内阻估计。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from identification.models import IdentificationError
from identification.pulse_detector import DetectionConfig, detect_events, detect_steps_within_dynamic
from identification.resistance_estimator import (
    estimate_from_steps,
    estimate_r0,
    soc_binned_resistance,
)


def test_estimate_r0_sign_and_value():
    assert estimate_r0(3.8, 3.74, 0.0, 2.0) == pytest.approx(0.03)
    assert estimate_r0(3.8, 3.86, 0.0, -2.0) == pytest.approx(0.03)
    with pytest.raises(IdentificationError):
        estimate_r0(3.8, 3.74, 1.0, 1.05)


def test_detect_pulse_and_step_events():
    time = np.concatenate([np.arange(0, 10, 1.0), np.arange(10, 70, 1.0), np.arange(70, 190, 1.0)])
    current = np.concatenate([np.zeros(10), np.full(60, 2.0), np.zeros(120)])
    voltage = np.concatenate([np.full(10, 3.8), np.full(60, 3.74), np.full(120, 3.8)])
    events, table = detect_events(time, current, voltage, config=DetectionConfig(minimum_pulse_s=5.0))
    types = set(table["event_type"])
    assert "pulse" in types
    assert any(item.startswith("step_rest_to_discharge") for item in types)
    assert any(item.startswith("step_discharge_to_rest") for item in types)
    pulse = table[table["event_type"] == "pulse"].iloc[0]
    assert pulse["delta_current_a"] == pytest.approx(2.0)
    assert pulse["duration_s"] == pytest.approx(59.0)


def test_detect_ignores_small_steps():
    time = np.arange(0, 100, 1.0)
    current = np.zeros_like(time)
    current[50:] = 0.1
    events, table = detect_events(time, current, config=DetectionConfig(minimum_current_step_a=0.2))
    assert table.empty


def test_detect_requires_monotonic_time():
    time = np.array([0.0, 1.0, 1.0, 3.0])
    with pytest.raises(IdentificationError):
        detect_events(time, np.zeros(4))


def test_estimate_from_steps_window_recorded():
    time = np.arange(0, 20, 1.0)
    current = np.concatenate([np.zeros(5), np.full(15, 2.0)])
    voltage = np.concatenate([np.full(5, 3.8), np.full(15, 3.74)])
    frame = pd.DataFrame(
        {"time_s": time, "current_a": current, "voltage_v": voltage, "soc_reference": np.linspace(0.8, 0.7, 20)}
    )
    steps = detect_steps_within_dynamic(time, current)
    table, stats = estimate_from_steps(frame, steps, window_s=1.0)
    assert stats["valid_samples"] >= 1
    assert stats["window_s"] == 1.0
    assert stats["median_ohm"] == pytest.approx(0.03, rel=0.05)
    bins = soc_binned_resistance(table)
    assert set(bins["status"]) <= {"IDENTIFIED", "NOT_VERIFIED"}
