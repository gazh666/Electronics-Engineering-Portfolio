"""性能分析器测试：指标、限值、N/A、数据质量与配置校验。"""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest
import yaml

from analysis.performance_analyzer import (
    PerformanceAnalyzer,
    load_performance_limits,
)
from bench.virtual_test_bench import VirtualTestBench
from instruments import InstrumentManager
from models.virtual_dut import VirtualDUT

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "instruments.yaml"
DUT_CONFIG = ROOT / "configs" / "dut_config.yaml"
LIMITS_CONFIG = ROOT / "configs" / "performance_limits.yaml"


@pytest.fixture()
def analyzer():
    return PerformanceAnalyzer(LIMITS_CONFIG)


@pytest.fixture()
def bench():
    with InstrumentManager(CONFIG) as manager:
        yield VirtualTestBench(manager, VirtualDUT.from_yaml(DUT_CONFIG))


def _setup(bench):
    bench.psu.set_output(False)
    bench.load.set_input(False)
    bench.psu.set_voltage(12.0)
    bench.psu.set_current(2.0)
    bench.load.set_mode("CC")
    bench.load.set_current(1.0)
    bench.psu.set_output(True)
    bench.load.set_input(True)


def _valid_mapping(**overrides):
    result = VirtualDUT().calculate(12.0, 2.0, 1.0)
    mapping = asdict(result)
    mapping["state"] = result.state.value
    mapping.update(overrides)
    return mapping


def test_nominal_record_metrics(analyzer):
    row = analyzer.analyze(VirtualDUT().calculate(12.0, 2.0, 1.0))

    assert row["data_quality_status"] == "VALID"
    assert row["metric_status"] == "AVAILABLE"
    assert row["metrics"]["output_power_w"] == pytest.approx(4.98)
    assert row["metrics"]["efficiency_percent"] == pytest.approx(90.0)
    assert row["metrics"]["voltage_error_percent"] == pytest.approx(-0.4)
    assert row["metrics"]["absolute_voltage_error_percent"] == pytest.approx(0.4)


def test_all_normal_checks_pass(analyzer):
    row = analyzer.analyze(VirtualDUT().calculate(12.0, 2.0, 1.0))
    statuses = {check["metric"]: check["status"] for check in row["checks"]}

    assert statuses["output_voltage"] == "PASS"
    assert statuses["voltage_error"] == "PASS"
    assert statuses["efficiency"] == "PASS"
    assert statuses["load_regulation"] == "N/A"
    assert statuses["line_regulation"] == "N/A"


def test_protection_state_is_not_applicable(analyzer):
    row = analyzer.analyze(VirtualDUT().calculate(12.0, 2.0, 2.5))

    assert row["state"] == "OVERCURRENT"
    assert row["metric_status"] == "NOT_APPLICABLE"
    assert row["metrics"] is None
    assert all(check["status"] == "N/A" for check in row["checks"])
    assert not any(check["status"] == "FAIL" for check in row["checks"])


def test_no_load_efficiency_is_na(analyzer):
    row = analyzer.analyze(VirtualDUT().calculate(12.0, 2.0, 0.0))
    efficiency = next(
        check for check in row["checks"] if check["metric"] == "efficiency"
    )
    assert row["metrics"]["efficiency_percent"] is None
    assert efficiency["status"] == "N/A"


def test_static_mock_source_is_invalid(analyzer):
    row = analyzer.analyze(_valid_mapping(source="static_mock"))
    assert row["data_quality_status"] == "ERROR"
    assert row["metric_status"] == "INVALID_DATA"
    assert row["metrics"] is None
    assert any(
        issue["code"] == "SOURCE_MISMATCH" for issue in row["quality_issues"]
    )


def test_power_imbalance_marks_invalid(analyzer):
    row = analyzer.analyze(_valid_mapping(pout=6.0, power_loss=-0.4666))
    assert row["data_quality_status"] == "ERROR"
    assert row["metric_status"] == "INVALID_DATA"


def test_non_finite_value_marks_invalid(analyzer):
    row = analyzer.analyze(_valid_mapping(iin=float("nan")))
    assert row["data_quality_status"] == "ERROR"
    assert row["metric_status"] == "INVALID_DATA"


def test_efficiency_above_100_marks_invalid(analyzer):
    row = analyzer.analyze(_valid_mapping(efficiency=1.2))
    assert row["data_quality_status"] == "ERROR"
    assert any(
        issue["code"] == "EFFICIENCY_ABOVE_100"
        for issue in row["quality_issues"]
    )


def test_limit_threshold_change_causes_failure(analyzer):
    strict = PerformanceAnalyzer(
        replace(
            analyzer.limits,
            max_absolute_voltage_error_percent=0.2,
        )
    )
    row = strict.analyze(VirtualDUT().calculate(12.0, 2.0, 1.0))
    statuses = {check["metric"]: check["status"] for check in row["checks"]}

    assert statuses["output_voltage"] == "PASS"
    assert statuses["voltage_error"] == "FAIL"


def test_analysis_record_is_json_serializable(analyzer):
    row = analyzer.analyze(VirtualDUT().calculate(12.0, 2.0, 1.0))
    payload = json.dumps(row, ensure_ascii=False)
    assert "behavioral_model" in payload


def test_load_limits_missing_file():
    with pytest.raises(FileNotFoundError):
        load_performance_limits("missing_limits.yaml")


def test_invalid_limits_config_rejected(tmp_path):
    data = yaml.safe_load(LIMITS_CONFIG.read_text(encoding="utf-8"))
    data["profile"]["output_voltage"]["min_v"] = 5.2
    data["profile"]["output_voltage"]["max_v"] = 5.1
    path = tmp_path / "limits.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")

    with pytest.raises(ValueError):
        load_performance_limits(path)


def test_efficiency_limit_above_100_rejected(tmp_path):
    data = yaml.safe_load(LIMITS_CONFIG.read_text(encoding="utf-8"))
    data["profile"]["efficiency"]["max_percent"] = 110.0
    path = tmp_path / "limits.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")

    with pytest.raises(ValueError):
        load_performance_limits(path)


def test_analyze_real_bench_result(bench, analyzer):
    _setup(bench)
    row = analyzer.analyze(bench.read_state())

    assert row["source"] == "behavioral_model"
    assert row["data_quality_status"] == "VALID"
    assert row["state"] == "NORMAL"
    assert row["metrics"]["input_power_w"] == pytest.approx(5.533333, rel=1e-5)
    assert row["metrics"]["output_power_w"] == pytest.approx(4.98)


def test_analyze_many_preserves_order(analyzer):
    results = [
        VirtualDUT().calculate(12.0, 2.0, 0.0),
        VirtualDUT().calculate(12.0, 2.0, 1.0),
        VirtualDUT().calculate(12.0, 2.0, 2.5),
    ]
    rows = analyzer.analyze_many(results)
    assert [row["state"] for row in rows] == ["NORMAL", "NORMAL", "OVERCURRENT"]
    assert [row["iout"] for row in rows] == [0.0, 1.0, 0.0]


def test_resources_released_after_analysis_exception():
    manager = InstrumentManager(CONFIG)
    with pytest.raises(RuntimeError):
        with manager:
            bench = VirtualTestBench(manager, VirtualDUT.from_yaml(DUT_CONFIG))
            _setup(bench)
            raise RuntimeError("模拟分析中断")
    assert manager.opened_devices == {}
    assert manager.available == ()
