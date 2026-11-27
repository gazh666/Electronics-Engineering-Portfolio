"""抗积分饱和策略测试。"""

from __future__ import annotations

import pytest

from control.anti_windup import (
    back_calculation_correction,
    clamp_duty,
    conditional_integral_weight,
    integral_increment,
    saturation_direction,
)


def test_clamp_duty_bounds_and_validation():
    assert clamp_duty(1.2, 0.02, 0.9) == pytest.approx(0.9)
    assert clamp_duty(-0.5, 0.02, 0.9) == pytest.approx(0.02)
    assert clamp_duty(0.4, 0.02, 0.9) == pytest.approx(0.4)
    with pytest.raises(ValueError):
        clamp_duty(0.4, 0.9, 0.9)


def test_back_calculation_correction_sign():
    assert back_calculation_correction(2000.0, 0.9, 1.2) == pytest.approx(-600.0)
    assert back_calculation_correction(2000.0, 0.02, -0.2) == pytest.approx(440.0)


def test_conditional_weight_only_blocks_saturated_direction():
    assert conditional_integral_weight(0.95, 0.5, 0.02, 0.9) == 0.0
    assert conditional_integral_weight(0.95, -0.5, 0.02, 0.9) == 1.0
    assert conditional_integral_weight(0.0, -0.5, 0.02, 0.9) == 0.0
    assert conditional_integral_weight(0.0, 0.5, 0.02, 0.9) == 1.0
    assert conditional_integral_weight(0.5, 1.0, 0.02, 0.9) == 1.0


def test_integral_increment_none_matches_plain_euler():
    increment, correction = integral_increment(
        "none",
        ki=100.0,
        error_v=0.5,
        dt_s=1e-3,
        raw_duty=0.4,
        limited_duty=0.4,
        duty_min=0.02,
        duty_max=0.9,
        tracking_gain=2000.0,
    )
    assert increment == pytest.approx(0.05)
    assert correction == 0.0


def test_integral_increment_conditional_scales_error():
    increment, _ = integral_increment(
        "conditional",
        ki=100.0,
        error_v=0.5,
        dt_s=1e-3,
        raw_duty=0.95,
        limited_duty=0.9,
        duty_min=0.02,
        duty_max=0.9,
        tracking_gain=2000.0,
    )
    assert increment == pytest.approx(0.0)


def test_integral_increment_back_calculation_includes_correction():
    increment, correction = integral_increment(
        "back_calculation",
        ki=100.0,
        error_v=0.5,
        dt_s=1e-3,
        raw_duty=1.2,
        limited_duty=0.9,
        duty_min=0.02,
        duty_max=0.9,
        tracking_gain=2000.0,
    )
    assert correction == pytest.approx(-600.0)
    assert increment == pytest.approx((50.0 - 600.0) * 1e-3)


def test_unknown_method_and_negative_ki_rejected():
    with pytest.raises(ValueError):
        integral_increment(
            "magic",
            ki=1.0,
            error_v=0.0,
            dt_s=1e-3,
            raw_duty=0.4,
            limited_duty=0.4,
            duty_min=0.0,
            duty_max=1.0,
            tracking_gain=1.0,
        )
    with pytest.raises(ValueError):
        integral_increment(
            "none",
            ki=-1.0,
            error_v=0.0,
            dt_s=1e-3,
            raw_duty=0.4,
            limited_duty=0.4,
            duty_min=0.0,
            duty_max=1.0,
            tracking_gain=1.0,
        )


def test_saturation_direction():
    assert saturation_direction(0.95, 0.02, 0.9) == "high"
    assert saturation_direction(-0.1, 0.02, 0.9) == "low"
    assert saturation_direction(0.5, 0.02, 0.9) == "none"
