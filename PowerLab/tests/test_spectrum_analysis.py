"""频谱重采样、可信频段与幅值谱测试。"""

from __future__ import annotations

import numpy as np
import pytest

from analysis.spectrum_analysis import (
    analyze_spectrum,
    choose_sample_rate,
    resample_uniform,
)

F_SW = 100e3
PERIOD_S = 1.0 / F_SW


def _uniform_signal(cycles: int = 100, points_per_cycle: int = 400, amplitude: float = 0.1):
    time = np.arange(0, cycles * points_per_cycle + 1, dtype=float) * (
        PERIOD_S / points_per_cycle
    )
    values = 5.0 + amplitude * np.sin(2.0 * np.pi * F_SW * time)
    return time, values


def test_choose_sample_rate_scales_with_per_cycle():
    rate, count = choose_sample_rate(1e-3, F_SW, 200, 1_000_000)
    assert rate == pytest.approx(20e6)
    assert count == 20_000

    capped_rate, capped_count = choose_sample_rate(1e-3, F_SW, 200, 1024)
    assert capped_count == 1024
    assert capped_rate == pytest.approx(1024 / 1e-3)

    with pytest.raises(ValueError):
        choose_sample_rate(0.0, F_SW, 200, 1_000_000)
    with pytest.raises(ValueError):
        choose_sample_rate(1e-3, F_SW, 4, 1_000_000)
    with pytest.raises(ValueError):
        choose_sample_rate(1e-3, F_SW, 200, 100)
    with pytest.raises(ValueError):
        choose_sample_rate(1e-6, F_SW, 200, 1_000_000)


def test_resample_uniform_linear_interpolation_is_exact_for_ramp():
    time = np.array([0.0, 1e-3, 2e-3])
    values = np.array([0.0, 1.0, 2.0])
    uniform_time, uniform_values, info = resample_uniform(
        time,
        values,
        start_s=0.0,
        end_s=2e-3,
        sample_rate_hz=1e6,
        point_count=2000,
    )
    assert uniform_time[0] == pytest.approx(0.0)
    assert uniform_values[-1] == pytest.approx(1.999, abs=1e-9)
    assert np.allclose(uniform_values, uniform_time * 1000.0, atol=1e-9)
    assert info.interpolation == "linear"
    assert info.frequency_resolution_hz == pytest.approx(1e6 / 2000)
    assert info.nyquist_hz == pytest.approx(5e5)
    assert info.complete_cycles == 0


def test_resample_rejects_out_of_range_and_bad_grid():
    time = np.linspace(0.0, 1e-3, 1001)
    values = np.sin(time)
    with pytest.raises(ValueError):
        resample_uniform(time, values, start_s=-1e-6, end_s=1e-3, sample_rate_hz=1e6, point_count=1000)
    with pytest.raises(ValueError):
        resample_uniform(time, values, start_s=0.0, end_s=1e-3, sample_rate_hz=1e6, point_count=2000)
    with pytest.raises(ValueError):
        resample_uniform(time, values, start_s=0.0, end_s=1e-3, sample_rate_hz=0.0, point_count=1000)


def test_analyze_spectrum_recovers_fundamental_amplitude():
    time, values = _uniform_signal()
    spectrum = analyze_spectrum(
        time,
        values,
        start_s=float(time[0]),
        end_s=float(time[-1]),
        switching_frequency_hz=F_SW,
        samples_per_cycle=200,
    )
    assert spectrum.dc_value == pytest.approx(5.0, abs=1e-6)
    assert spectrum.resample.complete_cycles == 100
    assert spectrum.resample.frequency_resolution_hz == pytest.approx(1000.0, rel=1e-9)
    assert spectrum.amplitude_at(F_SW) == pytest.approx(0.1, rel=2e-2)
    assert spectrum.resampled_values is not None
    assert spectrum.metadata()["complete_cycles"] == 100
    assert max(spectrum.amplitude_peak) == pytest.approx(0.1, rel=2e-2)
    for array in (spectrum.frequency_hz, spectrum.amplitude_peak, spectrum.psd):
        assert np.isfinite(array).all()


def test_analyze_spectrum_reports_trusted_band_limited_by_raw_gap():
    time = np.linspace(0.0, 100 * PERIOD_S, 5000)
    values = 5.0 + 0.1 * np.sin(2.0 * np.pi * F_SW * time)
    spectrum = analyze_spectrum(
        time,
        values,
        start_s=0.0,
        end_s=100 * PERIOD_S,
        switching_frequency_hz=F_SW,
        samples_per_cycle=200,
    )
    expected_trusted = min(
        spectrum.resample.nyquist_hz, 0.5 / spectrum.resample.max_step_s
    )
    assert spectrum.resample.trusted_max_hz == pytest.approx(expected_trusted, rel=1e-12)


def test_analyze_spectrum_rejects_unknown_window():
    time, values = _uniform_signal(cycles=10)
    with pytest.raises(ValueError):
        analyze_spectrum(
            time,
            values,
            start_s=0.0,
            end_s=10 * PERIOD_S,
            switching_frequency_hz=F_SW,
            window_name="triangle",
        )


def _task_validation_signal(cycles: int = 1000, points_per_cycle: int = 100):
    fs = 100000.0
    time = np.arange(cycles * points_per_cycle + 1) / fs
    values = (
        5.0
        + 0.02 * np.sin(2.0 * np.pi * 1000.0 * time)
        + 0.005 * np.sin(2.0 * np.pi * 3000.0 * time)
    )
    return time, values, fs


def test_task_19_known_signal_fft_validation():
    time, values, _fs = _task_validation_signal()
    spectrum = analyze_spectrum(
        time,
        values,
        start_s=float(time[0]),
        end_s=float(time[-1]),
        switching_frequency_hz=1000.0,
        samples_per_cycle=100,
    )
    assert spectrum.dc_value == pytest.approx(5.0, abs=1e-5)
    assert spectrum.amplitude_at(1000.0) == pytest.approx(0.02, rel=5e-3)
    assert spectrum.amplitude_at(3000.0) == pytest.approx(0.005, rel=5e-3)
    assert spectrum.resample.complete_cycles >= 990
    error = abs(spectrum.amplitude_at(1000.0) - 0.02) / 0.02
    assert error < 5e-4


def test_parseval_matches_time_domain_variance():
    time, values, _fs = _task_validation_signal()
    spectrum = analyze_spectrum(
        time,
        values,
        start_s=float(time[0]),
        end_s=float(time[-1]),
        switching_frequency_hz=1000.0,
        samples_per_cycle=100,
        window_name="boxcar",
    )
    df = spectrum.resample.frequency_resolution_hz
    psd_integral = float(np.sum(spectrum.psd) * df)
    variance = float(np.var(spectrum.resampled_values))
    assert psd_integral == pytest.approx(variance, rel=1e-9)


def test_odd_and_even_fft_lengths_are_supported():
    time, values, _fs = _task_validation_signal()
    even = analyze_spectrum(
        time,
        values,
        start_s=float(time[0]),
        end_s=float(time[-1]),
        switching_frequency_hz=1000.0,
        samples_per_cycle=100,
        maximum_samples=10001,
    )
    odd = analyze_spectrum(
        time,
        values,
        start_s=float(time[0]),
        end_s=float(time[-1]),
        switching_frequency_hz=1000.0,
        samples_per_cycle=100,
        maximum_samples=9999,
    )
    assert even.resample.resampled_points == 10001
    assert odd.resample.resampled_points == 9999
    assert even.amplitude_at(1000.0) == pytest.approx(0.02, rel=5e-3)
    assert odd.amplitude_at(1000.0) == pytest.approx(0.02, rel=5e-3)


def test_pure_dc_has_no_visible_ac_peak():
    time = np.linspace(0.0, 10 * PERIOD_S, 2001)
    values = np.full_like(time, 5.0)
    spectrum = analyze_spectrum(
        time,
        values,
        start_s=0.0,
        end_s=10 * PERIOD_S,
        switching_frequency_hz=F_SW,
        samples_per_cycle=200,
    )
    assert spectrum.dc_value == pytest.approx(5.0, abs=1e-12)
    assert np.max(spectrum.amplitude_peak[1:]) < 1e-10


def test_noninteger_cycles_still_recover_amplitude():
    time = np.arange(10400) / 100000.0
    values = 5.0 + 0.02 * np.sin(2.0 * np.pi * 1000.0 * time)
    spectrum = analyze_spectrum(
        time,
        values,
        start_s=0.0,
        end_s=float(time[-1]),
        switching_frequency_hz=1000.0,
        samples_per_cycle=100,
    )
    assert spectrum.resample.complete_cycles == 103
    assert spectrum.amplitude_at(1000.0) == pytest.approx(0.02, rel=5e-3)


def test_alias_risk_is_bounded_by_trusted_band():
    time = np.arange(4000) / 40000.0
    values = 5.0 + 0.02 * np.sin(2.0 * np.pi * 25000.0 * time)
    spectrum = analyze_spectrum(
        time,
        values,
        start_s=0.0,
        end_s=float(time[-1]),
        switching_frequency_hz=1000.0,
        samples_per_cycle=40,
    )
    assert spectrum.resample.trusted_max_hz <= spectrum.resample.nyquist_hz
    assert spectrum.resample.nyquist_hz == pytest.approx(20000.0)
    # 25 kHz 超过 20 kHz Nyquist，在 15 kHz 处出现混叠分量。
    assert spectrum.amplitude_at(15000.0) == pytest.approx(0.02, rel=1e-1)


def test_spectrum_rejects_nan_and_infinity():
    time, values = _uniform_signal(cycles=10)
    for bad in (np.nan, np.inf):
        corrupted = values.copy()
        corrupted[5] = bad
        with pytest.raises(ValueError):
            analyze_spectrum(
                time,
                corrupted,
                start_s=0.0,
                end_s=10 * PERIOD_S,
                switching_frequency_hz=F_SW,
                samples_per_cycle=200,
            )
