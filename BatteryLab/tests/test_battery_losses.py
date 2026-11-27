"""损耗分析测试。"""

from __future__ import annotations

import pandas as pd
import pytest

from analysis.battery_losses import LossAnalysisError, instantaneous_losses, integrate_losses
from battery_models.parameters import CellParameters, RCBranch


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "time_s": [0.0, 10.0, 20.0],
            "current_a": [0.0, 0.0, 0.0],
            "terminal_voltage_v": [3.79, 3.79, 3.79],
            "polarization_1_v": [0.1, 0.1, 0.1],
            "polarization_2_v": [0.0, 0.0, 0.0],
            "stored_energy_j": [5.0, 5.0, 5.0],
        }
    )


def test_polarization_loss_uses_voltage_squared_over_resistance() -> None:
    parameters = CellParameters(capacity_ah=2.0, r0_ohm=0.03)
    branches = (RCBranch(0.02, 1000.0),)
    losses = instantaneous_losses(parameters, branches, _frame())
    assert losses["branch1_loss_w"].iloc[0] == pytest.approx(0.1**2 / 0.02)
    assert losses["ohmic_loss_w"].iloc[0] == pytest.approx(0.0)


def test_integrated_losses_on_rest() -> None:
    parameters = CellParameters(capacity_ah=2.0, r0_ohm=0.03)
    branches = (RCBranch(0.02, 1000.0),)
    result = integrate_losses(parameters, branches, _frame())
    assert result["polarization_energy_j"] == pytest.approx(0.5 * 20.0)
    assert result["ohmic_energy_j"] == pytest.approx(0.0)
    assert result["terminal_energy_j"] == pytest.approx(0.0)
    assert result["stored_energy_change_j"] == pytest.approx(0.0)
    assert result["mean_polarization_power_w"] == pytest.approx(0.5)
    assert result["integration_method"] == "trapezoidal"


def test_i_squared_r1_is_not_used_as_polarization_loss() -> None:
    parameters = CellParameters(capacity_ah=2.0, r0_ohm=0.03)
    branch = RCBranch(0.02, 1000.0)
    frame = _frame()
    frame["current_a"] = [2.0, 2.0, 2.0]
    losses = instantaneous_losses(parameters, (branch,), frame)
    naive = 2.0**2 * branch.resistance_ohm
    assert losses["branch1_loss_w"].iloc[0] != pytest.approx(naive)
    assert losses["branch1_loss_w"].iloc[0] == pytest.approx(0.1**2 / 0.02)


def test_invalid_window_rejected() -> None:
    parameters = CellParameters(capacity_ah=2.0, r0_ohm=0.03)
    with pytest.raises(LossAnalysisError):
        integrate_losses(parameters, (RCBranch(0.02, 1000.0),), _frame(), start_s=15.0, end_s=16.0)
