"""可靠性统计与实验判定单元测试（不依赖真实仪器）。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from engine.models import CleanupStatus, TestStatus
from reliability.fault_logger import EventType, new_event
from reliability.reliability_analyzer import (
    ExperimentExpectation,
    ReliabilityAnalyzer,
    evaluate_suite_experiment,
    load_experiments,
    validate_experiment_coverage,
)

ROOT = Path(__file__).resolve().parents[1]


def _result(**overrides):
    data = {
        "status": TestStatus.PASS,
        "case_id": "CASE",
        "retry_count": 0,
        "recovered": False,
        "retry_exhausted": False,
        "cleanup_status": CleanupStatus.VERIFIED_OFF.value,
        "fault_injected": True,
        "cleanup_failed": False,
        "fault_events": [],
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_missing_experiment_rejected():
    experiments = load_experiments(ROOT / "configs" / "reliability_experiments.yaml")
    with pytest.raises(ValueError):
        validate_experiment_coverage(["NONE", "F001", "F999"], experiments)


def test_duplicate_experiment_rejected(tmp_path):
    path = tmp_path / "experiments.yaml"
    payload = {
        "version": "1.0",
        "simulation_only": True,
        "experiments": [
            {
                "scenario_id": "F001",
                "name": "a",
                "expected_status": "PASS",
            },
            {
                "scenario_id": "F001",
                "name": "b",
                "expected_status": "PASS",
            },
        ],
    }
    path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError):
        load_experiments(path)


def test_invalid_expected_status_rejected():
    with pytest.raises(ValueError):
        ExperimentExpectation(
            scenario_id="F001", name="x", expected_status="OK"
        )


def test_summary_counts_injections_retries_and_recovery_rate():
    events = [
        new_event(
            EventType.FAULT_INJECTED,
            scenario_id="F001",
            fault_type="TIMEOUT",
            operation_id="op-1",
        ),
        new_event(
            EventType.ATTEMPT_FAILED,
            scenario_id="F001",
            operation_id="op-1",
            error_category="TRANSIENT_COMMUNICATION",
            details={"retry_safe": True},
        ),
        new_event(
            EventType.RETRY_SCHEDULED,
            scenario_id="F001",
            operation_id="op-1",
            details={"delay_seconds": 0.1},
        ),
        new_event(
            EventType.RECOVERED,
            scenario_id="F001",
            operation_id="op-1",
        ),
        new_event(
            EventType.ATTEMPT_FAILED,
            scenario_id="F002",
            operation_id="op-2",
            error_category="TRANSIENT_COMMUNICATION",
            details={"retry_safe": True},
        ),
        new_event(
            EventType.RETRY_SCHEDULED,
            scenario_id="F002",
            operation_id="op-2",
            details={"delay_seconds": 0.2},
        ),
        new_event(
            EventType.RETRY_EXHAUSTED,
            scenario_id="F002",
            operation_id="op-2",
            error_category="TRANSIENT_COMMUNICATION",
        ),
        new_event(
            EventType.CLEANUP_FAILED,
            scenario_id="F009",
            cleanup_status="NOT_VERIFIED",
        ),
    ]
    results = [
        {
            "scenario_id": "F001",
            "status": "PASS",
            "experiment_passed": True,
            "cleanup_status": "VERIFIED_OFF",
        },
        {
            "scenario_id": "F002",
            "status": "ERROR",
            "experiment_passed": True,
            "cleanup_status": "VERIFIED_OFF",
        },
        {
            "scenario_id": "F009",
            "status": "ERROR",
            "experiment_passed": True,
            "cleanup_status": "NOT_VERIFIED",
            "forced_stop": True,
        },
        {"scenario_id": "F009", "status": "SKIP"},
    ]
    summary = ReliabilityAnalyzer().summarize(
        events, results, expected_fault_types=["TIMEOUT", "DISCONNECT"]
    )
    assert summary["total_fault_injections"] == 1
    assert summary["retry_count"] == 2
    assert summary["retry_eligible_operations"] == 2
    assert summary["recovered_operations"] == 1
    assert summary["recovery_rate"] == pytest.approx(50.0)
    assert summary["retry_exhausted_count"] == 1
    assert summary["cleanup_failure_count"] == 1
    assert summary["forced_stop_count"] == 1
    assert summary["experiment_pass_count"] == 3
    assert summary["retry_overhead_ms"] == pytest.approx(300.0)
    coverage = {item["fault_type"]: item for item in summary["fault_detection_coverage"]}
    assert coverage["TIMEOUT"]["covered"] is True
    assert coverage["DISCONNECT"]["covered"] is False


def test_summary_deduplicates_event_ids():
    event = new_event(EventType.FAULT_INJECTED, scenario_id="F001", fault_type="TIMEOUT")
    summary = ReliabilityAnalyzer().summarize([event, dict(event)], [])
    assert summary["total_fault_injections"] == 1


def test_evaluate_suite_experiment_business_error_can_pass():
    expectation = ExperimentExpectation(
        scenario_id="F002",
        name="持续超时",
        expected_status="ERROR",
        expected_retry_count=2,
        expected_retry_exhausted=True,
        expected_cleanup_status="VERIFIED_OFF",
        expect_fault_injected=True,
    )
    result = _result(
        status=TestStatus.ERROR,
        retry_count=2,
        retry_exhausted=True,
        fault_events=[new_event(EventType.RETRY_EXHAUSTED)],
    )
    passed, reasons, actual = evaluate_suite_experiment([result], expectation)
    assert passed is True
    assert reasons == []
    assert actual["status"] == "ERROR"


def test_evaluate_suite_experiment_detects_mismatch():
    expectation = ExperimentExpectation(
        scenario_id="F001", name="单次超时", expected_status="PASS", expected_retry_count=1
    )
    result = _result(status=TestStatus.ERROR, retry_count=0)
    passed, reasons, _ = evaluate_suite_experiment([result], expectation)
    assert passed is False
    assert any("业务状态" in reason for reason in reasons)
    assert any("重试次数" in reason for reason in reasons)


def test_evaluate_forced_stop_requires_skipped_tail():
    expectation = ExperimentExpectation(
        scenario_id="F009",
        name="关闭失败",
        expected_status="ERROR",
        expected_cleanup_status="NOT_VERIFIED",
        expect_fault_injected=True,
        expect_forced_stop=True,
    )
    first = _result(
        status=TestStatus.ERROR,
        cleanup_status="NOT_VERIFIED",
        cleanup_failed=True,
    )
    skipped = _result(status=TestStatus.SKIP, fault_injected=False)
    passed, reasons, actual = evaluate_suite_experiment(
        [first, skipped], expectation, stopped_early=True
    )
    assert passed is True
    assert actual["forced_stop"] is True

    passed_fail, reasons_fail, _ = evaluate_suite_experiment(
        [first, _result(status=TestStatus.PASS)], expectation, stopped_early=False
    )
    assert passed_fail is False
    assert any("强制停止" in reason for reason in reasons_fail)


def test_evaluate_requires_executed_result():
    expectation = ExperimentExpectation(
        scenario_id="NONE", name="基线", expected_status="PASS"
    )
    passed, reasons, actual = evaluate_suite_experiment(
        [_result(status=TestStatus.SKIP)], expectation
    )
    assert passed is False
    assert actual == {}
    assert "没有" in reasons[0]
