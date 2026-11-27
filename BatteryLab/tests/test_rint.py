"""Rint 模型测试。"""

from __future__ import annotations

import pytest

from battery_models.rint import (
    RintError,
    calculate_ohmic_drop,
    calculate_ohmic_loss,
    calculate_rint_voltage,
    rint_benchmark_rows,
)


@pytest.mark.parametrize(
    "current,drop,voltage,loss",
    [
        (0.0, 0.0, 3.800, 0.0),
        (0.5, 0.015, 3.785, 0.0075),
        (1.0, 0.030, 3.770, 0.030),
        (2.0, 0.060, 3.740, 0.120),
        (3.0, 0.090, 3.710, 0.270),
    ],
)
def test_rint_reference_points(current: float, drop: float, voltage: float, loss: float) -> None:
    assert calculate_ohmic_drop(current, 0.03) == pytest.approx(drop, abs=1e-12)
    assert calculate_rint_voltage(3.8, current, 0.03) == pytest.approx(voltage, abs=1e-12)
    assert calculate_ohmic_loss(current, 0.03) == pytest.approx(loss, abs=1e-12)


def test_charge_current_raises_terminal_voltage() -> None:
    voltage = calculate_rint_voltage(3.8, -1.0, 0.03)
    assert voltage > 3.8
    assert voltage == pytest.approx(3.83)


def test_zero_resistance_allows_ocv_output() -> None:
    assert calculate_rint_voltage(3.8, 5.0, 0.0) == pytest.approx(3.8)
    assert calculate_ohmic_loss(5.0, 0.0) == pytest.approx(0.0)


def test_negative_resistance_rejected() -> None:
    with pytest.raises(RintError):
        calculate_rint_voltage(3.8, 1.0, -0.03)
    with pytest.raises(RintError):
        calculate_ohmic_loss(1.0, -0.03)


def test_benchmark_rows_are_computed() -> None:
    rows = rint_benchmark_rows()
    assert len(rows) == 7
    assert rows[3]["current_a"] == pytest.approx(2.0)
    assert rows[3]["terminal_voltage_v"] == pytest.approx(3.74)
    assert any(row["mode"] == "charge" for row in rows)
