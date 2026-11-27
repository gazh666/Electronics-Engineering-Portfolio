"""系统候选验证单元测试：平均模型统计口径与 LC 常量。"""

from __future__ import annotations

import pytest

from hardening.system_candidate_validation import (
    BASELINE_CONTROLLER,
    BASELINE_LC,
    OPTIMIZED_LC,
    SystemValidationError,
    _average_metrics,
)


def _records(vout_after: float = 5.0, step_s: float = 6e-3):
    rows = []
    time = 0.0
    while time < 9e-3:
        value = 5.0 if time < step_s else vout_after
        rows.append({
            "time_s": time,
            "output_voltage_v": value,
            "inductor_current_a": 2.5,
            "load_current_a": 2.0,
            "battery_current_a": 1.0,
            "input_voltage_v": 10.0,
        })
        time += 1e-5
    return rows


def test_average_metrics_uses_instantaneous_power_ratio():
    metrics = _average_metrics(_records(), 6e-3, 5.0)
    assert metrics["steady_voltage_v"] == pytest.approx(5.0)
    assert metrics["efficiency_percent"] == pytest.approx(100.0)


def test_average_metrics_reports_step_deviation():
    metrics = _average_metrics(_records(vout_after=5.4), 6e-3, 5.0)
    assert metrics["step_deviation_v"] == pytest.approx(0.4, rel=1e-6)
    assert metrics["recovered"] is False


def test_average_metrics_requires_enough_window_samples():
    with pytest.raises(SystemValidationError):
        _average_metrics(_records()[:3], 6e-3, 5.0)


def test_lc_candidates_registered_as_documented():
    assert BASELINE_LC["inductance_h"] == pytest.approx(47e-6)
    assert BASELINE_LC["capacitance_f"] == pytest.approx(100e-6)
    assert OPTIMIZED_LC["inductance_h"] == pytest.approx(68e-6)
    assert OPTIMIZED_LC["capacitance_f"] == pytest.approx(330e-6)
    assert OPTIMIZED_LC["inductor_dcr_ohm"] < BASELINE_LC["inductor_dcr_ohm"]
    assert OPTIMIZED_LC["capacitor_esr_ohm"] < BASELINE_LC["capacitor_esr_ohm"]
    assert BASELINE_CONTROLLER["kp"] == pytest.approx(0.0585)
