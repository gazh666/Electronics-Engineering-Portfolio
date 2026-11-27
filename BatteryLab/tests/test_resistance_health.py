"""内阻健康指标单元测试。"""

from __future__ import annotations

import math

import pytest

from health.resistance_health import (
    ResistanceCondition,
    ResistanceHealthError,
    compare_resistance_conditions,
    pulse_resistance_ohm,
    resistance_growth_percent,
)


def test_growth_percent():
    assert math.isclose(resistance_growth_percent(0.09, 0.075), 20.0, abs_tol=1e-12)


def test_pulse_resistance_sign_convention():
    # 放电阶跃：电流 +1 A，电压下降 75 mV -> 0.075 Ω
    resistance = pulse_resistance_ohm(4.0, 3.925, 0.0, 1.0)
    assert math.isclose(resistance, 0.075, abs_tol=1e-12)


def test_condition_comparison_detects_mismatch():
    reference = ResistanceCondition("SP2", soc=0.5, temperature_c=25.0, current_direction="discharge",
                                    pulse_amplitude_a=1.0, window_s=1.0)
    same = compare_resistance_conditions(reference, reference)
    assert same["status"] == "COMPARABLE"
    different_temperature = ResistanceCondition(
        "SP2", soc=0.5, temperature_c=35.0, current_direction="discharge", pulse_amplitude_a=1.0, window_s=1.0
    )
    result = compare_resistance_conditions(reference, different_temperature)
    assert result["status"] == "CONDITION_MISMATCH"
    assert "TEMPERATURE_MISMATCH" in result["reasons"]


def test_invalid_inputs_raise():
    with pytest.raises(ResistanceHealthError):
        resistance_growth_percent(0.0, 0.075)
    with pytest.raises(ResistanceHealthError):
        pulse_resistance_ohm(4.0, 3.9, 1.0, 1.0)
