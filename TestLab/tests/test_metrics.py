"""工程指标公式单元测试：用手工计算结果校验。"""

import math

import pytest

from analysis.metrics import (
    PerformanceMetrics,
    absolute_voltage_error_percent,
    calculate_metrics,
    efficiency_anomaly,
    efficiency_percent,
    input_power,
    line_regulation_mv_per_v,
    line_regulation_percent,
    line_regulation_span_percent,
    load_regulation_percent,
    missing_fields,
    output_power,
    pass_rate_percent,
    power_loss_watts,
    power_watts,
    signed_voltage_error_percent,
    voltage_absolute_error,
    voltage_error_percent,
    voltage_error_volts,
)


def test_input_and_output_power():
    # Pin = 12 V × 0.5 A = 6 W
    assert input_power(12.0, 0.5) == pytest.approx(6.0)
    # Pout = 4.98 V × 1 A = 4.98 W
    assert output_power(4.98, 1.0) == pytest.approx(4.98)


def test_efficiency_percent_hand_calculation():
    # Pin = 12 × 0.5 = 6 W；Pout = 4.98 × 1.0 = 4.98 W
    # 4.98 / 6 × 100 = 83 %
    assert efficiency_percent(12.0, 0.5, 4.98, 1.0) == pytest.approx(83.0)


def test_efficiency_is_none_when_input_power_is_zero():
    assert efficiency_percent(12.0, 0.0, 0.0, 0.0) is None


def test_efficiency_above_100_is_kept_and_flagged():
    # Pin = 5 × 1 = 5 W；Pout = 5 × 1.2 = 6 W -> 120 %
    value = efficiency_percent(5.0, 1.0, 5.0, 1.2)
    assert value == pytest.approx(120.0)

    message = efficiency_anomaly(value)
    assert message is not None
    assert "120.000%" in message
    assert "数据异常" in message


def test_normal_efficiency_has_no_anomaly():
    assert efficiency_anomaly(90.0) is None
    assert efficiency_anomaly(None) is None


def test_voltage_absolute_error():
    # |5.05 - 5.00| = 0.05 V
    assert voltage_absolute_error(5.05, 5.0) == pytest.approx(0.05)
    # 误差与方向无关
    assert voltage_absolute_error(4.95, 5.0) == pytest.approx(0.05)


def test_voltage_relative_error_percent():
    # |5.05 - 5.00| / 5.00 × 100 = 1 %
    assert voltage_error_percent(5.05, 5.0) == pytest.approx(1.0)
    assert voltage_error_percent(4.90, 5.0) == pytest.approx(2.0)


def test_invalid_voltage_reference_rejected():
    with pytest.raises(ValueError):
        voltage_error_percent(5.0, 0.0)
    with pytest.raises(ValueError):
        voltage_error_percent(5.0, -1.0)
    with pytest.raises(ValueError):
        voltage_error_percent(math.nan, 5.0)


def test_load_regulation_uses_nominal_voltage_as_denominator():
    # |5.00 - 4.99| / 5.00 × 100 = 0.2 %
    assert load_regulation_percent(5.00, 4.99, 5.0) == pytest.approx(0.2)

    # 空载 5.1 V、满载 5.0 V、标称 5.0 V：
    # 本定义 0.1/5.0 = 2 %；若用空载电压作分母则为 0.1/5.1 = 1.96 %
    assert load_regulation_percent(5.1, 5.0, 5.0) == pytest.approx(2.0)


def test_load_regulation_rejects_invalid_nominal_voltage():
    with pytest.raises(ValueError):
        load_regulation_percent(5.0, 4.9, 0.0)


def test_line_regulation_percent():
    # |5.05 - 5.00| / 5.00 × 100 = 1 %
    assert line_regulation_percent(5.0, 5.05, 9.0, 16.0) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        line_regulation_percent(5.0, 5.05, 12.0, 12.0)


def test_pass_rate_excludes_skipped_cases():
    statuses = ["PASS", "PASS", "FAIL", "ERROR", "SKIP", "SKIP"]
    # 2 / (2 + 1 + 1) × 100 = 50 %
    assert pass_rate_percent(statuses) == pytest.approx(50.0)


def test_pass_rate_without_executed_cases_is_none():
    assert pass_rate_percent([]) is None
    assert pass_rate_percent(["SKIP"]) is None


def test_pass_rate_rejects_unknown_status():
    with pytest.raises(ValueError):
        pass_rate_percent(["PASS", "UNKNOWN"])


def test_missing_fields_detects_absent_none_nan_and_blank():
    record = {
        "vin": 12.0,
        "iin": None,
        "vout": math.nan,
        "iout": "",
        "efficiency": None,
    }
    missing = missing_fields(
        record,
        ["vin", "iin", "vout", "iout", "pin", "efficiency"],
        allow_none=("efficiency",),
    )
    assert missing == ["iin", "vout", "iout", "pin"]


def test_power_rejects_negative_and_non_finite_values():
    with pytest.raises(ValueError):
        input_power(-1.0, 1.0)
    with pytest.raises(ValueError):
        output_power(math.nan, 1.0)
    with pytest.raises(ValueError):
        efficiency_percent(math.inf, 1.0, 5.0, 1.0)


# ---------------------------------------------------------------------------
# 第六阶段：统一指标接口
# ---------------------------------------------------------------------------


def test_power_watts_matches_manual_calculation():
    assert power_watts(5.0, 2.0) == pytest.approx(10.0)


def test_signed_voltage_error_is_directional():
    assert voltage_error_volts(4.98, 5.0) == pytest.approx(-0.02)
    assert signed_voltage_error_percent(4.98, 5.0) == pytest.approx(-0.4)
    assert signed_voltage_error_percent(5.05, 5.0) == pytest.approx(1.0)
    assert absolute_voltage_error_percent(4.90, 5.0) == pytest.approx(2.0)


def test_voltage_error_rejects_zero_or_negative_reference():
    with pytest.raises(ValueError):
        signed_voltage_error_percent(5.0, 0.0)
    with pytest.raises(ValueError):
        signed_voltage_error_percent(5.0, -1.0)


def test_power_loss_can_be_negative_for_quality_detection():
    assert power_loss_watts(12.0, 1.0, 5.0, 1.0) == pytest.approx(7.0)
    assert power_loss_watts(10.0, 1.0, 12.0, 1.0) == pytest.approx(-2.0)


def test_line_regulation_span_and_mv_per_v():
    assert line_regulation_span_percent([4.98, 4.98, 4.98], 5.0) == pytest.approx(0.0)
    assert line_regulation_span_percent([4.97, 5.00], 5.0) == pytest.approx(0.6)
    assert line_regulation_mv_per_v(9.0, 16.0, 4.97, 5.00) == pytest.approx(
        30.0 / 7.0
    )


def test_line_regulation_span_requires_two_samples():
    with pytest.raises(ValueError):
        line_regulation_span_percent([4.98], 5.0)


def test_calculate_metrics_matches_manual_values():
    metrics = calculate_metrics(12.0, 0.4611111111, 4.98, 1.0, 5.0)
    assert isinstance(metrics, PerformanceMetrics)
    assert metrics.input_power_w == pytest.approx(5.5333333333, rel=1e-6)
    assert metrics.output_power_w == pytest.approx(4.98)
    assert metrics.power_loss_w == pytest.approx(0.5533333333, rel=1e-6)
    assert metrics.efficiency_percent == pytest.approx(90.0, rel=1e-6)
    assert metrics.voltage_error_v == pytest.approx(-0.02)
    assert metrics.voltage_error_percent == pytest.approx(-0.4)
    assert metrics.absolute_voltage_error_percent == pytest.approx(0.4)


def test_metrics_reject_boolean_inputs():
    with pytest.raises(ValueError):
        power_watts(True, 1.0)
    with pytest.raises(ValueError):
        voltage_error_volts(5.0, True)
