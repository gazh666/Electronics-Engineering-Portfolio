"""器件特性提取辅助函数测试（全部为解析函数，不调用 SPICE）。"""

from __future__ import annotations

import pytest

from analysis.device_characteristics import (
    check_device_limits,
    interpolate_value,
    linear_fit,
    temperature_trend,
    threshold_from_sqrt_fit,
)
from circuits.nonideal_config import load_validation_limits


def test_linear_fit_recovers_line():
    fit = linear_fit([1.0, 2.0, 3.0, 4.0], [3.0, 5.0, 7.0, 9.0])
    assert fit["slope"] == pytest.approx(2.0)
    assert fit["intercept"] == pytest.approx(1.0)
    assert fit["r_squared"] == pytest.approx(1.0)
    assert fit["points"] == 4


def test_linear_fit_rejects_bad_input():
    with pytest.raises(ValueError):
        linear_fit([1.0], [1.0])
    with pytest.raises(ValueError):
        linear_fit([1.0, 2.0], [1.0])


def test_interpolate_value_within_and_outside_range():
    inside = interpolate_value(2.0, [1.0, 2.0, 3.0], [10.0, 20.0, 30.0], name="test")
    assert inside["value"] == pytest.approx(20.0)
    assert inside["status"] == "ok"
    outside = interpolate_value(5.0, [1.0, 2.0, 3.0], [10.0, 20.0, 30.0], name="test")
    assert outside["value"] is None
    assert outside["status"] == "target_outside_measured_range"


def test_threshold_from_sqrt_fit_recovers_vth():
    vgs = [2.0 + 0.2 * index for index in range(31)]
    current = [(value - 2.0) ** 2 for value in vgs]
    result = threshold_from_sqrt_fit(vgs, current)
    assert result["status"] == "ok"
    assert result["threshold_v"] == pytest.approx(2.0, abs=0.05)


def test_threshold_requires_enough_points():
    with pytest.raises(ValueError):
        threshold_from_sqrt_fit([1.0, 2.0], [0.0, 1.0])
    zero = threshold_from_sqrt_fit([1.0, 2.0, 3.0, 4.0], [0.0, 0.0, 0.0, 0.0])
    assert zero["status"] == "no_positive_current"


def _limit_payload():
    return {
        "device": {
            "off_state_current_ratio_max": 1e-6,
            "rds_on_min_ohm": 1e-3,
            "rds_on_max_ohm": 0.5,
            "diode_forward_drop_min_v": 0.2,
            "diode_forward_drop_max_v": 1.5,
            "diode_reverse_current_max_a": 1e-3,
        }
    }


def test_check_device_limits_pass_and_fail():
    limits = _limit_payload()
    passed = check_device_limits(
        transfer={"on_off_current_ratio": 1e9},
        rds={"rds_on_ohm": 0.02},
        off_state={},
        diode_forward={"voltage_drops": {"2.0": {"forward_voltage_v": 0.45}}},
        diode_reverse={"max_abs_leakage_a": 1e-6},
        limits=limits,
    )
    assert passed["passed"] is True

    failed = check_device_limits(
        transfer={"on_off_current_ratio": 10.0},
        rds={"rds_on_ohm": 2.0},
        off_state={},
        diode_forward={"voltage_drops": {"2.0": {"forward_voltage_v": 0.05}}},
        diode_reverse={"max_abs_leakage_a": 1.0},
        limits=limits,
    )
    assert failed["passed"] is False
    assert failed["checks"]["rds_on"]["passed"] is False


def test_check_device_limits_requires_limit_keys():
    with pytest.raises(ValueError):
        check_device_limits(
            transfer={},
            rds={},
            off_state={},
            diode_forward={},
            diode_reverse={},
            limits={"device": {}},
        )


def test_validation_config_contains_device_limits():
    limits = load_validation_limits()
    assert limits["device"]["rds_on_max_ohm"] > limits["device"]["rds_on_min_ohm"]


def test_temperature_trend_reports_change_only():
    trend = temperature_trend(
        [
            {"temperature_c": 75.0, "efficiency": 92.2},
            {"temperature_c": 25.0, "efficiency": 92.9},
        ],
        "efficiency",
    )
    assert trend["status"] == "ok"
    assert trend["values"][0][0] == 25.0
    assert trend["change"] == pytest.approx(-0.7)
    assert temperature_trend([{"temperature_c": 25.0, "x": 1.0}], "x")["status"] == (
        "insufficient_points"
    )
