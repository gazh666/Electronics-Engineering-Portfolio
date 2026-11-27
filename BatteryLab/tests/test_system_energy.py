"""能量守恒、损耗分解与瞬态指标测试。"""

from __future__ import annotations

import numpy as np
import pytest

from analysis.system_transient_metrics import find_settling_time, step_metrics
from validation.system_energy_validator import loss_breakdown, trapezoid_energy, validate_energy


def test_trapezoid_constant_power() -> None:
    time_s = np.linspace(0.0, 2.0, 101)
    power = np.full_like(time_s, 5.0)
    assert trapezoid_energy(time_s, power) == pytest.approx(10.0)


def test_trapezoid_rejects_bad_shapes() -> None:
    with pytest.raises(ValueError):
        trapezoid_energy([0.0, 1.0], [1.0])
    with pytest.raises(ValueError):
        trapezoid_energy([0.0], [1.0])


def consistent_waveform():
    time_s = np.linspace(0.0, 10e-3, 1001)
    ibat = np.full_like(time_s, 1.0)
    path = 0.05
    vbat = np.full_like(time_s, 10.5)
    vin = vbat - ibat * path
    iin = ibat.copy()
    vout = np.full_like(time_s, 5.0)
    iout = np.full_like(time_s, 1.8)
    return time_s, vbat, ibat, vin, iin, vout, iout


def test_energy_balance_closes_for_consistent_data() -> None:
    time_s, vbat, ibat, vin, iin, vout, iout = consistent_waveform()
    result = validate_energy(
        time_s=time_s, battery_voltage_v=vbat, battery_current_a=ibat,
        converter_input_voltage_v=vin, converter_input_current_a=iin,
        output_voltage_v=vout, load_current_a=iout,
        path_resistance_ohm=0.05, steady_window_start_s=0.0,
    )
    assert result["boundary_a_residual_percent"] < 0.01
    assert result["boundary_a_status"] == "PASS"
    assert result["energy_balance_verified"] is True


def test_energy_balance_detects_injected_loss() -> None:
    time_s, vbat, ibat, vin, iin, vout, iout = consistent_waveform()
    vin = vin - 0.4  # 人为制造 0.4 V 未解释压降
    result = validate_energy(
        time_s=time_s, battery_voltage_v=vbat, battery_current_a=ibat,
        converter_input_voltage_v=vin, converter_input_current_a=iin,
        output_voltage_v=vout, load_current_a=iout,
        path_resistance_ohm=0.05, steady_window_start_s=0.0,
        residual_limit_percent=1.0,
    )
    assert result["boundary_a_status"] == "FAIL"


def test_loss_breakdown_sums_to_converter_input() -> None:
    time_s, vbat, ibat, vin, iin, vout, iout = consistent_waveform()
    breakdown = loss_breakdown(
        time_s=time_s, battery_voltage_v=vbat, battery_current_a=ibat,
        converter_input_voltage_v=vin, converter_input_current_a=iin,
        output_voltage_v=vout, load_current_a=iout,
        path_resistance_ohm=0.05, battery_internal_resistance_ohm=0.2,
        steady_window_start_s=0.0,
    )
    # 窗口 10 ms、1 A、0.05 Ω -> ∫i²R dt = 5e-4 J
    assert breakdown["protection_path_loss_j"] == pytest.approx(5e-4, rel=1e-3)
    assert breakdown["converter_loss_j"] > 0


def test_settling_time_last_exit() -> None:
    time_s = np.linspace(0, 0.01, 1001)
    values = 5.0 + 0.5 * np.exp(-time_s / 1e-3) * np.cos(2 * np.pi * 2000 * time_s)
    settling = find_settling_time(time_s, values, 5.0, 0.01, hold_time_s=1e-4)
    assert settling is not None
    assert settling == pytest.approx(0.004, abs=0.0015)


def test_settling_time_returns_none_when_never_inside() -> None:
    time_s = np.linspace(0, 0.001, 101)
    assert find_settling_time(time_s, np.full_like(time_s, 6.0), 5.0, 0.01) is None


def test_settling_time_requires_hold_window() -> None:
    time_s = np.linspace(0, 0.001, 101)
    values = np.where(time_s > 0.0009, 5.0, 5.5)
    assert find_settling_time(time_s, values, 5.0, 0.01, hold_time_s=5e-4) is None


def test_step_metrics_reports_droop() -> None:
    time_s = np.linspace(0, 0.01, 5001)
    values = np.where(time_s < 0.005, 5.0, 4.7)
    metrics = step_metrics(time_s, values, step_time_s=0.005, post_window_s=0.002, nominal_v=4.7)
    assert metrics["status"] == "OK"
    assert metrics["deviation_v"] == pytest.approx(0.3, abs=1e-6)
