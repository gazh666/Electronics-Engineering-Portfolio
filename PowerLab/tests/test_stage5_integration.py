"""第五阶段端到端集成测试：真实 SPICE 波形 → 统一分析器 → 判定。"""

from __future__ import annotations

import pytest

from circuits.nonideal_config import load_nonideal_buck_config
from scripts.performance_common import run_performance_case


@pytest.fixture(scope="module")
def baseline_e():
    config = load_nonideal_buck_config()
    return config, run_performance_case(config, variant="E")


@pytest.fixture(scope="module")
def baseline_a():
    config = load_nonideal_buck_config()
    return config, run_performance_case(config, variant="A", include_spectrum=False)


def test_baseline_e_metrics_come_from_spice(baseline_e):
    config, result = baseline_e
    assert result.variant == "E"
    assert result.data_source == "spice_simulation"
    assert result.overall_status == "PASS"
    assert result.quality["passed"] is True
    assert result.quality["error_count"] == 0

    assert 4.5 < result.numeric("output_voltage_mean_v") < 4.8
    assert 0.010 < result.numeric("output_voltage_ripple_vpp") < 0.030
    assert 1.5 < result.numeric("inductor_current_mean_a") < 2.2
    assert 90.0 < result.numeric("efficiency_system_percent") < 95.0
    assert abs(result.numeric("power_residual_ratio")) < 0.05
    assert result.numeric("switching_frequency_hz") == pytest.approx(100e3, rel=1e-3)
    assert abs(result.numeric("pwm_duty_absolute_error")) < 5e-3


def test_baseline_e_switching_is_reported_not_resolved(baseline_e):
    _config, result = baseline_e
    assert result.numeric("switching_edge_resolution_ok") == 0.0
    assert result.numeric("switching_power_w") == pytest.approx(0.020, rel=5e-2)
    details = result.switching_details
    assert details["turn_on"]["status"] == "NOT_RESOLVED"
    assert details["turn_off"]["status"] == "NOT_RESOLVED"
    assert "W_EDGE_NOT_RESOLVED" in result.quality["warning_codes"]


def test_baseline_e_spectrum_is_trusted_and_resolved(baseline_e):
    _config, result = baseline_e
    spectrum = result.spectrum
    assert spectrum is not None
    assert spectrum.resample.trusted_max_hz >= 1e6
    assert spectrum.resample.complete_cycles >= 50
    assert spectrum.resample.frequency_resolution_hz > 0
    assert result.numeric("spectrum_frequency_resolution_hz") == pytest.approx(
        spectrum.resample.frequency_resolution_hz, rel=1e-9
    )
    assert len(result.harmonic_entries) == 10
    assert all(entry["status"] == "AVAILABLE" for entry in result.harmonic_entries)
    assert 10.0 < sum(
        entry["amplitude_rms"] ** 2 for entry in result.harmonic_entries[1:]
    ) ** 0.5 / result.harmonic_entries[0]["amplitude_rms"] * 100.0 < 20.0


def test_baseline_a_reports_switching_not_applicable(baseline_a):
    _config, result = baseline_a
    assert result.variant == "A"
    assert result.overall_status == "PASS"
    assert result.numeric("switching_power_w") is None
    assert result.numeric("switching_edge_resolution_ok") is None
    assert result.numeric("output_voltage_mean_v") > 0.0


def test_run_ids_are_unique_per_execution(baseline_e, baseline_a):
    _, result_e = baseline_e
    _, result_a = baseline_a
    assert result_e.run_id != result_a.run_id
    assert result_e.run_id and result_a.run_id
    assert result_e.run_id.count("_") == 2
