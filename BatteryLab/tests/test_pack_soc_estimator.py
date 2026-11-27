"""电池组 SOC 估计单元测试。"""

from __future__ import annotations

import math

import pytest

from estimation.ecm_observer import ObserverRCBranch
from estimation.pack_soc_estimator import (
    PackEstimationError,
    PackSOCEstimator,
    calculate_cell_currents,
    summarize_pack_soc,
)


class LinearOCV:
    def voltage_at(self, soc: float) -> float:
        return 3.0 + float(soc)

    def slope_at(self, soc: float) -> float:
        return 1.0


def test_cell_currents_add_balancing():
    currents = calculate_cell_currents(1.0, [0.04, 0.0, 0.0])
    assert currents.tolist() == pytest.approx([1.04, 1.0, 1.0])


def test_summarize_pack_uses_weakest_cell_for_available_charge():
    summary = summarize_pack_soc([0.8, 0.5, 0.6], [2.0, 2.0, 2.0])
    assert math.isclose(summary["minimum_cell_soc"], 0.5)
    assert math.isclose(summary["soc_spread_pp"], 30.0)
    assert math.isclose(summary["ideal_discharge_charge_bound_ah"], 1.0)


def test_balancing_current_changes_cell_soc():
    estimator = PackSOCEstimator(capacities_ah=[2.0, 2.0, 2.0], initial_socs=[0.8, 0.8, 0.8])
    result = estimator.step(1.0, 1.0, 3600.0, balancing_currents_a=[0.04, 0.0, 0.0])
    assert result["cell_soc"][0] == pytest.approx(0.28, abs=1e-12)
    assert result["cell_soc"][1] == pytest.approx(0.30, abs=1e-12)
    assert result["cell_soc"][2] == pytest.approx(0.30, abs=1e-12)


def test_voltage_correction_path_is_optional():
    estimator = PackSOCEstimator(
        capacities_ah=[2.0, 2.0],
        initial_socs=[0.5, 0.5],
        r0_ohm=[0.05, 0.05],
        branches=(ObserverRCBranch(0.02, 10.0),),
        ocv_tables=[LinearOCV(), LinearOCV()],
    )
    voltages = [3.5, 3.5]
    result = estimator.step(0.0, 0.0, 1.0, balancing_currents_a=[0.0, 0.0], cell_voltages_v=voltages)
    assert len(result["cell_soc"]) == 2
    assert all(status == "VOLTAGE_CORRECTED" for status in result["cell_status"])


def test_invalid_configuration_raises():
    with pytest.raises(PackEstimationError):
        PackSOCEstimator(capacities_ah=[2.0], initial_socs=[0.5, 0.5])
    with pytest.raises(PackEstimationError):
        calculate_cell_currents(1.0, [0.04, -0.01])
