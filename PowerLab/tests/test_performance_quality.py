"""数据质量检查测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from analysis.performance_models import (
    DataSource,
    MetricStatus,
    PerformanceMetric,
)
from analysis.performance_quality import (
    QualityIssue,
    check_metric_consistency,
    check_power_residual,
    check_spectrum,
    check_steady_state,
    check_switching,
    check_waveform_frame,
    quality_summary,
)
from analysis.switching_analysis import EdgeTiming, SwitchingAnalysis


def _frame() -> pd.DataFrame:
    time = np.linspace(0.0, 1e-4, 101)
    return pd.DataFrame({"time_s": time, "vout_v": np.full_like(time, 5.0)})


def test_check_waveform_frame_accepts_clean_frame():
    assert check_waveform_frame(_frame(), ["time_s", "vout_v"]) == []


def test_check_waveform_frame_detects_missing_and_invalid():
    issues = check_waveform_frame(_frame(), ["time_s", "missing"])
    assert [issue.code for issue in issues] == ["E_MISSING_WAVEFORM"]

    nonfinite = _frame()
    nonfinite.loc[10, "vout_v"] = float("nan")
    codes = [issue.code for issue in check_waveform_frame(nonfinite, ["time_s", "vout_v"])]
    assert "E_NONFINITE_DATA" in codes

    reversed_time = _frame()
    reversed_time.loc[5, "time_s"] = reversed_time.loc[4, "time_s"]
    codes = [issue.code for issue in check_waveform_frame(reversed_time, ["time_s"])]
    assert "E_TIME_AXIS_INVALID" in codes

    short = pd.DataFrame({"time_s": [0.0], "vout_v": [1.0]})
    codes = [issue.code for issue in check_waveform_frame(short, ["time_s"])]
    assert "E_TIME_AXIS_INVALID" in codes

    assert check_waveform_frame("not-a-frame", ["time_s"])[0].code == "E_MISSING_WAVEFORM"


def _metric(name: str, value: float, unit: str = "V") -> PerformanceMetric:
    return PerformanceMetric(
        name=name,
        value=value,
        unit=unit,
        status=MetricStatus.AVAILABLE,
        data_source=DataSource.SPICE_DERIVED,
        method="test",
    )


def test_check_metric_consistency_accepts_consistent_metrics():
    metrics = {
        "output_voltage_max_v": _metric("output_voltage_max_v", 5.01),
        "output_voltage_min_v": _metric("output_voltage_min_v", 4.99),
        "output_voltage_ripple_vpp": _metric("output_voltage_ripple_vpp", 0.02),
        "output_voltage_mean_v": _metric("output_voltage_mean_v", 5.0),
        "efficiency_power_stage_percent": _metric(
            "efficiency_power_stage_percent", 95.0, "%"
        ),
    }
    assert check_metric_consistency(metrics) == []


def test_check_metric_consistency_flags_problems():
    metrics = {
        "output_voltage_max_v": _metric("output_voltage_max_v", 4.98),
        "output_voltage_min_v": _metric("output_voltage_min_v", 5.02),
        "output_voltage_ripple_vpp": _metric("output_voltage_ripple_vpp", -0.01),
        "output_voltage_mean_v": _metric("output_voltage_mean_v", 6.0),
        "efficiency_power_stage_percent": _metric(
            "efficiency_power_stage_percent", 120.0, "%"
        ),
    }
    codes = {issue.code for issue in check_metric_consistency(metrics)}
    assert "E_METRIC_INCONSISTENT" in codes
    assert "E_NEGATIVE_RIPPLE" in codes


def test_check_metric_consistency_flags_missing_unit_and_value():
    missing_unit = PerformanceMetric(
        "custom", 1.0, "", MetricStatus.AVAILABLE, DataSource.SPICE_DERIVED, "test"
    )
    missing_value = PerformanceMetric(
        "empty", None, "V", MetricStatus.AVAILABLE, DataSource.SPICE_DERIVED, "test"
    )
    codes = {
        issue.code
        for issue in check_metric_consistency(
            {"custom": missing_unit, "empty": missing_value}
        )
    }
    assert "E_UNIT_MISMATCH" in codes
    assert "E_METRIC_INCONSISTENT" in codes


def test_check_power_residual_threshold():
    assert check_power_residual(None) == []
    assert check_power_residual(0.01, maximum_ratio=0.05) == []
    issues = check_power_residual(0.2, maximum_ratio=0.05)
    assert [issue.code for issue in issues] == ["E_POWER_RESIDUAL_EXCESSIVE"]


def test_check_steady_state_requires_achievement():
    assert check_steady_state({"achieved": True}) == []
    issues = check_steady_state({"achieved": False})
    assert [issue.code for issue in issues] == ["E_NOT_SETTLED"]


def _switching(turn_on_status: str, turn_off_status: str) -> SwitchingAnalysis:
    edge_on = EdgeTiming("turn_on_vds_fall", turn_on_status, None, None, None, 1, None, "note-on")
    edge_off = EdgeTiming("turn_off_vds_rise", turn_off_status, None, None, None, 1, None, "note-off")
    return SwitchingAnalysis(
        vds_low_v=0.2,
        vds_high_v=11.8,
        low_threshold_v=1.36,
        high_threshold_v=10.64,
        turn_on=edge_on,
        turn_off=edge_off,
        turn_on_delay_s=None,
        turn_off_delay_s=None,
        edge_count=0,
        cycle_energy_j=None,
        turn_on_energy_j=None,
        turn_off_energy_j=None,
        switching_power_w=None,
    )


def test_check_switching_warns_for_unresolved_edges():
    assert check_switching(None) == []
    assert check_switching(_switching("AVAILABLE", "AVAILABLE")) == []
    issues = check_switching(_switching("NOT_RESOLVED", "NOT_RESOLVED"))
    assert [issue.code for issue in issues] == ["W_EDGE_NOT_RESOLVED", "W_EDGE_NOT_RESOLVED"]


def test_check_spectrum_requires_data_and_cycles():
    assert check_spectrum(None, preferred_cycles=10) == []


def test_quality_summary_separates_errors_and_warnings():
    summary = quality_summary(
        [
            QualityIssue("E_X", "ERROR", "bad"),
            QualityIssue("W_Y", "WARNING", "note"),
            QualityIssue("W_Y", "WARNING", "note again"),
        ]
    )
    assert summary["passed"] is False
    assert summary["error_count"] == 1
    assert summary["warning_count"] == 2
    assert summary["error_codes"] == ["E_X"]
    assert summary["warning_codes"] == ["W_Y"]
    assert len(summary["issues"]) == 3
    assert quality_summary([])["passed"] is True
