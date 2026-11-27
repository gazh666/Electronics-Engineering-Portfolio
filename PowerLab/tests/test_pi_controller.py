"""离散 PI 控制器测试（与 SPICE 行为控制律一致）。"""

from __future__ import annotations

import pytest

from control.models import ControllerConfig
from control.pi_controller import PIController


def _config(**overrides) -> ControllerConfig:
    payload = dict(kp=0.1, ki=100.0, duty_min=0.02, duty_max=0.9)
    payload.update(overrides)
    return ControllerConfig(**payload)


def test_feedforward_matches_buck_relation():
    controller = PIController(_config())
    assert controller.feedforward_duty(5.0, 12.0) == pytest.approx(5.0 / 12.0)
    controller_off = PIController(_config(feedforward_enabled=False))
    assert controller_off.feedforward_duty(5.0, 12.0) == 0.0


def test_update_returns_expected_terms_and_integrates():
    controller = PIController(_config())
    sample = controller.update(5.0, 4.0, 1e-3, vin_v=12.0)
    assert sample.error_v == pytest.approx(1.0)
    assert sample.feedforward_duty == pytest.approx(5.0 / 12.0)
    assert sample.proportional_term == pytest.approx(0.1)
    assert sample.integral_state == pytest.approx(0.0)
    assert sample.raw_duty == pytest.approx(5.0 / 12.0 + 0.1)
    assert sample.limited_duty == pytest.approx(sample.raw_duty)
    assert controller.integral_state == pytest.approx(0.1)
    assert controller.diagnostics.samples == 1


def test_duty_is_clamped_at_upper_limit():
    controller = PIController(_config(kp=10.0, ki=0.0))
    sample = controller.update(5.0, 0.0, 1e-6, vin_v=12.0)
    assert sample.raw_duty > 0.9
    assert sample.limited_duty == pytest.approx(0.9)
    assert controller.diagnostics.saturated_high_samples == 1


def test_back_calculation_limits_integral_growth():
    config = _config(kp=1.0, ki=1000.0, anti_windup="back_calculation")
    controller = PIController(config)
    for _ in range(10):
        controller.update(5.0, 1.0, 1e-3, vin_v=12.0)
    reference = PIController(_config(kp=1.0, ki=1000.0, anti_windup="none"))
    for _ in range(10):
        reference.update(5.0, 1.0, 1e-3, vin_v=12.0)
    assert reference.integral_state == pytest.approx(40.0)
    assert abs(controller.integral_state) < 10.0


def test_conditional_blocks_positive_accumulation_at_limit():
    config = _config(kp=10.0, ki=1000.0, anti_windup="conditional")
    controller = PIController(config)
    for _ in range(10):
        controller.update(5.0, 0.0, 1e-3, vin_v=12.0)
    assert controller.integral_state == pytest.approx(0.0)

def test_reset_clears_integral_state():
    controller = PIController(_config())
    controller.update(5.0, 4.0, 1e-3)
    assert controller.integral_state != 0.0
    controller.reset()
    assert controller.integral_state == 0.0
    assert controller.diagnostics.reset_count == 1


def test_invalid_dt_rejected():
    controller = PIController(_config())
    with pytest.raises(ValueError):
        controller.update(5.0, 4.0, 0.0)
