"""保护事件提取单元测试：纯波形判据，不调用 SPICE。"""

from __future__ import annotations

import numpy as np
import pytest

from hardening.protection_physical_validation import (
    ProtectionValidationError,
    find_held_current_suppression,
    first_crossing,
)


def _time(end_s: float = 20e-6, step_s: float = 0.2e-6) -> np.ndarray:
    return np.arange(0.0, end_s, step_s)


def test_threshold_reached_reports_start_and_delay():
    time = _time()
    current = np.ones_like(time)
    current[25:] = 0.0
    result = find_held_current_suppression(time, current, 4e-6, 0.05, 5e-6, 0.5e-6)
    assert result["status"] == "THRESHOLD_REACHED"
    assert result["suppression_time_s"] == pytest.approx(5e-6)
    assert result["delay_from_gate_command_s"] == pytest.approx(1e-6)


def test_requires_full_hold_time():
    time = _time()
    current = np.where((time >= 5e-6) & (time < 7e-6), 0.0, 1.0)
    result = find_held_current_suppression(time, current, 4e-6, 0.05, 5e-6, 0.5e-6)
    assert result["status"] == "NOT_REACHED"


def test_large_sample_gap_invalidates_hold_window():
    time = np.concatenate([np.arange(0.0, 6e-6, 0.2e-6), np.array([20e-6])])
    current = np.zeros(time.size)
    result = find_held_current_suppression(time, current, 4e-6, 0.05, 5e-6, 0.5e-6)
    assert result["status"] == "NOT_REACHED"


def test_gate_event_outside_waveform_raises():
    time = _time()
    current = np.ones_like(time)
    with pytest.raises(ProtectionValidationError):
        find_held_current_suppression(time, current, 1.0, 0.05, 5e-6, 0.5e-6)


def test_invalid_time_axis_raises():
    time = np.array([0.0, 1e-6, 1e-6, 2e-6])
    current = np.array([1.0, 1.0, 1.0, 1.0])
    with pytest.raises(ProtectionValidationError):
        find_held_current_suppression(time, current, 1e-6, 0.05, 5e-6, 0.5e-6)


def test_current_already_gone_before_gate_command_is_not_suppression():
    time = _time()
    gate = 6e-6
    current = np.where(time < gate, 0.0, 1.0)
    result = find_held_current_suppression(time, current, gate, 0.05, 5e-6, 0.5e-6)
    assert result["status"] == "NOT_REACHED"


def test_first_crossing_respects_direction_and_start_time():
    time = np.array([0.0, 1.0, 2.0, 3.0])
    values = np.array([5.0, 4.0, 1.0, 0.0])
    assert first_crossing(time, values, 4.0, "below") == pytest.approx(1.0)
    assert first_crossing(time, values, 4.0, "below", start_s=1.5) == pytest.approx(2.0)
    assert first_crossing(time, values, 5.5, "above") is None
