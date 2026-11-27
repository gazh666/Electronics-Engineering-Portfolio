"""稳态窗口、时间加权指标与能量平衡测试（人工构造数组）。"""

from __future__ import annotations

import numpy as np
import pytest

from analysis.steady_state import (
    STATUS_INSUFFICIENT_CYCLES,
    STATUS_NOT_SETTLED,
    STATUS_STEADY_STATE,
    SteadyStateWindow,
    capacitor_charge_balance,
    cycle_ripples,
    identify_steady_state,
    inductor_volt_second_balance,
    peak_to_peak,
    settling_time_s,
    slice_window,
    steady_state_metrics,
    time_weighted_mean,
)
from circuits.buck_config import SteadyStateConfig

PERIOD_S = 10e-6


def test_time_weighted_mean_handles_nonuniform_sampling():
    time = [0.0, 1.0, 3.0]
    values = [0.0, 0.0, 4.0]
    assert time_weighted_mean(time, values) == pytest.approx(4.0 / 3.0)


def test_time_weighted_mean_rejects_bad_arrays():
    with pytest.raises(ValueError):
        time_weighted_mean([0.0], [1.0])
    with pytest.raises(ValueError):
        time_weighted_mean([0.0, 1.0], [1.0, float("inf")])
    with pytest.raises(ValueError):
        time_weighted_mean([0.0, 0.0], [1.0, 2.0])


def test_peak_to_peak():
    assert peak_to_peak([1.0, -2.0, 3.0]) == pytest.approx(5.0)
    with pytest.raises(ValueError):
        peak_to_peak([])


def test_slice_window_interpolates_boundaries():
    time = np.array([0.0, 1.0, 2.0])
    values = np.array([0.0, 10.0, 20.0])
    window_time, window_values = slice_window(time, values, 0.5, 1.5)
    assert window_time[0] == pytest.approx(0.5)
    assert window_time[-1] == pytest.approx(1.5)
    assert window_values.tolist() == pytest.approx([5.0, 10.0, 15.0])


def test_slice_window_rejects_out_of_range_and_reversed():
    time = np.array([0.0, 1.0, 2.0])
    values = np.array([0.0, 1.0, 2.0])
    with pytest.raises(ValueError):
        slice_window(time, values, -0.1, 1.0)
    with pytest.raises(ValueError):
        slice_window(time, values, 1.0, 0.5)


def test_cycle_ripples_per_cycle():
    time = np.array([0.0, 0.5, 1.0, 1.5, 2.0])
    values = np.array([0.0, 1.0, 0.0, 1.0, 0.0])
    assert cycle_ripples(time, values, [0.0, 1.0, 2.0]) == pytest.approx([1.0, 1.0])
    with pytest.raises(ValueError):
        cycle_ripples(time, values, [0.0])


def _periodic_case(cycles: int = 60, slope_v_per_s: float = 0.0):
    step = PERIOD_S / 200.0
    time = np.arange(0.0, cycles * PERIOD_S, step)
    phase = 2.0 * np.pi * time / PERIOD_S
    voltage = 5.0 + 0.01 * np.sin(phase) + slope_v_per_s * time
    current = 2.0 + 0.2 * np.sin(phase)
    boundaries = [index * PERIOD_S for index in range(cycles + 1)]
    return time, voltage, current, boundaries


def test_identify_steady_state_for_periodic_waveform():
    time, voltage, current, boundaries = _periodic_case()
    window = identify_steady_state(time, voltage, current, boundaries, SteadyStateConfig())
    assert window.status == STATUS_STEADY_STATE
    assert window.is_steady
    assert window.complete_cycles == 20
    assert window.mean_output_voltage_v == pytest.approx(5.0, abs=1e-3)


def test_identify_not_settled_for_ramping_waveform():
    time, voltage, current, boundaries = _periodic_case(slope_v_per_s=100.0)
    window = identify_steady_state(time, voltage, current, boundaries, SteadyStateConfig())
    assert window.status == STATUS_NOT_SETTLED
    assert not window.is_steady


def test_identify_insufficient_cycles():
    time, voltage, current, boundaries = _periodic_case(cycles=5)
    window = identify_steady_state(time, voltage, current, boundaries, SteadyStateConfig())
    assert window.status == STATUS_INSUFFICIENT_CYCLES
    # 记录结束于最后一个周期终点之前，因此只有 cycles - 1 个完整周期。
    assert window.complete_cycles == 4


def test_identify_rejects_invalid_boundaries_and_nan():
    time, voltage, current, boundaries = _periodic_case(cycles=30)
    with pytest.raises(ValueError):
        identify_steady_state(time, voltage, current, [0.0])
    with pytest.raises(ValueError):
        identify_steady_state(time, voltage, current, [0.0, 2e-5, 1e-5])
    bad = voltage.copy()
    bad[10] = float("nan")
    with pytest.raises(ValueError):
        identify_steady_state(time, bad, current, boundaries)


def test_steady_state_metrics_on_periodic_waveform():
    time, voltage, current, boundaries = _periodic_case()
    window = identify_steady_state(time, voltage, current, boundaries, SteadyStateConfig())
    payload = {
        "vout_v": voltage,
        "inductor_current_a": current,
        "input_current_a": current * 0.4,
        "load_current_a": voltage / 2.5,
    }
    metrics = steady_state_metrics(time, payload, window, boundaries)
    assert metrics["complete_cycles"] == 20
    assert metrics["output_voltage_mean_v"] == pytest.approx(5.0, abs=1e-3)
    assert metrics["output_voltage_ripple_vpp"] == pytest.approx(0.02, rel=1e-3)
    assert metrics["inductor_current_ripple_app"] == pytest.approx(0.4, rel=1e-3)
    assert metrics["data_source"] == "spice_simulation"


def test_steady_state_metrics_requires_waveform_fields():
    time, voltage, current, boundaries = _periodic_case()
    window = identify_steady_state(time, voltage, current, boundaries, SteadyStateConfig())
    with pytest.raises(ValueError):
        steady_state_metrics(time, {"vout_v": voltage}, window, boundaries)


def test_settling_time_returns_first_time_inside_band():
    time = np.linspace(0.0, 5e-3, 1001)
    values = np.where(time < 2e-3, 6.0, 5.0)
    settling = settling_time_s(time, values, 5.0, relative_band=0.02, absolute_band=0.01)
    assert settling == pytest.approx(2e-3, abs=5e-6)


def test_settling_time_returns_none_when_still_outside():
    time = np.linspace(0.0, 5e-3, 1001)
    values = 5.0 + 1000.0 * time
    assert settling_time_s(time, values, 5.0) is None


def test_volt_second_balance_matches_l_delta_i():
    time = np.linspace(0.0, 1e-3, 1001)
    current = 1.0 + 4000.0 * time
    voltage = np.full_like(time, 47e-6 * 4000.0)
    window = SteadyStateWindow(
        start_time_s=0.0,
        end_time_s=1e-3,
        complete_cycles=1,
        voltage_mean_change_ratio=0.0,
        current_mean_change_ratio=0.0,
        ripple_change_ratio=0.0,
        status=STATUS_STEADY_STATE,
    )
    payload = inductor_volt_second_balance(time, voltage, current, 47e-6, window)
    assert payload["expected_l_delta_i_v_s"] == pytest.approx(1.88e-4, rel=1e-6)
    assert abs(payload["relative_error"]) < 1e-9


def test_charge_balance_matches_c_delta_v():
    time = np.linspace(0.0, 1e-3, 1001)
    voltage = 5.0 + 100.0 * time
    current = np.full_like(time, 100e-6 * 100.0)
    window = SteadyStateWindow(
        start_time_s=0.0,
        end_time_s=1e-3,
        complete_cycles=1,
        voltage_mean_change_ratio=0.0,
        current_mean_change_ratio=0.0,
        ripple_change_ratio=0.0,
        status=STATUS_STEADY_STATE,
    )
    payload = capacitor_charge_balance(time, current, voltage, 100e-6, window)
    assert payload["expected_c_delta_v_c"] == pytest.approx(1e-5, rel=1e-6)
    assert abs(payload["relative_error"]) < 1e-9


def test_balance_requires_valid_window_and_parameters():
    time = np.linspace(0.0, 1e-3, 101)
    current = np.ones_like(time)
    window = SteadyStateWindow(
        start_time_s=0.0,
        end_time_s=1e-3,
        complete_cycles=1,
        voltage_mean_change_ratio=0.0,
        current_mean_change_ratio=0.0,
        ripple_change_ratio=0.0,
        status=STATUS_STEADY_STATE,
    )
    with pytest.raises(ValueError):
        inductor_volt_second_balance(time, current, current, 0.0, window)
    with pytest.raises(ValueError):
        capacitor_charge_balance(time, current, current, 100e-6, "bad-window")
