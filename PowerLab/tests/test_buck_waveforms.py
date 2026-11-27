"""Buck 波形提取与 PWM 阈值分析测试（人工构造数组，不是 SPICE 数据）。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from analysis.buck_waveforms import (
    WAVEFORM_COLUMNS,
    analyze_pwm_waveform,
    buck_waveforms_from_result,
    threshold_crossing_time,
    threshold_crossings,
)


def _frame(**overrides) -> pd.DataFrame:
    payload = {
        "time_s": [0.0, 1e-6, 2e-6, 3e-6],
        "vin_v": [12.0, 12.0, 12.0, 12.0],
        "gate_v": [0.0, 5.0, 5.0, 0.0],
        "sw_v": [0.0, 12.0, 12.0, 0.0],
        "lx_v": [10.0, 11.0, 12.0, 13.0],
        "out_v": [5.0, 5.1, 5.2, 5.3],
        "vin_branch_current_a": [-0.5, -1.0, -1.5, -2.0],
        "vsense_branch_current_a": [1.0, 1.5, 2.0, 2.5],
    }
    payload.update(overrides)
    return pd.DataFrame(payload)


def test_conversion_produces_standard_columns_and_signs():
    waveforms = buck_waveforms_from_result(_frame(), load_resistance_ohm=2.5)
    assert tuple(waveforms.columns) == WAVEFORM_COLUMNS
    assert waveforms["input_current_a"].tolist() == [0.5, 1.0, 1.5, 2.0]
    assert waveforms["inductor_voltage_v"].tolist() == [5.0, 5.9, 6.8, 7.7]
    assert waveforms["load_current_a"].tolist() == pytest.approx([2.0, 2.04, 2.08, 2.12])
    expected_cap = waveforms["inductor_current_a"] - waveforms["load_current_a"]
    assert waveforms["capacitor_current_a"].tolist() == pytest.approx(expected_cap.tolist())


def test_missing_required_column_is_rejected():
    frame = _frame()
    frame = frame.drop(columns=["sw_v"])
    with pytest.raises(ValueError, match="sw_v"):
        buck_waveforms_from_result(frame, load_resistance_ohm=2.5)


def test_missing_inductor_current_column_is_rejected():
    frame = _frame().drop(columns=["vsense_branch_current_a"])
    with pytest.raises(ValueError, match="inductor current"):
        buck_waveforms_from_result(frame, load_resistance_ohm=2.5)


def test_non_increasing_time_is_rejected():
    frame = _frame(time_s=[0.0, 1e-6, 1e-6, 3e-6])
    with pytest.raises(ValueError, match="strictly increasing"):
        buck_waveforms_from_result(frame, load_resistance_ohm=2.5)


def test_nan_samples_are_rejected():
    frame = _frame(out_v=[5.0, float("nan"), 5.2, 5.3])
    with pytest.raises(ValueError):
        buck_waveforms_from_result(frame, load_resistance_ohm=2.5)


def test_invalid_load_resistance_is_rejected():
    with pytest.raises(ValueError):
        buck_waveforms_from_result(_frame(), load_resistance_ohm=0.0)


def test_threshold_crossing_time_interpolates_linearly():
    assert threshold_crossing_time(0.0, 1.0, 0.0, 10.0, 2.5) == pytest.approx(0.25)
    with pytest.raises(ValueError):
        threshold_crossing_time(1.0, 1.0, 0.0, 1.0, 0.5)
    with pytest.raises(ValueError):
        threshold_crossing_time(0.0, 1.0, 2.0, 2.0, 2.0)


def test_threshold_crossings_detects_edges():
    time = np.array([0.0, 1.0, 2.0, 3.0])
    values = np.array([0.0, 5.0, 5.0, 0.0])
    rising, falling = threshold_crossings(time, values, 2.5)
    assert rising.tolist() == pytest.approx([0.5])
    assert falling.tolist() == pytest.approx([2.5])


def _square_wave(cycles: float = 3.4, duty: float = 0.4, period: float = 10e-6):
    step = 1e-8
    time = np.arange(0.0, cycles * period, step)
    phase = np.mod(time, period) / period
    gate = np.where(phase < duty, 5.0, 0.0)
    return time, gate


def test_analyze_pwm_measures_frequency_and_duty():
    time, gate = _square_wave()
    analysis = analyze_pwm_waveform(time, gate, low_voltage_v=0.0, high_voltage_v=5.0)
    assert analysis.mean_frequency_hz == pytest.approx(1e5, rel=1e-3)
    assert analysis.mean_duty_cycle == pytest.approx(0.4, abs=5e-3)
    assert analysis.complete_cycles == 2
    assert analysis.data_source == "spice_simulation"
    assert len(analysis.cycle_boundaries_s) == 3


def test_analyze_pwm_ignores_incomplete_first_pulse():
    time, gate = _square_wave(cycles=2.4)
    analysis = analyze_pwm_waveform(time, gate, low_voltage_v=0.0, high_voltage_v=5.0)
    assert analysis.rising_edge_times_s[0] > time[0]
    assert analysis.complete_cycles == 1


def test_analyze_pwm_requires_two_rising_edges():
    time, gate = _square_wave(cycles=0.9)
    with pytest.raises(ValueError, match="two rising edges"):
        analyze_pwm_waveform(time, gate, low_voltage_v=0.0, high_voltage_v=5.0)


def test_analyze_pwm_rejects_bad_levels():
    time, gate = _square_wave()
    with pytest.raises(ValueError):
        analyze_pwm_waveform(time, gate, low_voltage_v=5.0, high_voltage_v=5.0)
    with pytest.raises(ValueError):
        analyze_pwm_waveform(time[:-1], gate, low_voltage_v=0.0, high_voltage_v=5.0)


def test_pwm_analysis_serializes_derived_values():
    time, gate = _square_wave()
    payload = analyze_pwm_waveform(time, gate, low_voltage_v=0.0, high_voltage_v=5.0).to_dict()
    assert payload["complete_cycles"] == 2
    assert payload["mean_period_s"] == pytest.approx(10e-6, rel=1e-3)
    assert payload["threshold_v"] == pytest.approx(2.5)
