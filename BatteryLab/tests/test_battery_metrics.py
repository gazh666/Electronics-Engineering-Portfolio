"""容量、能量与单位换算测试（人工数据仅用于数学函数验证）。"""

from __future__ import annotations

import numpy as np
import pytest

from analysis.battery_metrics import (
    calculate_charge_capacity_ah,
    calculate_charge_energy_wh,
    calculate_discharge_capacity_ah,
    calculate_discharge_energy_wh,
    convert_current_sign,
    convert_time_to_seconds,
    derive_soc_from_current,
    instantaneous_power_w,
    segment_statistics,
    split_sign_capacity_ah,
    summarize_measurement,
)


def test_constant_current_capacity():
    time_s = np.array([0, 1800, 3600])
    current = np.array([1.0, 1.0, 1.0])
    assert calculate_discharge_capacity_ah(time_s, current) == pytest.approx(1.0)


def test_two_ampere_capacity():
    time_s = np.array([0, 900, 1800])
    current = np.array([2.0, 2.0, 2.0])
    assert calculate_discharge_capacity_ah(time_s, current) == pytest.approx(1.0)


def test_constant_voltage_energy():
    time_s = np.array([0, 1800, 3600])
    voltage = np.array([3.7, 3.7, 3.7])
    current = np.array([1.0, 1.0, 1.0])
    assert calculate_discharge_energy_wh(time_s, voltage, current) == pytest.approx(3.7)


def test_negative_current_is_charge():
    time_s = np.array([0.0, 3600.0])
    current = np.array([-2.0, -2.0])
    assert calculate_charge_capacity_ah(time_s, current) == pytest.approx(2.0)
    assert calculate_discharge_capacity_ah(time_s, current) == pytest.approx(0.0)
    energy = calculate_charge_energy_wh(time_s, np.array([4.0, 4.0]), current)
    assert energy == pytest.approx(8.0)


def test_zero_current_rest():
    time_s = np.array([0.0, 600.0, 1200.0])
    current = np.zeros(3)
    assert calculate_discharge_capacity_ah(time_s, current) == pytest.approx(0.0)
    assert calculate_charge_capacity_ah(time_s, current) == pytest.approx(0.0)


def test_non_uniform_intervals():
    time_s = np.array([0.0, 100.0, 400.0, 1000.0])
    current = np.array([1.0, 1.0, 2.0, 2.0])
    expected = (1.0 * 100 + 1.5 * 300 + 2.0 * 600) / 3600
    assert calculate_discharge_capacity_ah(time_s, current) == pytest.approx(expected)


def test_invalid_time_axis():
    with pytest.raises(ValueError):
        calculate_discharge_capacity_ah(np.array([0.0, 10.0, 5.0]), np.ones(3))
    with pytest.raises(ValueError):
        calculate_discharge_capacity_ah(np.array([0.0]), np.ones(1))


def test_length_mismatch():
    with pytest.raises(ValueError):
        calculate_discharge_capacity_ah(np.array([0.0, 1.0]), np.ones(3))


def test_non_finite_values():
    with pytest.raises(ValueError):
        calculate_discharge_capacity_ah(np.array([0.0, np.nan]), np.ones(2))
    with pytest.raises(ValueError):
        calculate_discharge_capacity_ah(np.array([0.0, 1.0]), np.array([1.0, np.inf]))


def test_unit_conversion():
    assert convert_time_to_seconds(np.array([1.0]), "ms")[0] == pytest.approx(0.001)
    assert convert_time_to_seconds(np.array([2.0]), "min")[0] == pytest.approx(120.0)
    assert convert_time_to_seconds(np.array([1.0]), "h")[0] == pytest.approx(3600.0)
    with pytest.raises(ValueError):
        convert_time_to_seconds(np.array([1.0]), "day")


def test_current_sign_conversion():
    raw = np.array([1.0, -2.0])
    assert np.allclose(convert_current_sign(raw, "charge_positive"), np.array([-1.0, 2.0]))
    assert np.allclose(convert_current_sign(raw, "discharge_positive"), raw)
    with pytest.raises(ValueError):
        convert_current_sign(raw, "unknown")


def test_split_sign_handles_zero_crossing():
    time_s = np.array([0.0, 3600.0])
    current = np.array([1.0, -1.0])
    discharge, charge = split_sign_capacity_ah(time_s, current)
    # 线性插值零穿越点在 1800 s，两侧三角形面积各 900 A·s = 0.25 Ah
    assert discharge == pytest.approx(0.25, rel=1e-6)
    assert charge == pytest.approx(0.25, rel=1e-6)


def test_power_and_soc():
    power = instantaneous_power_w(np.array([4.0, 3.5]), np.array([1.0, -1.0]))
    assert np.allclose(power, np.array([4.0, -3.5]))
    soc = derive_soc_from_current(np.array([0.0, 3600.0]), np.array([2.0, 2.0]), 1.0, 2.0)
    assert soc[0] == pytest.approx(1.0)
    assert soc[-1] == pytest.approx(0.0, abs=1e-9)


def test_summary_and_segments():
    time_s = np.array([0.0, 600.0, 1200.0, 1800.0, 2400.0])
    voltage = np.array([4.0, 3.9, 3.8, 4.05, 4.1])
    current = np.array([1.0, 1.0, 0.0, -1.0, -1.0])
    summary = summarize_measurement(time_s, voltage, current, capacity_ah=2.0, initial_soc=1.0)
    assert summary["points"] == 5
    assert summary["discharge_capacity_ah"] > 0
    assert summary["charge_capacity_ah"] > 0
    segments = segment_statistics(time_s, current, min_segment_s=1.0)
    labels = [segment["label"] for segment in segments]
    assert "discharge" in labels and "rest" in labels and "charge" in labels
