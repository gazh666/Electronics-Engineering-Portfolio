"""零点/两点校准测试（Task 25/29/36）。"""

from __future__ import annotations

import pytest

from sensing.calibration import (
    CalibrationError,
    apply_calibration,
    calibration_error_report,
    fit_two_point_calibration,
    fit_zero_calibration,
    identity_calibration,
)


def test_identity_calibration():
    model = identity_calibration()
    assert model.apply(1.234) == pytest.approx(1.234)
    assert model.is_identity


def test_zero_calibration_removes_offset():
    model = fit_zero_calibration(0.05)
    assert model.apply(0.05) == pytest.approx(0.0, abs=1e-15)
    assert model.apply(1.05) == pytest.approx(1.0, abs=1e-15)
    assert model.kind == "zero"


def test_two_point_calibration_recovers_affine_map():
    model = fit_two_point_calibration(0.0, 0.1, 10.0, 10.1)
    assert model.gain == pytest.approx(1.0, rel=1e-12)
    assert model.offset == pytest.approx(0.1, rel=1e-12)
    assert model.apply(5.1) == pytest.approx(5.0, abs=1e-12)


def test_two_point_calibration_independent_validation():
    model = fit_two_point_calibration(0.0, 0.02, 5.0, 5.02)
    # 验证点未参与拟合
    assert model.apply(5.02) == pytest.approx(5.0, abs=1e-12)
    assert model.apply(2.52) == pytest.approx(2.5, abs=1e-12)


def test_forward_and_apply_are_inverse():
    model = fit_two_point_calibration(-2.0, -1.99, 2.0, 2.01)
    for value in (-2.0, -0.5, 0.0, 1.5, 2.0):
        assert model.apply(model.forward(value)) == pytest.approx(value, abs=1e-12)


def test_duplicate_reference_points_rejected():
    with pytest.raises(CalibrationError):
        fit_two_point_calibration(1.0, 1.0, 1.0, 2.0)


def test_zero_slope_rejected():
    with pytest.raises(CalibrationError):
        fit_two_point_calibration(0.0, 1.0, 1.0, 1.0)


def test_error_report_metrics():
    report = calibration_error_report([0.0, 1.0], [0.1, 0.8], identity_calibration())
    assert report["count"] == 2.0
    assert report["mae"] == pytest.approx(0.15)
    assert report["max_abs_error"] == pytest.approx(0.2)
    assert report["rmse"] == pytest.approx(0.15811388300841894)


def test_apply_calibration_matches_model():
    model = fit_two_point_calibration(0.0, 0.5, 10.0, 10.5)
    assert apply_calibration(5.5, model.gain, model.offset) == pytest.approx(5.0, abs=1e-12)
