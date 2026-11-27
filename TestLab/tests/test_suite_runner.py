"""SuiteRunner 单元测试：使用桩执行器与内存存储，不接触仪器。"""

from __future__ import annotations

import pytest

from engine.models import (
    SuiteRunStatus,
    TestCase,
    TestResult,
    TestStatus,
    TestSuite,
    summarize_results,
)
from engine.suite_runner import SuiteRunner, exit_code_for_results


def _case(case_id: str) -> TestCase:
    return TestCase(
        case_id=case_id,
        name=f"用例 {case_id}",
        category="normal",
        vin=12.0,
        input_current_limit=3.0,
        load_current=1.0,
        expected_state="NORMAL",
    )


class StubRunner:
    def __init__(self, statuses, cleanup_ids=(), interrupt_ids=(), error_ids=()):
        self.statuses = statuses
        self.cleanup_ids = set(cleanup_ids)
        self.interrupt_ids = set(interrupt_ids)
        self.error_ids = set(error_ids)
        self.calls: list[str] = []

    def run_case(self, case, run_id, execution_index=0):
        self.calls.append(case.case_id)
        if case.case_id in self.interrupt_ids:
            raise KeyboardInterrupt
        if case.case_id in self.error_ids:
            raise RuntimeError("执行器异常")

        status = self.statuses[case.case_id]
        return TestResult(
            run_id=run_id,
            case_id=case.case_id,
            case_name=case.name,
            started_at="t0",
            finished_at="t1",
            duration_ms=1.0,
            status=status,
            expected_state=case.expected_state,
            execution_index=execution_index,
            error_message=None if status is TestStatus.PASS else f"{status} 原因",
            cleanup_failed=case.case_id in self.cleanup_ids,
        )


class MemoryStore:
    def __init__(self, fail=False):
        self.fail = fail
        self.started = None
        self.results: list[TestResult] = []
        self.logs: list[str] = []
        self.finished = None

    def start_run(self, **kwargs):
        self.started = kwargs

    def save_result(self, result):
        if self.fail:
            raise OSError("磁盘已满")
        self.results.append(result)

    def finish_run(self, run_id, status, summary):
        self.finished = (run_id, status, summary)

    def log(self, message):
        self.logs.append(message)


def _suite(*case_ids, **overrides) -> TestSuite:
    data = dict(
        suite_id="S1",
        name="临时方案",
        case_ids=tuple(case_ids),
        stop_on_fail=False,
        stop_on_error=True,
    )
    data.update(overrides)
    return TestSuite(**data)


def test_cases_execute_in_suite_order():
    cases = [_case("A"), _case("B"), _case("C")]
    runner = StubRunner({"A": TestStatus.PASS, "B": TestStatus.PASS, "C": TestStatus.PASS})
    run = SuiteRunner(runner).run_suite(_suite("C", "A", "B"), cases)
    assert runner.calls == ["C", "A", "B"]
    assert [result.case_id for result in run.results] == ["C", "A", "B"]
    assert run.status is SuiteRunStatus.COMPLETED


def test_stop_on_fail_adds_skip_records_with_reason():
    cases = [_case("A"), _case("B"), _case("C")]
    runner = StubRunner({"A": TestStatus.PASS, "B": TestStatus.FAIL, "C": TestStatus.PASS})
    store = MemoryStore()
    run = SuiteRunner(runner, store).run_suite(_suite("A", "B", "C", stop_on_fail=True), cases)

    assert runner.calls == ["A", "B"]  # C 未执行
    assert [result.status for result in run.results] == [
        TestStatus.PASS,
        TestStatus.FAIL,
        TestStatus.SKIP,
    ]
    assert "未执行" in run.results[-1].error_message
    assert len(store.results) == 3  # SKIP 也被持久化


def test_stop_on_error_can_be_disabled():
    cases = [_case("A"), _case("B")]
    runner = StubRunner({"A": TestStatus.ERROR, "B": TestStatus.PASS})
    run = SuiteRunner(runner).run_suite(
        _suite("A", "B", stop_on_error=False), cases
    )
    assert runner.calls == ["A", "B"]
    assert run.summary["error_count"] == 1
    assert run.summary["pass_count"] == 1


def test_stop_on_error_default_stops():
    cases = [_case("A"), _case("B")]
    runner = StubRunner({"A": TestStatus.ERROR, "B": TestStatus.PASS})
    run = SuiteRunner(runner).run_suite(_suite("A", "B"), cases)
    assert runner.calls == ["A"]
    assert run.results[-1].status is TestStatus.SKIP


def test_cleanup_failure_forces_stop_even_without_stop_on_fail():
    cases = [_case("A"), _case("B")]
    runner = StubRunner(
        {"A": TestStatus.PASS, "B": TestStatus.PASS}, cleanup_ids={"A"}
    )
    run = SuiteRunner(runner).run_suite(
        _suite("A", "B", stop_on_fail=False, stop_on_error=False), cases
    )
    assert runner.calls == ["A"]
    assert run.results[0].status is TestStatus.ERROR
    assert run.status is SuiteRunStatus.ERROR
    assert "清理失败" in run.stop_reason


def test_keyboard_interrupt_marks_aborted_and_keeps_skips():
    cases = [_case("A"), _case("B")]
    runner = StubRunner({"A": TestStatus.PASS, "B": TestStatus.PASS}, interrupt_ids={"A"})
    run = SuiteRunner(runner).run_suite(_suite("A", "B"), cases)
    assert run.status is SuiteRunStatus.ABORTED
    assert run.results[0].status is TestStatus.SKIP
    assert "用户中断" in run.results[0].error_message


def test_executor_exception_becomes_error_record():
    cases = [_case("A"), _case("B")]
    runner = StubRunner(
        {"A": TestStatus.PASS, "B": TestStatus.PASS}, error_ids={"A", "B"}
    )
    run = SuiteRunner(runner).run_suite(
        _suite("A", "B", stop_on_error=False), cases
    )
    assert all(result.status is TestStatus.ERROR for result in run.results)
    assert "执行器异常" in run.results[0].error_message


def test_progress_callback_exception_does_not_break_execution():
    cases = [_case("A"), _case("B")]
    runner = StubRunner({"A": TestStatus.PASS, "B": TestStatus.PASS})
    suite_runner = SuiteRunner(runner)
    seen: list[str] = []

    def callback(current, total, result):
        seen.append(result.case_id)
        raise ValueError("回调坏了")

    run = suite_runner.run_suite(_suite("A", "B"), cases, progress_callback=callback)
    assert run.status is SuiteRunStatus.COMPLETED
    assert seen == ["A", "B"]
    assert len(suite_runner.callback_errors) == 2


def test_storage_failure_marks_suite_error_without_hiding_results():
    cases = [_case("A"), _case("B")]
    runner = StubRunner({"A": TestStatus.PASS, "B": TestStatus.PASS})
    suite_runner = SuiteRunner(runner, MemoryStore(fail=True))
    run = suite_runner.run_suite(_suite("A", "B"), cases)

    assert run.status is SuiteRunStatus.ERROR
    assert len(suite_runner.storage_errors) == 2
    assert len(run.results) == 2  # 内存结果仍在，未被静默丢弃
    assert run.summary["pass_count"] == 2


def test_summary_counts_total_and_rates():
    cases = [_case("A"), _case("B"), _case("C"), _case("D")]
    runner = StubRunner(
        {
            "A": TestStatus.PASS,
            "B": TestStatus.FAIL,
            "C": TestStatus.ERROR,
            "D": TestStatus.PASS,
        }
    )
    run = SuiteRunner(runner).run_suite(
        _suite("A", "B", "C", "D", stop_on_error=False), cases
    )
    summary = run.summary
    assert summary["total_cases"] == 4
    assert summary["executed_cases"] == 4
    assert summary["pass_count"] == 2
    assert summary["fail_count"] == 1
    assert summary["error_count"] == 1
    assert summary["pass_rate"] == pytest.approx(2 / 3 * 100)
    assert summary["completion_rate"] == pytest.approx(100.0)
    assert summary["planned_pass_rate"] == pytest.approx(50.0)


def test_missing_case_reference_raises_before_execution():
    runner = StubRunner({"A": TestStatus.PASS})
    with pytest.raises(ValueError, match="未加载"):
        SuiteRunner(runner).run_suite(_suite("A", "X"), [_case("A")])
    assert runner.calls == []


def test_exit_code_mapping():
    def result(status: TestStatus) -> TestResult:
        return TestResult(
            run_id="r",
            case_id="c",
            case_name="n",
            started_at="t",
            finished_at="t",
            duration_ms=0.0,
            status=status,
            expected_state="NORMAL",
        )

    assert exit_code_for_results([result(TestStatus.PASS)]) == 0
    assert exit_code_for_results([result(TestStatus.PASS), result(TestStatus.FAIL)]) == 1
    assert exit_code_for_results([result(TestStatus.FAIL), result(TestStatus.ERROR)]) == 2
    assert exit_code_for_results([result(TestStatus.SKIP)]) == 3
    assert exit_code_for_results([]) == 3


def test_summarize_empty_results():
    summary = summarize_results([], 0)
    assert summary["pass_rate"] is None
    assert summary["completion_rate"] is None
    assert summary["planned_pass_rate"] is None
