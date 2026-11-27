"""RC 滤波理论与真实 ngspice AC 测试（Task 10/11/12/36）。"""

from __future__ import annotations

import math

import numpy as np
import pytest

from analysis.filter_response import (
    FilterAnalysisError,
    extract_ac_metrics,
    first_order_magnitude,
    theoretical_attenuation_db,
)
from circuits.rc_filter import (
    RCFilterConfig,
    RCFilterError,
    attenuation_db,
    extract_cutoff,
    run_ac_response,
    theoretical_cutoff_hz,
    theoretical_rise_time_s,
    theoretical_settling_time_s,
)


def test_theoretical_cutoff_and_times():
    cutoff = theoretical_cutoff_hz(47.0, 0.22e-6)
    assert cutoff == pytest.approx(7696.0804, rel=1e-5)
    tau = 2.0 * 47.0 * 0.22e-6
    assert theoretical_rise_time_s(47.0, 0.22e-6) == pytest.approx(2.197 * tau, rel=1e-12)
    assert theoretical_settling_time_s(47.0, 0.22e-6) == pytest.approx(4.605 * tau, rel=1e-12)


def test_first_order_magnitude_at_cutoff():
    cutoff = theoretical_cutoff_hz(47.0, 0.22e-6)
    magnitude = float(first_order_magnitude(np.array([cutoff]), cutoff)[0])
    assert magnitude == pytest.approx(1.0 / math.sqrt(2.0), rel=1e-12)


def test_theoretical_attenuation_100khz():
    cutoff = theoretical_cutoff_hz(47.0, 0.22e-6)
    assert theoretical_attenuation_db(100e3, cutoff) == pytest.approx(-22.300255, rel=1e-5)


def test_real_ngspice_ac_matches_theory():
    config = RCFilterConfig(47.0, 0.22e-6)
    data = run_ac_response(config, start_hz=100.0, stop_hz=1e6, points_per_decade=40)
    cutoff = extract_cutoff(data["frequency_hz"], data["transfer"])
    assert cutoff == pytest.approx(config.cutoff_hz, rel=0.01)
    measured_100k = attenuation_db(data["frequency_hz"], data["gain_db"], 100e3)
    assert measured_100k == pytest.approx(theoretical_attenuation_db(100e3, config.cutoff_hz), abs=0.1)


def test_extract_ac_metrics_keys():
    config = RCFilterConfig(47.0, 0.22e-6)
    data = run_ac_response(config, start_hz=100.0, stop_hz=1e6, points_per_decade=20)
    metrics = extract_ac_metrics(
        data["frequency_hz"], data["gain_db"], data["phase_deg"], cutoff_hz=config.cutoff_hz
    )
    assert metrics["cutoff_relative_error"] == pytest.approx(0.0, abs=0.01)
    assert metrics["attenuation_100000hz_db"] < -20.0


def test_phase_at_cutoff_is_minus_45_degrees():
    # 理论一阶低通在截止频率处相位为 -45°
    cutoff = theoretical_cutoff_hz(47.0, 0.22e-6)
    ratio = cutoff / cutoff
    assert -math.degrees(math.atan(ratio)) == pytest.approx(-45.0)


def test_invalid_config_rejected():
    with pytest.raises(RCFilterError):
        RCFilterConfig(0.0, 0.22e-6)
    with pytest.raises(RCFilterError):
        RCFilterConfig(47.0, 0.0)
    with pytest.raises(FilterAnalysisError):
        theoretical_attenuation_db(0.0, 100.0)
