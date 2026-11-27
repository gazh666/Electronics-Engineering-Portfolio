"""OCV-SOC 反查表单元测试。"""

from __future__ import annotations

import math

import pytest

from estimation.ocv_estimator import OCVSOCTable


def _simple_table(minimum_slope: float = 0.2) -> OCVSOCTable:
    soc = [0.0, 0.25, 0.5, 0.75, 1.0]
    ocv = [3.0, 3.3, 3.6, 3.8, 4.0]
    return OCVSOCTable(soc, ocv, minimum_slope=minimum_slope)


def test_round_trip_is_exact_on_table_points():
    table = _simple_table()
    for soc in (0.0, 0.25, 0.5, 0.75, 1.0):
        estimate = table.estimate(table.voltage_at(soc))
        assert estimate.status == "VALID"
        assert math.isclose(estimate.soc, soc, abs_tol=1e-9)


def test_non_monotonic_raw_curve_uses_monotonic_envelope_and_audits():
    soc = [0.0, 0.25, 0.5, 0.75, 0.9, 0.95, 1.0]
    ocv = [3.0, 3.3, 3.6, 3.9, 4.05, 4.02, 4.10]
    table = OCVSOCTable(soc, ocv, minimum_slope=0.01)
    assert table.monotonic_indices == (5,)
    assert table.audit()["monotonic_adjusted_count"] == 1
    assert table.raw_ocv_table_v[5] == pytest.approx(4.02)
    assert table.ocv_table_v[5] == pytest.approx(4.05)


def test_low_slope_region_returns_low_observability():
    soc = [0.0, 0.5, 0.505, 1.0]
    ocv = [3.0, 3.6, 3.6005, 4.0]
    table = OCVSOCTable(soc, ocv, minimum_slope=0.2)
    estimate = table.estimate(3.6002)
    assert estimate.status == "LOW_OBSERVABILITY"
    assert estimate.soc is None
    assert estimate.local_slope_v_per_soc is not None


def test_out_of_range_never_extrapolates():
    table = _simple_table()
    assert table.estimate(2.9).status == "OUTSIDE_OCV_RANGE"
    assert table.estimate(4.1).status == "OUTSIDE_OCV_RANGE"
    assert table.estimate(float("nan")).status == "INVALID_VOLTAGE"


def test_invalid_table_raises():
    with pytest.raises(Exception):
        OCVSOCTable([0.0, 1.0], [4.0, 3.0], minimum_slope=0.2, enforce_monotonic=False)
    with pytest.raises(Exception):
        OCVSOCTable([0.0, 0.0], [3.0, 4.0], minimum_slope=0.2)
    with pytest.raises(Exception):
        OCVSOCTable([0.0, 1.0], [3.0, 4.0], minimum_slope=0.0)
