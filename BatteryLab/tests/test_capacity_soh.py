"""容量型 SOH 单元测试。"""

from __future__ import annotations

import math

import pytest

from health.capacity_soh import SOHValidationError, calculate_capacity_soh


def test_soh_and_loss():
    health = calculate_capacity_soh(1.8, 2.0)
    assert math.isclose(health.soh_percent, 90.0, abs_tol=1e-12)
    assert math.isclose(health.capacity_loss_percent, 10.0, abs_tol=1e-12)


def test_above_100_percent_is_not_clipped():
    health = calculate_capacity_soh(2.1, 2.0)
    assert health.soh_percent > 100.0
    assert math.isclose(health.soh_percent, 105.0, abs_tol=1e-12)


def test_invalid_inputs_raise():
    with pytest.raises(SOHValidationError):
        calculate_capacity_soh(2.0, 0.0)
    with pytest.raises(SOHValidationError):
        calculate_capacity_soh(-0.1, 2.0)
    with pytest.raises(SOHValidationError):
        calculate_capacity_soh(float("nan"), 2.0)
