"""性能数据模型与 YAML 配置加载测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from analysis.performance_models import (
    DataSource,
    MetricStatus,
    PerformanceMetric,
    PerformanceResult,
    VoltageMetrics,
    load_analysis_config,
    load_cases,
    load_limits,
    resolve_profile,
)


def test_metric_keeps_status_and_source():
    metric = PerformanceMetric(
        name="output_voltage_mean_v",
        value=4.67,
        unit="V",
        status=MetricStatus.AVAILABLE,
        data_source=DataSource.SPICE_DERIVED,
        method="time_weighted_integration",
    )
    assert metric.numeric() == pytest.approx(4.67)
    payload = metric.to_dict()
    assert payload["status"] == "AVAILABLE"
    assert payload["data_source"] == "spice_derived"
    text_metric = PerformanceMetric(
        name="note",
        value="ok",
        unit="1",
        status=MetricStatus.AVAILABLE,
        data_source=DataSource.PROJECT_ASSUMPTION,
        method="manual",
    )
    assert text_metric.numeric() is None


def test_metric_group_and_result_lookup():
    group = VoltageMetrics(
        {
            "output_voltage_mean_v": PerformanceMetric(
                "output_voltage_mean_v", 4.67, "V", MetricStatus.AVAILABLE,
                DataSource.SPICE_DERIVED, "integration",
            )
        }
    )
    assert group.value("output_voltage_mean_v") == pytest.approx(4.67)
    assert group.get("missing") is None
    assert group.to_dict()["label"] == "voltage"

    result = PerformanceResult(
        run_id="run",
        circuit_name="nonideal_buck",
        variant="E",
        data_source="spice_simulation",
        steady_state={"achieved": True},
        groups={"voltage": group},
        checks=(),
        quality={"passed": True},
        overall_status="PASS",
    )
    assert result.numeric("output_voltage_mean_v") == pytest.approx(4.67)
    assert result.numeric("missing") is None
    payload = result.to_dict()
    assert payload["variant"] == "E"
    assert "metrics" in payload


def test_load_analysis_config_reads_real_file():
    data = load_analysis_config()
    analysis = data["analysis"]
    assert analysis["steady_state"]["minimum_cycles"] > 0
    assert analysis["spectrum"]["window"] in ("hann", "hamming", "blackman", "boxcar")
    assert analysis["quality"]["maximum_power_residual_ratio"] > 0


def test_load_limits_and_profiles():
    limits = load_limits()
    baseline = resolve_profile(limits, "baseline_open_loop")
    assert "efficiency_system_percent" in baseline
    assert "output_voltage_ripple_vpp" in baseline
    with pytest.raises(ValueError):
        resolve_profile(limits, "does_not_exist")


def test_load_cases_ids_are_unique():
    cases = load_cases()
    assert len(cases) >= 6
    identifiers = [case["id"] for case in cases]
    assert len(set(identifiers)) == len(identifiers)
    assert all("variant" in case for case in cases)


def test_missing_configuration_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_analysis_config(tmp_path / "missing.yaml")


def test_invalid_configuration_raises(tmp_path: Path):
    path = tmp_path / "bad.yaml"
    path.write_text("analysis: {}\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_analysis_config(path)

    cases = tmp_path / "cases.yaml"
    cases.write_text("cases: []\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_cases(cases)

    duplicate = tmp_path / "duplicate.yaml"
    duplicate.write_text(
        "cases:\n  - id: A\n    variant: E\n  - id: A\n    variant: E\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_cases(duplicate)
