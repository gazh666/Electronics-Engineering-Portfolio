"""软启动参考电压测试。"""

from __future__ import annotations

import math

import pytest

from control.soft_start import (
    ramp_rate_v_per_s,
    soft_start_points,
    soft_start_reference,
)


def test_reference_ramps_linearly_and_saturates():
    assert soft_start_reference(0.0, 5.0, 0.002) == pytest.approx(0.0)
    assert soft_start_reference(0.001, 5.0, 0.002) == pytest.approx(2.5)
    assert soft_start_reference(0.002, 5.0, 0.002) == pytest.approx(5.0)
    assert soft_start_reference(0.01, 5.0, 0.002) == pytest.approx(5.0)
    assert soft_start_reference(-1e-3, 5.0, 0.002) == pytest.approx(0.0)


def test_disabled_or_zero_duration_starts_at_target():
    assert soft_start_reference(0.0, 5.0, 0.002, enabled=False) == pytest.approx(5.0)
    assert soft_start_reference(1e-6, 5.0, 0.0) == pytest.approx(5.0)


def test_reference_rejects_bad_parameters():
    with pytest.raises(ValueError):
        soft_start_reference(0.0, 5.0, -1e-3)
    with pytest.raises(ValueError):
        soft_start_reference(0.0, 1.0, 0.002, initial_v=1.0)


def test_points_include_ramp_and_hold():
    points = soft_start_points(5.0, 0.002, end_time_s=0.012)
    assert points[0] == (0.0, 0.0)
    assert points[1] == pytest.approx((0.002, 5.0))
    assert points[-1] == pytest.approx((0.012, 5.0))
    assert [t for t, _ in points] == sorted(t for t, _ in points)


def test_points_without_soft_start_use_finite_rise():
    points = soft_start_points(5.0, 0.0, enabled=False)
    assert points[0] == (0.0, 0.0)
    assert points[1] == pytest.approx((1e-7, 5.0))
    with_end = soft_start_points(5.0, 0.0, enabled=False, end_time_s=0.01)
    assert with_end[-1] == pytest.approx((0.01, 5.0))


def test_ramp_rate():
    assert ramp_rate_v_per_s(5.0, 0.002) == pytest.approx(2500.0)
    assert math.isinf(ramp_rate_v_per_s(5.0, 0.0))
    with pytest.raises(ValueError):
        ramp_rate_v_per_s(5.0, -1e-3)
