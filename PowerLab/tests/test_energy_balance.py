"""能量平衡测试（由功率核算构造）。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from analysis.energy_balance import (
    check_energy_balance,
    energy_balance,
    energy_balance_sum,
    residual_power,
)
from analysis.power_metrics import compute_power_accounting


def _frame(
    *,
    input_current: float = 0.5,
    vout: float = 5.0,
    time: np.ndarray | None = None,
    input_current_series: np.ndarray | None = None,
) -> pd.DataFrame:
    time = np.linspace(0.0, 1e-5, 101) if time is None else time
    zeros = np.zeros_like(time)
    return pd.DataFrame(
        {
            "time_s": time,
            "vin_v": np.full_like(time, 10.0),
            "vout_v": np.full_like(time, vout),
            "input_current_a": (
                np.full_like(time, input_current)
                if input_current_series is None
                else input_current_series
            ),
            "load_current_a": np.full_like(time, 0.5),
            "mosfet_vds_v": zeros,
            "mosfet_drain_terminal_current_a": zeros,
            "mosfet_vgs_v": np.full_like(time, 10.0),
            "gate_current_a": zeros,
            "diode_anode_cathode_voltage_v": zeros,
            "diode_current_a": zeros,
            "inductor_current_a": np.full_like(time, 1.0),
            "capacitor_current_a": np.full_like(time, 0.5),
            "driver_current_a": zeros,
            "drive_vgs_command_v": np.full_like(time, 10.0),
        }
    )


def test_energy_balance_marks_large_residual_excessive():
    accounting = compute_power_accounting(_frame())
    balance = energy_balance(accounting)
    assert balance.duration_s == pytest.approx(1e-5)
    assert balance.input_energy_j == pytest.approx(5.0e-5, rel=1e-9)
    assert balance.output_energy_j == pytest.approx(2.5e-5, rel=1e-9)
    assert balance.residual_ratio == pytest.approx(0.5, rel=1e-9)
    assert balance.status == "excessive"
    assert balance.to_dict()["data_source"] == "spice_simulation"


def test_energy_balance_ok_when_residual_small():
    accounting = compute_power_accounting(_frame(input_current=0.25))
    balance = energy_balance_sum(accounting)
    assert balance.residual_ratio == pytest.approx(0.0, abs=1e-12)
    assert balance.status == "ok"
    assert check_energy_balance(balance)["passed"] is True


def test_energy_balance_custom_ratios_and_validation():
    accounting = compute_power_accounting(_frame(input_current=0.2525))
    balance = energy_balance(accounting, warning_ratio=0.001, failure_ratio=0.02)
    assert balance.status == "warning"
    with pytest.raises(ValueError):
        energy_balance(accounting, warning_ratio=0.2, failure_ratio=0.1)
    with pytest.raises(ValueError):
        energy_balance("bad")
    with pytest.raises(ValueError):
        check_energy_balance(balance, tolerance=0.0)


def test_residual_power_is_not_redistributed():
    accounting = compute_power_accounting(_frame(input_current=0.5))
    balance = energy_balance(accounting)
    assert residual_power(balance) == pytest.approx(2.5, rel=1e-9)
    # 输入功率不变、损耗不含残差
    assert accounting.total_loss_w == pytest.approx(0.0, abs=1e-12)
