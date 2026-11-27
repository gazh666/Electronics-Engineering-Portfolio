"""ResultStore 测试：运行目录、JSONL/CSV、汇总与日志。"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import pytest

from engine.models import CheckResult, TestResult, TestStatus
from storage.result_store import ResultStore


def _result(run_id="run1", index=0, status=TestStatus.PASS, vout=4.98):
    return TestResult(
        run_id=run_id,
        case_id=f"TC{index:03d}",
        case_name="测试用例",
        started_at="2026-01-01T00:00:00+00:00",
        finished_at="2026-01-01T00:00:01+00:00",
        duration_ms=12.5,
        status=status,
        expected_state="NORMAL",
        actual_state="NORMAL",
        raw_data={
            "vin": 12.0,
            "iin": 0.4611,
            "vout": vout,
            "iout": 1.0,
            "pin": 5.5333,
            "pout": 4.98,
            "vin_setpoint": 12.0,
            "input_current_limit": 3.0,
            "load_current_setpoint": 1.0,
        },
        metrics={"efficiency_percent": 90.0, "voltage_error_percent": -0.4},
        checks=[CheckResult("vout", vout, {"min": 4.9, "max": 5.1}, TestStatus.PASS)],
        data_source="behavioral_model",
        execution_index=index,
    )


def _store(tmp_path: Path, **kwargs) -> ResultStore:
    return ResultStore(tmp_path / "automation", **kwargs)


def _start(store: ResultStore, run_id="run1", planned=1):
    from engine.models import TestCase

    case = TestCase(
        case_id="TC000",
        name="测试用例",
        category="normal",
        vin=12.0,
        input_current_limit=3.0,
        load_current=1.0,
        expected_state="NORMAL",
    )
    return store.start_run(
        run_id=run_id,
        suite_id="S1",
        suite_name="临时方案",
        planned_count=planned,
        cases=[case],
    )


def test_start_run_creates_directory_and_files(tmp_path):
    snapshot = tmp_path / "cases.yaml"
    snapshot.write_text("version: '1.0'\n", encoding="utf-8")

    store = _store(tmp_path, snapshot_files={"cases_snapshot.yaml": snapshot})
    directory = _start(store)

    assert directory.is_dir()
    for name in (
        "metadata.json",
        "results.jsonl",
        "results.csv",
        "execution.log",
        "cases_snapshot.yaml",
    ):
        assert (directory / name).exists()

    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["run_id"] == "run1"
    assert metadata["planned_count"] == 1
    assert metadata["data_mode"] == "SIMULATION"
    assert metadata["snapshots"]["cases_snapshot.yaml"] == str(snapshot)


def test_duplicate_run_id_rejected(tmp_path):
    store = _store(tmp_path)
    _start(store)
    with pytest.raises(ValueError, match="run_id 重复"):
        _start(store)


def test_missing_snapshot_source_raises(tmp_path):
    store = _store(tmp_path, snapshot_files={"missing.yaml": tmp_path / "nope.yaml"})
    with pytest.raises(FileNotFoundError):
        _start(store)


def test_save_result_appends_jsonl_and_csv(tmp_path):
    store = _store(tmp_path)
    directory = _start(store, planned=2)

    store.save_result(_result(index=0))
    store.save_result(_result(index=1, status=TestStatus.FAIL))

    lines = (directory / "results.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["status"] == "PASS"
    assert first["raw_data"]["vout"] == pytest.approx(4.98)

    with (directory / "results.csv").open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == 2
    assert rows[0]["case_id"] == "TC000"
    assert rows[0]["efficiency_percent"] == "90.0"
    assert rows[1]["status"] == "FAIL"
    assert store.result_count("run1") == 2


def test_non_finite_values_written_as_explicit_strings(tmp_path):
    store = _store(tmp_path)
    directory = _start(store)

    result = _result()
    result.raw_data["vout"] = math.nan
    result.raw_data["iin"] = math.inf
    store.save_result(result)

    payload = json.loads(
        (directory / "results.jsonl").read_text(encoding="utf-8").splitlines()[0]
    )
    assert payload["raw_data"]["vout"] == "NaN"
    assert payload["raw_data"]["iin"] == "Infinity"


def test_finish_run_writes_summary(tmp_path):
    store = _store(tmp_path)
    directory = _start(store)
    store.save_result(_result())
    store.finish_run("run1", TestStatus.PASS, {"total_cases": 1, "pass_count": 1})

    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "PASS"
    assert summary["summary"]["pass_count"] == 1
    assert summary["finished_at"]
    assert store.get_summary("run1")["run_id"] == "run1"


def test_execution_log_records_actions(tmp_path):
    store = _store(tmp_path)
    directory = _start(store)
    store.save_result(_result())
    store.log("自定义日志", run_id="run1")

    log_text = (directory / "execution.log").read_text(encoding="utf-8")
    assert "运行开始" in log_text
    assert "[PASS] TC000" in log_text
    assert "自定义日志" in log_text


def test_list_run_directories_returns_existing_runs(tmp_path):
    store = _store(tmp_path)
    _start(store, run_id="run1")
    _start(store, run_id="run2")
    directories = store.list_run_directories()
    assert {path.name for path in directories} == {"run_run1", "run_run2"}


def test_save_before_start_raises(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(KeyError):
        store.save_result(_result())
