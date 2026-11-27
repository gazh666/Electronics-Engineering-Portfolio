"""SQLiteStore 测试：模式、事务回滚、幂等写入与查询接口。"""

from __future__ import annotations

import json
import math
import sqlite3

import pytest

from engine.models import CheckResult, TestResult, TestStatus
from storage.sqlite_store import SQLiteStore


def _result(index=0, status=TestStatus.PASS, checks=None, run_id="run1"):
    return TestResult(
        run_id=run_id,
        case_id=f"TC{index:03d}",
        case_name="测试用例",
        started_at="2026-01-01T00:00:00+00:00",
        finished_at="2026-01-01T00:00:01+00:00",
        duration_ms=8.0,
        status=status,
        expected_state="NORMAL",
        actual_state="NORMAL",
        raw_data={"vin": 12.0, "vout": 4.98, "iout": 1.0},
        metrics={"efficiency_percent": 90.0},
        checks=checks
        or [CheckResult("vout", 4.98, {"min": 4.9, "max": 5.1}, TestStatus.PASS)],
        data_source="behavioral_model",
        execution_index=index,
    )


@pytest.fixture()
def store(tmp_path):
    return SQLiteStore(tmp_path / "history.db")


def test_schema_created(store):
    with sqlite3.connect(store.db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert {"runs", "test_results", "check_results"} <= tables


def test_save_and_query_result(store):
    store.start_run("run1", "S1", "临时方案", planned_count=1)
    result_id = store.save_result(_result())

    rows = store.get_results_by_run("run1")
    assert len(rows) == 1
    assert rows[0]["case_id"] == "TC000"
    assert rows[0]["status"] == "PASS"
    assert json.loads(rows[0]["raw_data_json"])["vout"] == pytest.approx(4.98)

    checks = store.get_checks(result_id)
    assert len(checks) == 1
    assert checks[0]["check_name"] == "vout"
    assert checks[0]["status"] == "PASS"


def test_duplicate_write_is_idempotent(store):
    store.start_run("run1", "S1", "临时方案", planned_count=1)
    first = store.save_result(_result(index=0))
    second = store.save_result(_result(index=0))

    assert first == second
    assert store.count_results("run1") == 1
    assert len(store.get_checks(first)) == 1


def test_transaction_rolls_back_on_check_failure(store):
    store.start_run("run1", "S1", "临时方案", planned_count=1)
    broken = _result(checks=[CheckResult("bad", 1, 1, "BAD")])

    with pytest.raises(sqlite3.IntegrityError):
        store.save_result(broken)

    assert store.count_results("run1") == 0
    with sqlite3.connect(store.db_path) as connection:
        checks = connection.execute("SELECT COUNT(*) FROM check_results").fetchone()[0]
    assert checks == 0


def test_save_without_start_auto_creates_run(store):
    store.save_result(_result(run_id="auto"))
    assert store.get_run("auto") is not None
    assert store.count_results("auto") == 1


def test_finish_run_updates_status_and_summary(store):
    store.start_run("run1", "S1", "临时方案", planned_count=1)
    store.save_result(_result(status=TestStatus.FAIL))
    store.finish_run("run1", "COMPLETED", {"total_cases": 1, "fail_count": 1})

    run = store.get_run("run1")
    assert run["status"] == "COMPLETED"
    assert run["finished_at"]
    assert json.loads(run["summary_json"])["fail_count"] == 1


def test_failed_results_can_be_filtered(store):
    store.start_run("run1", "S1", "临时方案", planned_count=2)
    store.save_result(_result(index=0, status=TestStatus.PASS))
    store.save_result(_result(index=1, status=TestStatus.FAIL))

    failed = store.get_failed_results("run1")
    assert len(failed) == 1
    assert failed[0]["status"] == "FAIL"


def test_run_summary_counts_by_status(store):
    store.start_run("run1", "S1", "临时方案", planned_count=4)
    for index, status in enumerate(
        (TestStatus.PASS, TestStatus.FAIL, TestStatus.ERROR, TestStatus.SKIP)
    ):
        store.save_result(_result(index=index, status=status))

    summary = store.get_run_summary("run1")
    assert summary["total"] == 4
    assert summary["PASS"] == 1
    assert summary["FAIL"] == 1
    assert summary["ERROR"] == 1
    assert summary["SKIP"] == 1


def test_parameterized_sql_treats_names_as_data(store):
    store.start_run("run1", "S1", "临时方案", planned_count=1)
    result = _result()
    result.case_name = "'); DROP TABLE test_results; --"
    store.save_result(result)

    assert store.count_results("run1") == 1
    assert store.get_results_by_run("run1")[0]["case_name"].startswith("'); DROP")


def test_non_finite_values_serialized_as_strings(store):
    store.start_run("run1", "S1", "临时方案", planned_count=1)
    result = _result()
    result.raw_data["vout"] = math.nan
    store.save_result(result)

    row = store.get_results_by_run("run1")[0]
    assert json.loads(row["raw_data_json"])["vout"] == "NaN"


def test_duplicate_run_registration_preserves_history(store):
    store.start_run("run1", "S1", "方案一", planned_count=1)
    store.start_run("run1", "S2", "方案二", planned_count=2)
    run = store.get_run("run1")
    assert run["suite_id"] == "S1"
    assert run["planned_count"] == 1
