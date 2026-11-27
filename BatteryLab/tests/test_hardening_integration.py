"""补强模块集成测试：真实 ngspice 执行 + 平均模型 + 公共统计函数。"""

from __future__ import annotations

import numpy as np
import pytest

from circuits.spice_utils import get_solve_count, reset_solve_counter
from hardening.common import (
    compare_performance,
    efficiency_delta,
    mean_power,
    time_average,
)
from hardening.protection_physical_validation import MosfetProtectionSpec, run_conduction
from system_models.averaged_system import AveragedSystemParams, simulate_averaged_system


def test_time_average_uses_trapezoid_on_nonuniform_grid():
    time = np.array([0.0, 1.0, 3.0])
    values = np.array([0.0, 2.0, 2.0])
    expected = (0.5 * 1.0 * 2.0 + 0.5 * (2.0 + 2.0) * 2.0) / 3.0
    assert time_average(time, values) == pytest.approx(expected)


def test_time_average_rejects_decreasing_time():
    with pytest.raises(ValueError):
        time_average(np.array([0.0, 1.0, 1.0]), np.array([1.0, 2.0, 3.0]))


def test_mean_power_integrates_instantaneous_product():
    time = np.linspace(0.0, 1.0, 101)
    voltage = np.full_like(time, 10.0)
    current = np.full_like(time, 0.5)
    assert mean_power(time, voltage, current) == pytest.approx(5.0)


def test_compare_performance_reports_worse_as_negative():
    assert compare_performance(10.0, 12.0)["improvement_percent"] == pytest.approx(-20.0)
    assert compare_performance(10.0, 8.0)["improvement_percent"] == pytest.approx(20.0)


def test_compare_performance_zero_baseline_is_none():
    assert compare_performance(0.0, 1.0)["relative_change_percent"] is None


def test_efficiency_delta_reports_points_and_relative():
    result = efficiency_delta(90.0, 92.0)
    assert result["percentage_point_change"] == pytest.approx(2.0)
    assert result["relative_improvement_percent"] == pytest.approx(2.0 / 90.0 * 100.0)


def test_real_ngspice_conduction_runs_and_is_physically_sane():
    reset_solve_counter()
    rows = run_conduction(MosfetProtectionSpec())
    assert get_solve_count() >= 4, "必须实际调用 ngspice 工作点求解"
    modes = {row["mode"]: row for row in rows}
    assert set(modes) == {"on_discharge", "off_discharge_block", "on_charge", "off_charge_block"}
    on = modes["on_discharge"]
    assert 0.02 <= on["path_resistance_ohm"] <= 0.05
    assert abs(on["battery_current_a"]) > 1.0
    assert abs(modes["off_discharge_block"]["battery_current_a"]) < 1e-9
    assert abs(modes["off_charge_block"]["battery_current_a"]) < 1e-9


def test_averaged_system_reaches_target_without_divergence():
    params = AveragedSystemParams(
        input_capacitance_f=100e-6,
        output_capacitance_f=100e-6,
        inductance_h=47e-6,
        battery_resistance_ohm=0.06,
        path_resistance_ohm=0.05,
        inductor_dcr_ohm=0.05,
        mosfet_rds_on_ohm=0.02,
        diode_drop_v=0.35,
    )
    result = simulate_averaged_system(
        params,
        effective_battery_voltage_v=10.5,
        target_output_voltage_v=5.0,
        duration_s=6e-3,
        dt_s=5e-6,
        controller_dt_s=1e-5,
        soft_start_s=2e-3,
        load_profile=((0.0, 2.5),),
        initial_state=(9.6, 1.0, 4.5),
    )
    assert result["records"]
    final = result["records"][-1]["output_voltage_v"]
    assert 4.0 < final < 5.5
    assert all(np.isfinite(row["output_voltage_v"]) for row in result["records"])
