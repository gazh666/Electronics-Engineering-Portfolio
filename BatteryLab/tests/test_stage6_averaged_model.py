"""第六阶段平均模型：CC/CV 行为、步长上限与 BMS 禁止充电。"""

from __future__ import annotations

import pytest

from charging.config import load_charger_config, load_controller_config
from simulations.averaged_charger import (
    AveragedChargerError,
    AveragedChargerParameters,
    compare_with_switching,
    simulate_averaged_charge,
)


@pytest.fixture(scope="module")
def parameters() -> AveragedChargerParameters:
    return AveragedChargerParameters.from_configs(
        load_charger_config(), load_controller_config()
    ).validate()


def test_cc_region_tracks_current(parameters):
    result = simulate_averaged_charge(
        parameters, initial_soc=0.30, duration_s=0.02, stop_at_termination=False
    )
    assert result.state in ("CC", "SOFT_START")
    assert float(result.charging_current_a[-1]) == pytest.approx(1.0, abs=0.02)
    assert result.metrics["cc_mean_current_a"] == pytest.approx(1.0, abs=0.02)


def test_cv_region_regulates_voltage(parameters):
    result = simulate_averaged_charge(
        parameters, initial_soc=0.90, duration_s=0.04, stop_at_termination=False
    )
    assert result.metrics["reached_cv"] is True
    assert float(result.pack_voltage_v[-1]) == pytest.approx(12.15, abs=0.01)
    assert float(result.charging_current_a[-1]) < 0.5


def test_bms_inhibit_stops_charging(parameters):
    result = simulate_averaged_charge(
        parameters, initial_soc=0.5, duration_s=0.01, bms_charge_allowed=False
    )
    assert result.state == "FAULT"
    assert result.termination_reason == "BMS_CHARGE_INHIBITED"


def test_step_above_average_limit_rejected(parameters):
    with pytest.raises(AveragedChargerError):
        simulate_averaged_charge(parameters, initial_soc=0.5, duration_s=0.01, step_s=5e-4)


def test_invalid_target_above_duty_limit_rejected():
    import dataclasses

    parameters = AveragedChargerParameters.from_configs(
        load_charger_config(), load_controller_config()
    )
    raised = dataclasses.replace(parameters, voltage_target_v=17.5)
    with pytest.raises(AveragedChargerError):
        raised.validate()


def test_cross_layer_comparison_reports_missing_reference(parameters):
    result = simulate_averaged_charge(parameters, initial_soc=0.63, duration_s=0.01)
    comparison = compare_with_switching(result, {})
    assert comparison["final_charging_current_a"]["difference"] is None
