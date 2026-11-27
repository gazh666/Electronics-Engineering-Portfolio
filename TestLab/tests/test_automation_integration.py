"""自动化引擎集成测试：真实 PyVISA-sim 仪器 + 真实 VirtualDUT + 真实存储。

不修改 PyVISA/PyVISA-sim 源码，全部通过业务层驱动。
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from analysis.performance_analyzer import PerformanceAnalyzer
from bench.virtual_test_bench import VirtualTestBench
from engine.case_loader import load_test_cases, load_test_suites
from engine.models import SuiteRunStatus, TestStatus, TestSuite
from engine.suite_runner import SuiteRunner
from engine.test_runner import TestRunner
from instruments.manager import InstrumentManager
from models.virtual_dut import VirtualDUT
from storage.result_store import ResultStore
from storage.sqlite_store import SQLiteStore

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "instruments.yaml"
CASES = ROOT / "configs" / "test_cases.yaml"
SUITES = ROOT / "configs" / "test_suites.yaml"
EV_CASES = ROOT / "configs" / "engine_validation_cases.yaml"
EV_SUITES = ROOT / "configs" / "engine_validation_suites.yaml"
LIMITS = ROOT / "configs" / "performance_limits.yaml"


def _stores(tmp_path):
    store = ResultStore(
        tmp_path / "automation",
        snapshot_files={
            "test_cases_snapshot.yaml": CASES,
            "limits_snapshot.yaml": LIMITS,
        },
    )
    return store, SQLiteStore(tmp_path / "history.db")


def _suite_runner(manager, tmp_path, dut=None):
    bench = VirtualTestBench(manager, dut or VirtualDUT())
    runner = TestRunner(manager, bench, PerformanceAnalyzer(LIMITS))
    store, sqlite_store = _stores(tmp_path)
    return SuiteRunner(runner, store, sqlite_store), store, sqlite_store, bench


def test_smoke_suite_passes_and_persists_everywhere(tmp_path):
    cases = load_test_cases(CASES)
    suites = load_test_suites(SUITES, [case.case_id for case in cases])
    smoke = next(suite for suite in suites if suite.suite_id == "SUITE-SMOKE")

    with InstrumentManager(CONFIG) as manager:
        suite_runner, store, sqlite_store, _ = _suite_runner(manager, tmp_path)
        run = suite_runner.run_suite(smoke, cases)

        assert run.status is SuiteRunStatus.COMPLETED
        assert [result.status for result in run.results] == [
            TestStatus.PASS,
            TestStatus.PASS,
        ]
        assert manager.get_electronic_load().get_input() is False
        assert manager.get_power_supply().get_output() is False

    run_dir = store.run_directory(run.run_id)
    lines = (run_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2

    with (run_dir / "results.csv").open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    assert [row["status"] for row in rows] == ["PASS", "PASS"]
    assert rows[0]["data_source"] == "behavioral_model"

    metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["data_mode"] == "SIMULATION"
    assert (run_dir / "test_cases_snapshot.yaml").exists()

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["summary"]["pass_count"] == 2

    assert sqlite_store.count_results(run.run_id) == 2
    assert store.result_count(run.run_id) == 2
    assert sqlite_store.get_run(run.run_id)["status"] == "COMPLETED"


def test_engine_validation_suite_hits_all_branches(tmp_path):
    cases = load_test_cases(EV_CASES)
    suites = load_test_suites(EV_SUITES, [case.case_id for case in cases])
    suite = suites[0]

    with InstrumentManager(CONFIG) as manager:
        suite_runner, _, sqlite_store, _ = _suite_runner(manager, tmp_path)
        run = suite_runner.run_suite(suite, cases)

        assert manager.get_power_supply().get_output() is False

    assert [result.status for result in run.results] == [
        TestStatus.FAIL,
        TestStatus.FAIL,
        TestStatus.SKIP,
        TestStatus.ERROR,
    ]
    assert "OVERCURRENT" in run.results[0].error_message
    assert "vout" in run.results[1].error_message
    assert "未访问仪器" in run.results[2].error_message
    assert "efficiency_percent" in run.results[3].error_message
    assert run.summary["pass_rate"] == 0.0
    assert run.summary["completion_rate"] == 75.0
    assert sqlite_store.count_results(run.run_id) == 4


def test_data_quality_error_is_reported_as_error(tmp_path):
    cases = load_test_cases(CASES)
    # 测试专用：绕过配置校验把模型效率改成 150%，制造“效率 >100%”数据质量异常
    dut = VirtualDUT()
    dut.nominal_efficiency = 1.5

    with InstrumentManager(CONFIG) as manager:
        suite_runner, store, _, _ = _suite_runner(manager, tmp_path, dut=dut)
        suite = TestSuite(
            suite_id="DQ",
            name="数据质量验证",
            case_ids=("TC001",),
            stop_on_fail=False,
            stop_on_error=False,
        )
        run = suite_runner.run_suite(suite, cases)

    result = run.results[0]
    assert result.status is TestStatus.ERROR
    assert "数据质量" in result.error_message
    assert result.quality_issues


def test_stop_on_fail_marks_remaining_as_skip(tmp_path):
    cases = load_test_cases(EV_CASES)
    by_id = {case.case_id: case for case in cases}
    suite = TestSuite(
        suite_id="STOP",
        name="停止条件验证",
        case_ids=("EV001", "EV002"),
        stop_on_fail=True,
        stop_on_error=True,
    )

    with InstrumentManager(CONFIG) as manager:
        suite_runner, _, _, _ = _suite_runner(manager, tmp_path)
        run = suite_runner.run_suite(suite, [by_id["EV001"], by_id["EV002"]])

    assert [result.status for result in run.results] == [
        TestStatus.FAIL,
        TestStatus.SKIP,
    ]
    assert "未执行" in run.results[1].error_message
    assert "FAIL" in run.stop_reason
