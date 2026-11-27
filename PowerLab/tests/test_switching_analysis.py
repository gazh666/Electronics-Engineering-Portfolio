"""开关边沿、延迟与开关能量测试（合成 VDS/栅极波形）。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from analysis.switching_analysis import (
    analyze_switching,
    interpolate_crossing,
)

PERIOD_S = 10e-6


def test_interpolate_crossing_linear_ramp():
    time = np.array([0.0, 1.0, 2.0, 3.0])
    values = np.array([0.0, 2.0, 8.0, 10.0])
    assert interpolate_crossing(time, values, 5.0, rising=True) == pytest.approx(1.5)
    assert interpolate_crossing(time, values, 5.0, rising=False) is None
    assert interpolate_crossing(time, values, 1.0, rising=True) == pytest.approx(0.5)
    with pytest.raises(ValueError):
        interpolate_crossing(time, values[:-1], 5.0, rising=True)


def _switching_frame(cycles: int = 10, samples_per_cycle: int = 2000, ramp_s: float = 100e-9):
    step = PERIOD_S / samples_per_cycle
    time = np.arange(0.0, cycles * PERIOD_S, step)
    phase = np.mod(time, PERIOD_S)
    gate = np.where((phase >= 0.10 * PERIOD_S) & (phase < 0.50 * PERIOD_S), 10.0, 0.0)

    fall_end = 0.15 * PERIOD_S + ramp_s
    rise_end = 0.50 * PERIOD_S + ramp_s
    vds = np.full_like(time, 11.8)
    falling = (phase >= 0.15 * PERIOD_S) & (phase < fall_end)
    vds[falling] = 11.8 + (0.2 - 11.8) * (
        (phase[falling] - 0.15 * PERIOD_S) / ramp_s
    )
    low = (phase >= fall_end) & (phase < 0.50 * PERIOD_S)
    vds[low] = 0.2
    rising = (phase >= 0.50 * PERIOD_S) & (phase < rise_end)
    vds[rising] = 0.2 + (11.8 - 0.2) * ((phase[rising] - 0.50 * PERIOD_S) / ramp_s)

    drain = np.where((phase >= 0.15 * PERIOD_S) & (phase < 0.51 * PERIOD_S), 1.0, 0.0)
    return pd.DataFrame(
        {
            "time_s": time,
            "mosfet_vds_v": vds,
            "mosfet_vgs_v": gate,
            "drive_vgs_command_v": gate,
            "mosfet_drain_terminal_current_a": drain,
        }
    )


def test_analyze_switching_resolves_edges_and_delays():
    frame = _switching_frame()
    analysis = analyze_switching(frame, minimum_edge_samples=5)
    assert analysis.low_threshold_v == pytest.approx(0.2 + 0.1 * (11.8 - 0.2), abs=1e-6)
    assert analysis.high_threshold_v == pytest.approx(0.2 + 0.9 * (11.8 - 0.2), abs=1e-6)
    assert analysis.turn_on.status == "AVAILABLE"
    assert analysis.turn_off.status == "AVAILABLE"
    assert analysis.turn_on.duration_s == pytest.approx(80e-9, rel=5e-2)
    assert analysis.turn_off.duration_s == pytest.approx(80e-9, rel=5e-2)
    assert analysis.turn_on_delay_s == pytest.approx(0.05 * PERIOD_S, rel=5e-2)
    assert -1e-9 <= analysis.turn_off_delay_s <= 200e-9
    assert analysis.edge_count == 10
    assert analysis.cycle_energy_j is not None and analysis.cycle_energy_j > 0
    assert analysis.switching_power_w is not None and analysis.switching_power_w > 0
    assert analysis.to_dict()["data_source"] == "spice_derived"


def test_analyze_switching_marks_unresolved_with_coarse_samples():
    frame = _switching_frame(samples_per_cycle=100, ramp_s=20e-9)
    analysis = analyze_switching(frame, minimum_edge_samples=5)
    assert analysis.turn_on.status == "NOT_RESOLVED"
    assert analysis.turn_off.status == "NOT_RESOLVED"
    assert analysis.turn_on.note


def test_analyze_switching_rejects_bad_inputs():
    frame = _switching_frame()
    with pytest.raises(ValueError):
        analyze_switching(frame.drop(columns=["mosfet_vds_v"]))
    with pytest.raises(ValueError):
        analyze_switching(frame, low_ratio=0.9, high_ratio=0.1)
    flat = frame.copy()
    flat["mosfet_vds_v"] = 5.0
    with pytest.raises(ValueError):
        analyze_switching(flat)
    with pytest.raises(ValueError):
        analyze_switching("not-a-frame")
