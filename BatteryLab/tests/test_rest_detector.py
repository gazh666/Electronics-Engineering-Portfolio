"""静置检测单元测试。"""

from __future__ import annotations

import pytest

from estimation.rest_detector import RestDetector, RestDetectorError


def test_rest_requires_minimum_time():
    detector = RestDetector(minimum_rest_time_s=10.0, maximum_gap_s=2.0)
    for time_s in range(0, 10):
        assert detector.update(float(time_s), 0.0) is False
    assert detector.update(10.0, 0.0) is True
    assert detector.rest_duration_s == pytest.approx(10.0)


def test_current_interrupts_rest():
    detector = RestDetector(minimum_rest_time_s=2.0)
    assert detector.update(0.0, 0.0) is False
    assert detector.update(1.0, 0.0) is False
    assert detector.update(2.0, 1.0) is False
    assert detector.rest_start_s is None
    assert detector.last_reason == "CURRENT_TOO_HIGH"


def test_data_gap_resets_rest_timer():
    detector = RestDetector(minimum_rest_time_s=10.0, maximum_gap_s=2.0)
    assert detector.update(0.0, 0.0) is False
    assert detector.update(100.0, 0.0) is False
    assert detector.rest_start_s == pytest.approx(100.0)


def test_voltage_slope_blocks_rest_until_stable():
    detector = RestDetector(
        minimum_rest_time_s=300.0,
        maximum_gap_s=2.0,
        maximum_voltage_slope_v_per_s=2e-5,
        slope_window_s=30.0,
    )
    for second in range(0, 401):
        detector.update(float(second), 0.0, voltage_v=3.5 + 1e-3 * second)
    assert detector.last_reason == "VOLTAGE_NOT_STABLE"
    assert detector.update(401.0, 0.0, voltage_v=3.9) is False
    for second in range(402, 435):
        eligible = detector.update(float(second), 0.0, voltage_v=3.9)
    assert eligible is True
    assert detector.last_reason == "VALID_REST"


def test_balancing_blocks_rest():
    detector = RestDetector(minimum_rest_time_s=1.0)
    assert detector.update(0.0, 0.0, balance_current_a=0.04) is False
    assert detector.last_reason == "BALANCING_ACTIVE"


def test_non_increasing_time_raises():
    detector = RestDetector()
    detector.update(1.0, 0.0)
    with pytest.raises(RestDetectorError):
        detector.update(1.0, 0.0)
