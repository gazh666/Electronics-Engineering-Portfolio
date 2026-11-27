"""损耗与开关能量解析函数测试（合成波形）。"""

from __future__ import annotations

import numpy as np
import pytest

from analysis.loss_analysis import (
    capacitor_esr_loss,
    component_loss_fractions,
    conduction_loss_in_on_windows,
    gate_network_losses,
    gate_on_intervals,
    inductor_dcr_loss,
    interval_energy,
    loss_summary_table,
    mosfet_network_loss,
    resistor_loss,
    switching_energy,
    threshold_intervals,
)


def _time(count: int = 1001, span: float = 1e-5) -> np.ndarray:
    return np.linspace(0.0, span, count)


def test_resistive_losses():
    time = _time()
    current = np.full_like(time, 2.0)
    assert resistor_loss(time, current, 0.1) == pytest.approx(0.4)
    assert inductor_dcr_loss(time, current, 0.05) == pytest.approx(0.2)
    assert capacitor_esr_loss(time, current, 0.03) == pytest.approx(0.12)
    with pytest.raises(ValueError):
        resistor_loss(time, current, -0.1)


def test_mosfet_network_loss_sums_drain_and_gate():
    time = _time()
    vds = np.full_like(time, 2.0)
    drain = np.full_like(time, 0.5)
    vgs = np.full_like(time, 10.0)
    gate = np.full_like(time, 0.001)
    assert mosfet_network_loss(time, vds, drain, vgs, gate) == pytest.approx(1.01)


def test_gate_network_losses_use_time_weighted_rms():
    time = _time()
    drive = np.full_like(time, 10.0)
    gate = np.full_like(time, 8.0)
    current = np.full_like(time, 0.2)
    losses = gate_network_losses(
        time,
        drive_voltage_v=drive,
        gate_voltage_v=gate,
        gate_current_a=current,
        gate_resistance_ohm=10.0,
        pulldown_resistance_ohm=100_000.0,
    )
    # RG 电流 = (10-8)/10 = 0.2 A → 0.4 W
    assert losses["gate_resistor_loss_w"] == pytest.approx(0.4)
    assert losses["pulldown_loss_w"] == pytest.approx(64.0 / 100_000.0)
    assert losses["driver_input_power_w"] == pytest.approx(0.0)


def test_threshold_intervals_detects_rise_and_fall():
    time = np.linspace(0.0, 100e-9, 1001)
    gate = np.clip((time - 10e-9) / 20e-9, 0.0, 1.0) * 10.0
    rising = threshold_intervals(time, gate, low_level=1.0, high_level=9.0, rising=True)
    assert len(rising) == 1
    assert rising[0][0] == pytest.approx(12e-9, abs=0.5e-9)
    assert rising[0][1] == pytest.approx(28e-9, abs=0.5e-9)
    falling = threshold_intervals(time, gate, low_level=1.0, high_level=9.0, rising=False)
    assert falling == []


def test_switching_energy_integrates_transition():
    time = np.linspace(0.0, 100e-9, 2001)
    gate = np.clip((time - 10e-9) / 20e-9, 0.0, 1.0) * 10.0
    vds = np.full_like(time, 10.0)
    drain = np.full_like(time, 1.0)
    energy = switching_energy(
        time, vds, drain, gate, low_level_v=0.0, high_level_v=10.0
    )
    assert len(energy.turn_on_intervals_s) == 1
    # 区间为 1 V -> 9 V，即 16 ns，功率 10 W → 160 nJ
    assert energy.turn_on_energy_j == pytest.approx(1.6e-7, rel=0.05)
    assert energy.turn_off_energy_j == pytest.approx(0.0, abs=1e-15)
    assert energy.total_energy_j == pytest.approx(energy.turn_on_energy_j)


def test_gate_on_intervals_and_conduction_estimate():
    time = np.linspace(0.0, 10e-6, 1001)
    period = 10e-6
    gate = np.where((time % period) < 4e-6, 10.0, 0.0)
    drain = np.where((time % period) < 4e-6, 2.0, 0.0)
    intervals = gate_on_intervals(time, gate, threshold_v=3.0)
    assert len(intervals) >= 1
    assert intervals[0][0] == pytest.approx(0.0)
    assert intervals[0][1] == pytest.approx(4e-6)
    estimate = conduction_loss_in_on_windows(
        time, drain, gate, rds_on_ohm=0.05, gate_threshold_v=3.0
    )
    # 4/10 占空比，2 A，50 mΩ → 平均 0.4*0.2 = 0.08 W
    assert estimate == pytest.approx(0.08, rel=0.05)


def test_interval_energy_rejects_bad_interval():
    time = _time()
    values = np.ones_like(time)
    with pytest.raises(ValueError):
        interval_energy(time, values, values, (5e-6, 1e-6))


def test_loss_tables_from_accounting_like_object():
    class Dummy:
        mosfet_network_average_power_w = 0.05
        diode_average_power_w = 0.4
        dcr_loss_w = 0.18
        esr_loss_w = 0.001
        gate_resistor_loss_w = 0.01
        pulldown_loss_w = 0.0004
        total_loss_w = 0.6414

    table = loss_summary_table(Dummy())
    assert len(table) == 7
    assert table[-1]["item"] == "total"
    fractions = component_loss_fractions(Dummy())
    assert fractions["diode"] == pytest.approx(0.4 / 0.6414)
