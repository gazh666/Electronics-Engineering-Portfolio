"""波形时间轴对齐测试（仅插值与统计，不运行 SPICE）。"""

from __future__ import annotations

import numpy as np
import pytest

from validation.waveform_alignment import (
    AlignmentResult,
    align_waveforms,
    alignment_is_usable,
    common_interval,
    cycle_mean_waveform,
    pwm_cycle_average,
    shift_to_event,
)


def test_common_interval_intersects_overlap():
    time_a = np.linspace(0.0, 10.0, 11)
    time_b = np.linspace(2.0, 8.0, 11)
    start, end = common_interval(time_a, time_b)
    assert start == pytest.approx(2.0)
    assert end == pytest.approx(8.0)


def test_common_interval_rejects_disjoint_waveforms():
    with pytest.raises(ValueError):
        common_interval([0.0, 1.0], [2.0, 3.0])


def test_align_waveforms_interpolates_onto_common_grid():
    reference_time = np.linspace(0.0, 1.0, 101)
    candidate_time = np.linspace(0.5, 1.5, 101)
    result = align_waveforms(
        reference_time,
        reference_time,
        candidate_time,
        candidate_time,
        point_count=11,
    )
    assert result.time_s.shape == (11,)
    assert result.reference.shape == (11,)
    assert result.candidate.shape == (11,)
    assert result.time_s[0] == pytest.approx(0.5)
    assert result.time_s[-1] == pytest.approx(1.0)
    # 两个波形在公共区间内都等于时间本身，插值结果应与网格一致。
    assert np.allclose(result.reference, result.time_s)
    assert np.allclose(result.candidate, result.time_s)
    assert result.max_time_shift_s == pytest.approx(0.0)
    payload = result.to_dict()
    assert payload["duration_s"] == pytest.approx(0.5)
    assert payload["point_count"] == 11
    assert payload["method"] == "linear_common_interval"


def test_align_waveforms_requires_two_points():
    with pytest.raises(ValueError):
        align_waveforms([0.0, 1.0], [0.0, 1.0], [0.0, 1.0], [0.0, 1.0], point_count=1)


def test_shift_to_event_moves_event_to_zero():
    time = np.linspace(1.0, 5.0, 9)
    values = np.arange(9, dtype=float)
    shifted_time, shifted_values = shift_to_event(time, values, 3.0)
    assert shifted_time[0] == pytest.approx(-2.0)
    assert shifted_time[-1] == pytest.approx(2.0)
    assert np.allclose(shifted_values, values)


def test_shift_to_event_rejects_event_outside_interval():
    with pytest.raises(ValueError):
        shift_to_event([1.0, 2.0, 3.0], [0.0, 1.0, 2.0], 5.0)


def test_pwm_cycle_average_returns_phase_means():
    frequency = 1000.0
    period = 1.0 / frequency
    time = np.arange(0.0, 2.0 * period, 1e-5)
    phase = np.mod(time, period) / period
    values = (phase < 0.5).astype(float)
    averaged = pwm_cycle_average(time, values, frequency, samples_per_cycle=4)
    assert averaged["phase_fraction"].shape == (4,)
    assert np.allclose(averaged["phase_fraction"], [0.125, 0.375, 0.625, 0.875])
    assert averaged["cycle_mean"][0] == pytest.approx(1.0)
    assert averaged["cycle_mean"][1] == pytest.approx(1.0)
    assert averaged["cycle_mean"][2] == pytest.approx(0.0)
    assert averaged["cycle_mean"][3] == pytest.approx(0.0)
    assert int(averaged["sample_count"].sum()) == time.size
    assert np.all(averaged["sample_count"] > 0)


def test_pwm_cycle_average_rejects_bad_frequency():
    with pytest.raises(ValueError):
        pwm_cycle_average([0.0, 1e-3], [0.0, 1.0], 0.0)


def test_cycle_mean_waveform_tracks_cycle_envelope():
    period = 1e-3
    time = np.arange(0.0, 3.0 * period, period / 10.0)
    values = np.floor(time / period)
    envelope = cycle_mean_waveform(time, values, 1000.0)
    assert np.array_equal(envelope["cycle_index"], np.array([0, 1, 2]))
    assert np.allclose(envelope["cycle_mean"], [0.0, 1.0, 2.0])
    assert np.allclose(envelope["cycle_center_s"], [0.5e-3, 1.5e-3, 2.5e-3])


def test_alignment_is_usable_for_matching_grids():
    time = np.linspace(0.0, 1.0, 101)
    result = align_waveforms(time, time, time, time, point_count=101)
    assert alignment_is_usable(result) is True


def test_alignment_is_usable_false_for_large_shift():
    reference_time = np.array([0.0, 1.0])
    candidate_time = np.array([0.005, 2.0])
    result = align_waveforms(reference_time, reference_time, candidate_time, candidate_time, point_count=5)
    assert result.max_time_shift_s / (result.end_s - result.start_s) > 0.01
    assert alignment_is_usable(result) is False


def test_alignment_is_usable_false_for_empty_overlap():
    result = AlignmentResult(
        time_s=np.array([0.0, 1.0]),
        reference=np.array([0.0, 1.0]),
        candidate=np.array([0.0, 1.0]),
        start_s=1.0,
        end_s=1.0,
        point_count=2,
        max_time_shift_s=0.0,
        method="manual",
    )
    assert alignment_is_usable(result) is False
