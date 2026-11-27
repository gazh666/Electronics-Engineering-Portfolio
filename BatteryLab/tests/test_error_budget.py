"""工程误差预算与限值比较测试（Task 27/34/36）。"""

from __future__ import annotations

import pytest

from analysis.error_budget import (
    BudgetItem,
    current_error_budget,
    resistor_mismatch_worst_case_error,
    summarize_budget,
    temperature_error_budget,
    voltage_error_budget,
)
from analysis.sensing_validation import adc_checks, check, summarize_checks
from sensing.adc import ADCConfig


def test_summarize_budget_linear_and_rss():
    items = [
        BudgetItem("a", 3.0, "V", "analytical_theory", "a"),
        BudgetItem("b", -4.0, "V", "analytical_theory", "b"),
    ]
    summary = summarize_budget(items, "V")
    assert summary["worst_case_linear_sum"] == pytest.approx(7.0)
    assert summary["rss_estimate"] == pytest.approx(5.0)
    assert summary["dominant_item"] == "b"


def test_resistor_mismatch_grows_with_tolerance_and_common_mode():
    kwargs = dict(
        r1_ohm=100_000.0,
        r2_ohm=50_000.0,
        r3_ohm=100_000.0,
        r4_ohm=50_000.0,
        reference_v=0.2,
        differential_v=3.6,
        common_mode_v=9.7,
    )
    tight = resistor_mismatch_worst_case_error(tolerance_percent=0.1, **kwargs)
    loose = resistor_mismatch_worst_case_error(tolerance_percent=1.0, **kwargs)
    low_cm = resistor_mismatch_worst_case_error(
        tolerance_percent=0.1,
        **{**kwargs, "common_mode_v": 1.8},
    )
    assert 0.015 < tight < 0.030
    assert loose == pytest.approx(10.0 * tight, rel=0.02)
    assert tight > low_cm


def test_voltage_budget_structure():
    summary = voltage_error_budget(
        r1_ohm=100_000.0,
        r2_ohm=50_000.0,
        r3_ohm=100_000.0,
        r4_ohm=50_000.0,
        reference_v=0.2,
        adc_config=ADCConfig(3.3, 12),
        cell_voltage_v=4.25,
        common_mode_v=9.7,
        resistor_tolerance_percent=0.1,
        opamp_offset_v=0.3e-3,
        adc_offset_v=1e-3,
        adc_gain_error_fraction=1e-4,
        adc_noise_v=0.1e-3,
        reference_tolerance_percent=0.05,
    )
    names = [item["name"] for item in summary["items"]]
    assert "四电阻失配（含增益与共模）" in names
    assert "ADC 量化" in names
    assert summary["worst_case_linear_sum"] > summary["rss_estimate"] > 0.0


def test_current_budget_structure():
    summary = current_error_budget(
        shunt_ohm=0.01,
        amplifier_gain=50.0,
        reference_v=1.65,
        adc_config=ADCConfig(3.3, 12),
        current_a=2.5,
        shunt_tolerance_percent=1.0,
        shunt_tcr_ppm_per_c=50.0,
        temperature_delta_c=20.0,
        input_offset_v=25e-6,
        gain_error_fraction=0.002,
        zero_reference_error_v=1e-3,
        adc_offset_v=1e-3,
        adc_gain_error_fraction=1e-4,
        adc_noise_v=1e-4,
        reference_tolerance_percent=0.05,
    )
    names = [item["name"] for item in summary["items"]]
    assert "分流电阻容差" in names
    assert "放大器输入失调" in names
    assert summary["unit"] == "A"
    assert summary["worst_case_linear_sum"] > 0.0


def test_temperature_budget_marks_self_heating_unverified():
    summary = temperature_error_budget(
        r25_ohm=10_000.0,
        beta_k=3950.0,
        pullup_ohm=10_000.0,
        excitation_v=3.3,
        temperature_c=25.0,
        adc_config=ADCConfig(3.3, 12),
        r25_tolerance_percent=1.0,
        beta_tolerance_percent=1.0,
        pullup_tolerance_percent=1.0,
    )
    assert summary["unit"] == "degC"
    assert summary["unverified_items"][0]["name"] == "NTC 自热"
    assert summary["unverified_items"][0]["evidence"] == "NOT_VERIFIED"
    assert summary["worst_case_linear_sum"] > 0.0


def test_adc_check_absorbs_binary_float_error_without_changing_limit():
    value = 0.5000000000001654
    assert check("adc", value, 0.5, "<=")["status"] == "FAIL"
    result = adc_checks(max_quantization_error_lsb=value, monotonic=True, limits={"ideal_consistency": {"adc_quantization_error_lsb": 0.5}})
    assert all(item["status"] == "PASS" for item in result)
    assert result[0]["threshold"] == 0.5


def test_summarize_checks_counts():
    checks = [check("a", 1, 2, "<="), check("b", 3, 2, "<=")]
    summary = summarize_checks(checks)
    assert summary["passed"] == 1
    assert summary["failed"] == 1
    assert summary["overall"] == "FAIL"
