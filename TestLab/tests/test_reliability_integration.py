"""阶段八集成测试：真实 PyVISA-sim + 真实 VirtualDUT + 真实存储。

覆盖：
- 普通测试零回归与默认关闭；
- 单次超时恢复、持续超时耗尽、断开、非法数据；
- NaN/Infinity/一致偏移/不一致偏移；
- 清理失败强制停止、SKIP 记录、原始异常保留；
- JSONL / SQLite 故障事件关联；
- 用户取消（KeyboardInterrupt）仍释放资源。

不修改 PyVISA / PyVISA-sim 源码。
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import pytest

from analysis.performance_analyzer import PerformanceAnalyzer
from bench.virtual_test_bench import VirtualTestBench
from engine.case_loader import load_test_cases
from engine.models import CleanupStatus, SuiteRunStatus, TestStatus, TestSuite
from engine.suite_runner import SuiteRunner
from engine.test_runner import TestRunner
from instruments.exceptions import InstrumentNotConnectedError
from instruments.manager import InstrumentManager
from models.virtual_dut import VirtualDUT
from reliability.fault_injector import (
    FaultInjector as ScenarioFaultInjector,
    apply_measurement_faults,
)
from reliability.fault_logger import FaultLogger
from reliability.fault_models import load_fault_scenarios
from reliability.reliability_analyzer import (
    evaluate_suite_experiment,
    load_experiments,
)
from reliability.retry_policy import RetryPolicy
from storage.sqlite_store import SQLiteStore

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "instruments.yaml"
DUT_CONFIG = ROOT / "configs" / "dut_config.yaml"
LIMITS = ROOT / "configs" / "performance_limits.yaml"
CASE_CONFIG = ROOT / "configs" / "reliability_cases.yaml"
SCENARIO_CONFIG = ROOT / "configs" / "fault_scenarios.yaml"
EXPERIMENT_CONFIG = ROOT / "configs" / "reliability_experiments.yaml"

FAST_POLICY = RetryPolicy(
    max_attempts=3,
    initial_delay=0.0,
    multiplier=1.0,
    max_delay=0.0,
)
CASES = {case.case_id: case for case in load_test_cases(CASE_CONFIG)}
CASE_A = CASES["RC-RELIABILITY"]
CASE_B = CASES["RC-RELIABILITY-B"]
LIBRARY = load_fault_scenarios(SCENARIO_CONFIG)
EXPERIMENTS = load_experiments(EXPERIMENT_CONFIG)


@contextmanager
def _session(tmp_path, scenarios=(), *, configure=True, logger=None):
    manager = InstrumentManager(CONFIG)
    manager.open()
    log = logger if logger is not None else FaultLogger(tmp_path / "fault_events.jsonl")
    try:
        bench = VirtualTestBench(manager, VirtualDUT.from_yaml(DUT_CONFIG))
        runner = TestRunner(manager, bench, PerformanceAnalyzer(LIMITS))
        if configure:
            runner.configure_reliability(
                scenarios, retry_policy=FAST_POLICY, fault_logger=log
            )
        yield manager, runner, log
    finally:
        try:
            manager.close()
        except Exception:
            # 断开场景下会话已失效，关闭失败是预期且已记录
            pass


def _event_types(result):
    return [event.get("event_type") for event in result.fault_events]


def test_normal_test_has_no_fault_injection(tmp_path):
    with _session(tmp_path, []) as (manager, runner, logger):
        result = runner.run_case(CASE_A, "run-normal", 0)

        assert result.status is TestStatus.PASS
        assert result.fault_injected is False
        assert result.retry_count == 0
        assert result.recovered is False
        assert result.retry_exhausted is False
        assert result.cleanup_status == CleanupStatus.VERIFIED_OFF.value
        assert result.original_model_data["vout"] == pytest.approx(4.98)
        assert result.observed_data is None
        assert result.data_source == "behavioral_model"
        assert result.original_data_source == "behavioral_model"
        assert result.observed_data_source == "behavioral_model"
        assert manager.get_power_supply().get_output() is False
        assert logger.events  # 清理事件仍被记录
        assert "FAULT_INJECTED" not in _event_types(result)


def test_single_timeout_recovers_and_still_passes(tmp_path):
    with _session(tmp_path, LIBRARY.select_one("F001")) as (manager, runner, logger):
        result = runner.run_case(CASE_A, "run-f001", 0)

        assert result.status is TestStatus.PASS
        assert result.fault_injected is True
        assert result.fault_scenario_ids == ["F001"]
        assert result.retry_count == 1
        assert result.recovered is True
        assert result.retry_exhausted is False
        assert result.error_category is None
        assert result.cleanup_status == CleanupStatus.VERIFIED_OFF.value
        assert result.observed_data is None
        assert manager.get_power_supply().get_output() is False

        types = _event_types(result)
        assert "FAULT_INJECTED" in types
        assert "ATTEMPT_FAILED" in types
        assert "RETRY_SCHEDULED" in types
        assert "RECOVERED" in types
        assert "CLEANUP_COMPLETED" in types

        lines = (tmp_path / "fault_events.jsonl").read_text(encoding="utf-8").splitlines()
        assert lines
        assert all(json.loads(line)["event_type"] for line in lines)


def test_persistent_timeout_exhausts_and_errors(tmp_path):
    with _session(tmp_path, LIBRARY.select_one("F002")) as (manager, runner, _):
        result = runner.run_case(CASE_A, "run-f002", 0)

        assert result.status is TestStatus.ERROR
        assert result.fault_injected is True
        assert result.retry_count == 2
        assert result.recovered is False
        assert result.retry_exhausted is True
        assert result.error_category == "TRANSIENT_COMMUNICATION"
        assert "RetryExhaustedError" in result.error_message
        assert result.cleanup_status == CleanupStatus.VERIFIED_OFF.value
        assert manager.get_power_supply().get_output() is False
        assert "RETRY_EXHAUSTED" in _event_types(result)


def test_disconnect_invalidates_session_and_cleanup_not_verified(tmp_path):
    with _session(tmp_path, LIBRARY.select_one("F003")) as (manager, runner, _):
        result = runner.run_case(CASE_A, "run-f003", 0)
        psu = manager.get_power_supply()

        assert result.status is TestStatus.ERROR
        assert result.error_category == "DEVICE_DISCONNECTED"
        assert result.retry_count == 0
        assert result.recovered is False
        assert result.cleanup_status == CleanupStatus.NOT_VERIFIED.value
        assert result.cleanup_failed is True
        assert result.cleanup_errors
        assert "DeviceDisconnectedError" in result.error_message
        assert "清理失败" in result.error_message
        assert result.original_model_data is None
        assert psu.session_invalid is True
        with pytest.raises(InstrumentNotConnectedError):
            psu.get_voltage()


def test_invalid_response_is_error_without_retry(tmp_path):
    with _session(tmp_path, LIBRARY.select_one("F004")) as (manager, runner, _):
        result = runner.run_case(CASE_A, "run-f004", 0)

        assert result.status is TestStatus.ERROR
        assert result.error_category == "INVALID_DATA"
        assert result.retry_count == 0
        assert result.recovered is False
        assert result.retry_exhausted is False
        assert "InstrumentResponseError" in result.error_message
        assert result.cleanup_status == CleanupStatus.VERIFIED_OFF.value
        assert manager.get_power_supply().get_output() is False


def test_measurement_faults_f005_to_f008(tmp_path):
    with _session(tmp_path, []) as (manager, runner, _):
        # F005：vout = NaN，数据质量 ERROR，原始结果不被修改
        runner.configure_reliability(
            LIBRARY.select_one("F005"), retry_policy=FAST_POLICY
        )
        nan_result = runner.run_case(CASE_A, "run-f005", 0)
        assert nan_result.status is TestStatus.ERROR
        assert nan_result.error_category == "INVALID_DATA"
        assert nan_result.original_model_data["vout"] == pytest.approx(4.98)
        assert nan_result.raw_data["vout"] != nan_result.raw_data["vout"]  # NaN
        assert nan_result.observed_data["vout"] != nan_result.observed_data["vout"]
        assert nan_result.data_source == "fault_injected_model"
        assert nan_result.original_data_source == "behavioral_model"
        assert nan_result.quality_issues
        assert nan_result.cleanup_status == CleanupStatus.VERIFIED_OFF.value

        # F006：iin = Infinity
        runner.configure_reliability(
            LIBRARY.select_one("F006"), retry_policy=FAST_POLICY
        )
        inf_result = runner.run_case(CASE_A, "run-f006", 0)
        assert inf_result.status is TestStatus.ERROR
        assert inf_result.error_category == "INVALID_DATA"
        assert inf_result.original_model_data["iin"] == pytest.approx(
            inf_result.original_model_data["iin"]
        )
        assert inf_result.raw_data["iin"] == float("inf")
        assert inf_result.data_source == "fault_injected_model"

        # F007：vout -0.3，效率保持，限值判定 FAIL
        runner.configure_reliability(
            LIBRARY.select_one("F007"), retry_policy=FAST_POLICY
        )
        voltage_result = runner.run_case(CASE_A, "run-f007", 0)
        assert voltage_result.status is TestStatus.FAIL
        assert voltage_result.original_model_data["vout"] == pytest.approx(4.98)
        assert voltage_result.raw_data["vout"] == pytest.approx(4.68)
        assert voltage_result.data_source == "fault_injected_model"
        assert voltage_result.metrics is not None
        assert voltage_result.metrics["efficiency_percent"] == pytest.approx(90.0, abs=1e-6)
        assert voltage_result.raw_data["pout"] == pytest.approx(
            voltage_result.raw_data["vout"] * voltage_result.raw_data["iout"]
        )
        assert voltage_result.cleanup_status == CleanupStatus.VERIFIED_OFF.value

        # F008：iout +0.2，一致性重算后电流超出限值 -> FAIL
        runner.configure_reliability(
            LIBRARY.select_one("F008"), retry_policy=FAST_POLICY
        )
        current_result = runner.run_case(CASE_A, "run-f008", 0)
        assert current_result.status is TestStatus.FAIL
        assert current_result.original_model_data["iout"] == pytest.approx(1.0)
        assert current_result.raw_data["iout"] == pytest.approx(1.2)
        assert current_result.data_source == "fault_injected_model"
        assert current_result.metrics["efficiency_percent"] == pytest.approx(90.0, abs=1e-6)
        assert manager.get_power_supply().get_output() is False


def test_inconsistent_measurement_view_fails_data_quality():
    dut_result = VirtualDUT().calculate(12.0, 1.0)
    injector = ScenarioFaultInjector(
        LIBRARY.select_one("F007"), enabled=True, run_id="unit", case_id="CASE"
    )
    view = apply_measurement_faults(dut_result, injector, consistent=False)
    assert view is not dut_result
    assert view.vout == pytest.approx(4.68)
    assert view.pout == pytest.approx(dut_result.pout)
    assert dut_result.vout == pytest.approx(4.98)

    analysis = PerformanceAnalyzer(LIMITS).analyze(
        view, expected_source=view.source
    )
    assert analysis["quality_status"] == "ERROR"
    assert analysis["quality_issues"]


def test_retry_recovery_does_not_bypass_limits(tmp_path):
    strict_case = replace(
        CASE_A, limits={"vout": {"min": 5.5, "max": 6.0}}
    )
    with _session(tmp_path, LIBRARY.select_one("F001")) as (_, runner, _):
        result = runner.run_case(strict_case, "run-strict", 0)

        assert result.retry_count == 1
        assert result.recovered is True
        assert result.status is TestStatus.FAIL
        assert any(
            check.name == "vout" and check.status is TestStatus.FAIL
            for check in result.checks
        )


def test_case_id_filter_prevents_injection(tmp_path):
    other = replace(LIBRARY.get("F001"), case_id="OTHER-CASE")
    with _session(tmp_path, [other]) as (manager, runner, _):
        result = runner.run_case(CASE_A, "run-filter", 0)
        assert result.status is TestStatus.PASS
        assert result.retry_count == 0
        assert result.fault_injected is False
        assert "FAULT_INJECTED" not in _event_types(result)
        assert manager.get_power_supply().get_output() is False


def test_cleanup_failure_forces_stop_and_records_skip(tmp_path):
    with _session(tmp_path, [], configure=False) as (manager, runner, logger):
        suite = TestSuite(
            suite_id="REL-F009",
            name="清理失败强制停止",
            case_ids=(CASE_A.case_id, CASE_B.case_id),
            stop_on_fail=False,
            stop_on_error=False,
        )
        suite_runner = SuiteRunner(runner)
        run = suite_runner.run_suite(
            suite,
            [CASE_A, CASE_B],
            run_id="run-f009-suite",
            fault_scenarios=LIBRARY.select_one("F009"),
            retry_policy=FAST_POLICY,
            fault_logger=logger,
        )

        assert run.status is SuiteRunStatus.ERROR
        assert [result.status for result in run.results] == [
            TestStatus.ERROR,
            TestStatus.SKIP,
        ]
        first, second = run.results
        assert first.cleanup_failed is True
        assert first.cleanup_status == CleanupStatus.NOT_VERIFIED.value
        assert first.actual_state == "NORMAL"
        assert first.error_category == "SHUTDOWN_ERROR"
        assert "UnsafeShutdownError" in first.error_message
        assert second.actual_state is None
        assert "强制停止" in second.error_message
        # 模拟状态下输出确实未在这次清理中关闭；系统只记录 NOT_VERIFIED
        assert manager.get_power_supply().get_output() is True
        assert "TEST_ABORTED" in [event.get("event_type") for event in logger.events]

        passed, reasons, actual = evaluate_suite_experiment(
            run.results,
            EXPERIMENTS["F009"],
            stopped_early=True,
        )
        assert passed is True
        assert actual["forced_stop"] is True
        assert reasons == []


def test_no_state_pollution_between_runs(tmp_path):
    with _session(tmp_path, LIBRARY.select_one("F001")) as (manager, runner, _):
        first = runner.run_case(CASE_A, "run-pollution-1", 0)
        assert first.status is TestStatus.PASS
        assert first.retry_count == 1
        assert manager.get_power_supply().fault_injector is None

        runner.configure_reliability([], retry_policy=FAST_POLICY)
        second = runner.run_case(CASE_B, "run-pollution-2", 0)
        assert second.status is TestStatus.PASS
        assert second.retry_count == 0
        assert second.fault_injected is False
        assert second.fault_scenario_ids == []
        assert "FAULT_INJECTED" not in _event_types(second)
        assert manager.get_power_supply().fault_injector is None


def test_broken_event_logger_does_not_block_cleanup(tmp_path):
    class BrokenLogger:
        def emit(self, event):
            raise RuntimeError("disk full")

    with _session(
        tmp_path, LIBRARY.select_one("F001"), logger=BrokenLogger()
    ) as (manager, runner, _):
        result = runner.run_case(CASE_A, "run-broken-log", 0)
        assert result.status is TestStatus.PASS
        assert result.cleanup_status == CleanupStatus.VERIFIED_OFF.value
        assert manager.get_power_supply().get_output() is False
        assert runner.logger_errors
        assert "disk full" in runner.logger_errors[0]


def test_keyboard_interrupt_releases_resources(tmp_path):
    class InterruptingBench:
        def read_state(self):
            raise KeyboardInterrupt

    manager = InstrumentManager(CONFIG)
    manager.open()
    try:
        runner = TestRunner(manager, InterruptingBench(), PerformanceAnalyzer(LIMITS))
        with pytest.raises(KeyboardInterrupt):
            runner.run_case(CASE_A, "run-cancel", 0)
        assert manager.get_power_supply().get_output() is False
        assert manager.get_electronic_load().get_input() is False
    finally:
        manager.close()


def test_fault_events_saved_to_jsonl_and_sqlite(tmp_path):
    sqlite = SQLiteStore(tmp_path / "history.db")
    with _session(tmp_path, LIBRARY.select_one("F001")) as (_, runner, logger):
        result = runner.run_case(CASE_A, "run-storage", 0)
        assert result.status is TestStatus.PASS

        sqlite.start_run(
            result.run_id,
            suite_id="REL",
            suite_name="可靠性",
            planned_count=1,
            started_at=result.started_at,
        )
        sqlite.save_result(result)
        sqlite.save_fault_events(result.fault_events)
        sqlite.finish_run(
            result.run_id,
            SuiteRunStatus.COMPLETED.value,
            {"experiment_passed": True},
        )

        jsonl_events = [
            json.loads(line)
            for line in (tmp_path / "fault_events.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
        assert len(jsonl_events) == len(result.fault_events)
        assert {event["event_id"] for event in jsonl_events} == {
            event["event_id"] for event in result.fault_events
        }

        by_run = sqlite.get_fault_events_by_run(result.run_id)
        assert len(by_run) == len(result.fault_events)
        assert sqlite.get_retry_exhausted_events(result.run_id) == []
        assert len(sqlite.get_recovered_events(result.run_id)) == 1
        assert sqlite.get_fault_events_by_type("TIMEOUT")
        assert sqlite.count_results(result.run_id) == 1

    # 迁移可重复执行
    SQLiteStore(tmp_path / "history.db")
    with sqlite.connect() as connection:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(fault_events)")
        }
    assert {"event_id", "run_id", "fault_type", "cleanup_status"} <= columns


def test_experiment_can_pass_while_business_result_is_error(tmp_path):
    with _session(tmp_path, LIBRARY.select_one("F002")) as (_, runner, _):
        result = runner.run_case(CASE_A, "run-experiment", 0)

    passed, reasons, actual = evaluate_suite_experiment(
        [result], EXPERIMENTS["F002"]
    )
    assert result.status is TestStatus.ERROR
    assert passed is True
    assert reasons == []
    assert actual["status"] == "ERROR"
