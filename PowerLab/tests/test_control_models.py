"""控制器数据模型校验测试。"""

from __future__ import annotations

import pytest

from control.models import (
    ANTI_WINDUP_METHODS,
    CARRIER_TYPES,
    CarrierConfig,
    ControllerConfig,
    ControllerDiagnostics,
    ControlSample,
    SoftStartConfig,
)


def test_controller_config_defaults_and_units():
    config = ControllerConfig(kp=0.0585, ki=117.66)
    payload = config.to_dict()
    assert payload["kp"] == pytest.approx(0.0585)
    assert payload["ki"] == pytest.approx(117.66)
    assert payload["anti_windup"] in ANTI_WINDUP_METHODS
    assert payload["model_source"] == "educational_assumption"
    assert payload["units"]["kp"] == "duty/V"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"kp": -1.0, "ki": 1.0},
        {"kp": 1.0, "ki": -1.0},
        {"kp": 1.0, "ki": 1.0, "duty_min": 0.5, "duty_max": 0.5},
        {"kp": 1.0, "ki": 1.0, "duty_max": 1.2},
        {"kp": 1.0, "ki": 1.0, "anti_windup": "magic"},
        {"kp": 1.0, "ki": 1.0, "tracking_gain": 0.0},
        {"kp": 1.0, "ki": 1.0, "vin_min_for_feedforward_v": 0.0},
    ],
)
def test_controller_config_rejects_invalid(kwargs):
    with pytest.raises(ValueError):
        ControllerConfig(**kwargs)


def test_soft_start_config_validation():
    config = SoftStartConfig(enabled=True, duration_s=0.002)
    assert config.to_dict()["duration_s"] == pytest.approx(0.002)
    with pytest.raises(ValueError):
        SoftStartConfig(duration_s=-1e-3)
    with pytest.raises(ValueError):
        SoftStartConfig(initial_reference_v=-0.1)


def test_carrier_config_period_and_validation():
    carrier = CarrierConfig(carrier_type="sine", frequency_hz=100e3)
    assert carrier.period_s == pytest.approx(10e-6)
    assert carrier.to_dict()["carrier_type"] in CARRIER_TYPES
    with pytest.raises(ValueError):
        CarrierConfig(carrier_type="triangle")
    with pytest.raises(ValueError):
        CarrierConfig(frequency_hz=0.0)
    with pytest.raises(ValueError):
        CarrierConfig(smoothing_width=0.5)
    with pytest.raises(ValueError):
        CarrierConfig(threshold=1.0)


def test_diagnostics_counts_saturation_and_integral():
    diagnostics = ControllerDiagnostics()
    sample = ControlSample(
        time_s=0.0,
        reference_v=5.0,
        feedback_v=4.0,
        error_v=1.0,
        feedforward_duty=0.4,
        proportional_term=0.06,
        integral_state=0.3,
        raw_duty=1.2,
        limited_duty=0.9,
    )
    diagnostics.record(sample, correction=-0.1)
    assert diagnostics.samples == 1
    assert diagnostics.saturated_high_samples == 1
    assert diagnostics.saturated_low_samples == 0
    assert diagnostics.maximum_abs_integral == pytest.approx(0.3)
    assert diagnostics.last_correction == pytest.approx(-0.1)
    payload = diagnostics.to_dict()
    assert payload["samples"] == 1
    assert "history" not in payload
