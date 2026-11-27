"""功率核算基础函数测试（合成波形，不调用 SPICE）。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from analysis.power_metrics import (
    PowerAccounting,
    average_power,
    compute_power_accounting,
    efficiency_percent,
    frame_window,
    integrated_power,
    loss_fractions,
    relative_residual,
    require_columns,
    rms_current_from_resistance_loss,
    rms_value,
    time_average,
)


def _frame(**overrides: float) -> pd.DataFrame:
    time = np.linspace(0.0, 1e-5, 101)
    values = {
        "time_s": time,
        "vin_v": np.full_like(time, 10.0),
        "vout_v": np.full_like(time, 5.0),
        "input_current_a": np.full_like(time, 0.5),
        "load_current_a": np.full_like(time, 0.5),
        "mosfet_vds_v": np.zeros_like(time),
        "mosfet_drain_terminal_current_a": np.zeros_like(time),
        "mosfet_vgs_v": np.full_like(time, 10.0),
        "gate_current_a": np.zeros_like(time),
        "diode_anode_cathode_voltage_v": np.zeros_like(time),
        "diode_current_a": np.zeros_like(time),
        "inductor_current_a": np.full_like(time, 1.0),
        "capacitor_current_a": np.full_like(time, 0.5),
        "driver_current_a": np.zeros_like(time),
        "drive_vgs_command_v": np.full_like(time, 10.0),
    }
    for key, value in overrides.items():
        values[key] = np.full_like(time, value)
    return pd.DataFrame(values)


def test_time_average_and_rms():
    time = np.linspace(0.0, 1.0, 11)
    values = np.full_like(time, 2.0)
    assert time_average(time, values) == pytest.approx(2.0)
    assert rms_value(time, values) == pytest.approx(2.0)
    assert rms_current_from_resistance_loss(0.4, 0.1) == pytest.approx(2.0)


def test_average_and_integrated_power():
    time = np.linspace(0.0, 1e-3, 101)
    voltage = np.full_like(time, 10.0)
    current = np.full_like(time, 2.0)
    assert integrated_power(time, voltage, current) == pytest.approx(0.02, rel=1e-9)
    assert average_power(time, voltage, current) == pytest.approx(20.0, rel=1e-9)


def test_efficiency_status_codes():
    assert efficiency_percent(95.0, 100.0) == (pytest.approx(95.0), "ok")
    value, status = efficiency_percent(5.0, 0.0)
    assert value is None and status == "input_power_not_positive"
    value, status = efficiency_percent(101.0, 100.0)
    assert value == pytest.approx(101.0)
    assert status == "efficiency_above_100_check_boundaries"


def test_frame_window_keeps_boundaries():
    frame = _frame()
    window = frame_window(frame, 1e-6, 5e-6)
    assert window["time_s"].iloc[0] >= 1e-6
    assert window["time_s"].iloc[-1] <= 5e-6
    with pytest.raises(ValueError):
        frame_window(frame, 5e-6, 1e-6)


def test_compute_power_accounting_energy_balance():
    accounting = compute_power_accounting(_frame())
    assert accounting.input_average_power_w == pytest.approx(5.0, rel=1e-9)
    assert accounting.output_average_power_w == pytest.approx(2.5, rel=1e-9)
    assert accounting.total_loss_w == pytest.approx(0.0, abs=1e-12)
    assert accounting.residual_w == pytest.approx(2.5, rel=1e-9)
    assert accounting.efficiency_power_stage_percent == pytest.approx(50.0)
    assert isinstance(accounting.to_dict(), dict)
    assert relative_residual(accounting) > 0


def test_compute_power_accounting_counts_passive_losses():
    accounting = compute_power_accounting(_frame(), dcr_ohm=0.1, esr_ohm=0.2)
    assert accounting.dcr_loss_w == pytest.approx(0.1, rel=1e-6)
    assert accounting.esr_loss_w == pytest.approx(0.05, rel=1e-6)
    fractions = loss_fractions(accounting)
    assert set(fractions) >= {"dcr", "esr"}


def test_compute_power_accounting_requires_columns():
    frame = _frame().drop(columns=["drive_vgs_command_v"])
    with pytest.raises(ValueError):
        compute_power_accounting(frame)
    with pytest.raises(ValueError):
        compute_power_accounting(_frame().head(2))


def test_require_columns_reports_missing():
    require_columns(_frame())
    with pytest.raises(ValueError):
        require_columns(_frame().drop(columns=["time_s"]))
