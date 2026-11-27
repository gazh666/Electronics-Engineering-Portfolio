"""第六阶段控制律：条件积分冻结、反计算与离散稳定性。"""

from __future__ import annotations

import pytest

from charging.anti_windup import (
    back_calculation_term,
    conditional_integral_rate,
    integral_rate,
    is_frozen,
    is_stable_timestep,
)
from charging.pi_controller import PIController


def test_freeze_only_when_saturation_matches_error_sign():
    assert is_frozen(unsaturated=1.2, saturated=1.0, error=0.1)
    assert is_frozen(unsaturated=-0.2, saturated=0.0, error=-0.1)
    assert not is_frozen(unsaturated=1.2, saturated=1.0, error=-0.1)
    assert not is_frozen(unsaturated=0.4, saturated=1.0, error=0.1)


def test_conditional_rate_freezes_integral_in_saturation():
    assert conditional_integral_rate(50.0, 0.2, 1000.0, 1.0, 1.2) == 0.0


def test_conditional_rate_keeps_back_calculation_when_error_reverses():
    value = conditional_integral_rate(50.0, -0.2, 1000.0, 1.0, 1.2)
    expected = 50.0 * -0.2 + 1000.0 * (1.0 - 1.2)
    assert value == pytest.approx(expected)


def test_pi_step_freezes_integral_when_saturated_same_direction():
    controller = PIController(kp=0.025, ki=50.0, kaw=1000.0, integral=0.5)
    controller.step(error=0.2, dt_s=1e-5, lower=0.0, upper=0.5)
    assert controller.integral == pytest.approx(0.5)
    assert controller.saturated


def test_pi_tracks_unsaturated_error():
    controller = PIController(kp=0.025, ki=50.0, kaw=0.0)
    output = controller.step(error=0.1, dt_s=1e-3, lower=0.0, upper=1.0)
    assert output == pytest.approx(0.0025)
    assert controller.integral == pytest.approx(0.005)


def test_back_calculation_direction():
    assert back_calculation_term(1000.0, 1.0, 1.2) == pytest.approx(-200.0)
    assert integral_rate(50.0, 0.1, 0.0, 1.0, 1.0) == pytest.approx(5.0)


def test_back_calculation_stability_guard():
    assert is_stable_timestep(50.0, 1e-3)
    assert not is_stable_timestep(5000.0, 1e-3)
    with pytest.raises(ValueError):
        is_stable_timestep(50.0, 0.0)
