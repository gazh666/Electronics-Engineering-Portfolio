"""第六阶段配置：充电器参数、保护协调、20 工况与资源预算。"""

from __future__ import annotations

import pytest

from charging.config import (
    ChargerConfigError,
    load_charger_config,
    load_charging_cases,
    load_controller_config,
    load_tuning_grid,
)
from circuits.charger_spice_controller import MINIMUM_RELIABLE_STEP_S
from simulations.charging_experiments import method_counts


def test_charger_config_validates_against_protection():
    charger = load_charger_config().validate()
    report = charger.validate_against_protection()
    assert report["per_cell_cv_v"] == pytest.approx(charger.charging.constant_voltage_v / 3)
    assert report["per_cell_cv_v"] < report["cell_overvoltage_release_v"]
    assert report["charge_overcurrent_trip_a"] > charger.charging.constant_current_a
    assert charger.charging.automatic_restart_enabled is False


def test_soft_start_fits_switch_level_window():
    charger = load_charger_config()
    # 8–12 ms 的开关级窗口内必须完成软启动，否则 CC 指标会测在瞬态上。
    assert charger.charging.soft_start_time_s <= 2e-3


def test_controller_gains_match_preregistered_value():
    controller = load_controller_config()
    assert controller.voltage_loop.kp == pytest.approx(2.0)
    assert controller.voltage_loop.ki == pytest.approx(2000.0)
    assert controller.voltage_loop.kaw == pytest.approx(50.0)
    assert controller.current_loop.kp == pytest.approx(0.025)
    assert controller.current_loop.ki == pytest.approx(50.0)
    assert controller.duty_min < controller.duty_max < 1.0


def test_tuning_grid_contains_frozen_gains():
    controller = load_controller_config()
    grid = load_tuning_grid()
    assert controller.voltage_loop.kp in grid["voltage_kp"]
    assert controller.voltage_loop.ki in grid["voltage_ki"]


def test_twenty_charging_cases_and_layers():
    cases = load_charging_cases()
    assert len(cases) == 20
    assert [case.id for case in cases][:3] == ["C01", "C02", "C03"]
    counts = method_counts()
    assert counts["spice_simulation"] == 12
    assert counts["ecm_charge_envelope"] == 3
    assert counts["software_test"] == 4
    assert counts["behavioral_charging_simulation"] == 1


def test_reliable_step_limit_is_twenty_nanoseconds():
    assert MINIMUM_RELIABLE_STEP_S == pytest.approx(2e-8)


def test_invalid_charger_config_is_rejected():
    import dataclasses

    charger = load_charger_config()
    raised = dataclasses.replace(
        charger,
        charging=dataclasses.replace(charger.charging, constant_voltage_v=13.5),
    )
    with pytest.raises(ChargerConfigError):
        raised.validate_against_protection()
