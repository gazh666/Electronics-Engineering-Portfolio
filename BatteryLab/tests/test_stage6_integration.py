"""第六阶段集成：网表内控制器、步长守卫、PWL 与真实 ngspice 冒烟。"""

from __future__ import annotations

import numpy as np
import pytest

from charging.config import load_charger_config, load_controller_config
from circuits.charger_buck import PackFixture, pwl_expression, step_expression
from circuits.charger_spice_controller import (
    CascadeParameters,
    ChargerCircuitError,
    build_cascade_circuit,
    run_cascade_buck,
)
from simulations.charger_spice_runner import SpiceCaseError, prerun_netlist, run_case
from simulations.long_duration_charge import temperature_gate_test


@pytest.fixture(scope="module")
def charger():
    return load_charger_config()


@pytest.fixture(scope="module")
def controller():
    return load_controller_config()


def test_netlist_contains_both_pi_loops_and_protection_hooks(charger, controller):
    netlist = prerun_netlist("C01", charger=charger, controller=controller)
    for fragment in (
        "BEV ev 0",
        "BIREF iref 0",
        "BIV 0 xv I=",
        "BEI ei 0",
        "BII 0 xi I=",
        "RFF out ff_in",
        "CFF ff_in 0",
        "1-V(vfrz)",
        "1-V(ifrz)",
        "BRAMP ramp 0",
    ):
        assert fragment in netlist


def test_step_guard_rejects_coarse_timestep(charger, controller):
    fixture = PackFixture.from_equivalent_voltage(
        11.4, charger.power_stage.path_resistance_ohm, series_cells=charger.battery.series_cells
    )
    with pytest.raises(ChargerCircuitError):
        run_cascade_buck(
            charger.power_stage,
            fixture,
            CascadeParameters.from_configs(charger, controller),
            duration_s=1e-5,
            step_s=5e-8,
        )


def test_pwl_and_step_expressions():
    assert pwl_expression([(0.0, 18.0), (4e-3, 18.0), (4.01e-3, 16.0)]).startswith("PWL(")
    assert step_expression(1.0, 0.0, 4e-3).startswith("PWL(")
    assert step_expression(1.0) == "DC 1"


def test_cascade_short_run_is_real_and_bounded(charger, controller):
    fixture = PackFixture.from_equivalent_voltage(
        11.4, charger.power_stage.path_resistance_ohm, series_cells=charger.battery.series_cells
    )
    waveform, circuit, layout = run_cascade_buck(
        charger.power_stage,
        fixture,
        CascadeParameters.from_configs(charger, controller),
        duration_s=1e-3,
        step_s=2e-8,
    )
    assert np.all(np.diff(waveform.time_s) > 0.0)
    assert waveform.current_reference_a is not None
    assert float(waveform.charging_current_a[-1]) > 0.5
    for cell in waveform.cell_voltages_v:
        assert float(cell.max()) < 4.25
    assert "SMAIN" in str(circuit)


def test_non_spice_case_is_rejected():
    with pytest.raises(SpiceCaseError):
        run_case("C11", persist=False)


def test_temperature_gate_revokes_permission():
    result = temperature_gate_test(50.0)
    assert result["status"] == "PASS"
    assert result["charge_allowed"] is False
