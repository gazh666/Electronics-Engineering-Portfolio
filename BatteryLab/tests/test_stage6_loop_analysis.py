"""第六阶段环路：Buck 小信号、双环裕度与带宽分离。"""

from __future__ import annotations

import pytest

from analysis.charging_loop_analysis import (
    analyze_current_loop,
    analyze_voltage_loop,
    bandwidth_separation_ratio,
    buck_plant_response,
    default_frequency_grid,
    loop_margins,
)
from charging.battery_adapter import load_identified_battery_bundle
from charging.config import load_charger_config, load_controller_config


def _plant():
    charger = load_charger_config()
    controller = load_controller_config()
    bundle = load_identified_battery_bundle(charger.battery.identified_model_id)
    cells = charger.battery.series_cells
    r0 = cells * float(bundle["parameters"].r0_ohm)
    r1 = cells * float(bundle["parameters"].r1_ohm)
    c1 = float(bundle["parameters"].c1_f) / cells
    grid = default_frequency_grid()
    plant = buck_plant_response(
        grid,
        charger.power_stage.input_voltage_v,
        charger.power_stage.inductance_h,
        charger.power_stage.capacitance_f,
        r0 + charger.power_stage.path_resistance_ohm,
        charger.power_stage.capacitor_esr_ohm,
        charger.power_stage.inductor_dcr_ohm,
    )
    current_loop = analyze_current_loop(
        grid,
        vin_v=charger.power_stage.input_voltage_v,
        inductance_h=charger.power_stage.inductance_h,
        capacitance_f=charger.power_stage.capacitance_f,
        load_resistance_ohm=r0 + charger.power_stage.path_resistance_ohm,
        capacitor_esr_ohm=charger.power_stage.capacitor_esr_ohm,
        kp_duty_per_a=controller.current_loop.kp,
        ki_duty_per_as=controller.current_loop.ki,
        inductor_dc_resistance_ohm=charger.power_stage.inductor_dcr_ohm,
    )
    voltage_loop = analyze_voltage_loop(
        grid, r0, r1, c1, controller.voltage_loop.kp, controller.voltage_loop.ki,
        inner_loop_gain=current_loop["loop_gain"],
    )
    return plant, current_loop, voltage_loop


def test_plant_has_positive_dc_current_gain():
    plant, _, _ = _plant()
    assert float(abs(plant["current"][0])) > 1.0


def test_current_loop_bandwidth_and_margin():
    _, current_loop, _ = _plant()
    assert 400.0 < current_loop["gain_crossover_hz"] < 1200.0
    assert current_loop["phase_margin_deg"] > 45.0


def test_voltage_loop_slower_than_current_loop():
    _, current_loop, voltage_loop = _plant()
    ratio = bandwidth_separation_ratio(current_loop, voltage_loop)
    assert ratio > 5.0
    assert voltage_loop["gain_crossover_hz"] < current_loop["gain_crossover_hz"]


def test_margin_helper_reports_infinite_when_no_phase_crossover():
    import numpy as np

    frequency = np.array([1.0, 10.0, 100.0])
    loop_gain = np.array([10.0 + 0j, 1.0 + 0j, 0.1 + 0j])
    margins = loop_margins(frequency, loop_gain)
    assert margins["gain_margin_infinite"] is True
    assert margins["gain_margin_db"] is None
    with pytest.raises(ValueError):
        loop_margins(np.array([1.0]), np.array([1.0 + 0j]))
