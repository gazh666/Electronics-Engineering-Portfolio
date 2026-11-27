"""服务层测试：真实 PyVISA-sim 执行，所有存储写入临时目录。"""

from __future__ import annotations

import csv
import io
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from storage.sqlite_store import SQLiteStore
from ui.service import (
    MAX_SWEEP_POINTS,
    TaskBusyError,
    TestLabService,
    exclusive_task,
    task_is_running,
)

import yaml

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def service(tmp_path: Path) -> TestLabService:
    results_root = tmp_path / "results"
    return TestLabService(
        results_root=results_root,
        db_path=results_root / "testlab.db",
        reliability_root=results_root / "reliability",
    )


# ---------------------------------------------------------------------------
# 配置加载与输入校验（不触碰仪器）
# ---------------------------------------------------------------------------


def test_service_loads_configured_cases_and_suites(service: TestLabService):
    cases = service.list_test_cases()
    suites = service.list_test_suites()
    assert len(cases) == 12
    assert {suite["suite_id"] for suite in suites} == {
        "SUITE-SMOKE",
        "SUITE-PROTECTION",
        "SUITE-REGRESSION",
        "SUITE005",
    }
    assert all(suite["case_count"] == len(suite["cases"]) for suite in suites)


def test_unknown_suite_rejected(service: TestLabService):
    with pytest.raises(ValueError, match="不存在"):
        service.run_test_suite("SUITE-NOT-EXIST")


def test_selected_cases_requires_non_empty(service: TestLabService):
    with pytest.raises(ValueError, match="至少选择"):
        service.run_selected_cases([])


def test_selected_cases_rejects_duplicates(service: TestLabService):
    with pytest.raises(ValueError, match="不能重复"):
        service.run_selected_cases(["TC001", "TC001"])


def test_selected_cases_rejects_unknown(service: TestLabService):
    with pytest.raises(ValueError, match="未知测试用例"):
        service.run_selected_cases(["TC001", "TC999"])


def test_estimate_sweep_points(service: TestLabService):
    assert service.estimate_sweep_points("load", currents=[0, 0.5, 1.0]) == 3
    assert service.estimate_sweep_points(
        "matrix", input_voltages=[9, 12], load_currents=[0, 1, 2]
    ) == 6
    with pytest.raises(ValueError):
        service.estimate_sweep_points("unknown")


# ---------------------------------------------------------------------------
# 普通测试执行与持久化
# ---------------------------------------------------------------------------


def test_run_suite_smoke_writes_jsonl_csv_and_sqlite(service: TestLabService):
    payload = service.run_test_suite("SUITE-SMOKE")
    assert payload["status"] == "COMPLETED"
    assert payload["summary"]["pass_count"] == 2
    assert payload["summary"]["fail_count"] == 0
    assert payload["summary"]["error_count"] == 0
    assert len(payload["results"]) == 2

    run_dir = Path(payload["run_directory"])
    assert (run_dir / "results.jsonl").exists()
    assert (run_dir / "results.csv").exists()
    assert (run_dir / "summary.json").exists()

    lines = (run_dir / "results.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert all(json.loads(line)["run_id"] == payload["run_id"] for line in lines)

    store = SQLiteStore(service.db_path)
    assert len(store.get_results_by_run(payload["run_id"])) == 2
    assert store.get_run_summary(payload["run_id"])["PASS"] == 2
    assert store.get_run_summary(payload["run_id"])["FAIL"] == 0


def test_progress_callback_is_after_persistence(service: TestLabService):
    snapshots: list[tuple[int, int, int]] = []

    def callback(current: int, total: int, result):
        stored = SQLiteStore(service.db_path).count_results(result.run_id)
        snapshots.append((current, total, stored))

    payload = service.run_test_suite("SUITE-SMOKE", progress_callback=callback)
    assert snapshots == [(1, 2, 1), (2, 2, 2)]
    assert payload["callback_errors"] == []


def test_stop_on_fail_appends_skip(service: TestLabService, tmp_path: Path):
    payload = {
        "version": "1.0",
        "test_cases": [
            {
                "id": "FAIL1",
                "name": "故意失败用例",
                "category": "normal",
                "vin": 12.0,
                "input_current_limit": 3.0,
                "load_current": 1.0,
                "expected_state": "NORMAL",
                "limits": {"vout": {"min": 5.5, "max": 6.0}},
            },
            {
                "id": "OK1",
                "name": "正常用例",
                "category": "normal",
                "vin": 12.0,
                "input_current_limit": 3.0,
                "load_current": 1.0,
                "expected_state": "NORMAL",
                "limits": {"vout": {"min": 4.9, "max": 5.1}},
            },
        ],
    }
    path = tmp_path / "stop_cases.yaml"
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    service.cases_config = path

    result = service.run_selected_cases(["FAIL1", "OK1"], stop_on_fail=True)
    statuses = [item["status"] for item in result["results"]]
    assert statuses == ["FAIL", "SKIP"]
    assert result["summary"]["fail_count"] == 1
    assert result["summary"]["skip_count"] == 1
    assert result["stop_reason"]


def test_dashboard_summary_uses_real_records(service: TestLabService):
    empty = service.get_dashboard_summary()
    assert empty["has_data"] is False
    assert empty["total_results"] == 0
    assert empty["pass_rate"] is None

    payload = service.run_test_suite("SUITE-SMOKE")
    summary = service.get_dashboard_summary()
    assert summary["has_data"] is True
    assert summary["total_runs"] == 1
    assert summary["total_results"] == 2
    assert summary["status_counts"]["PASS"] == 2
    assert summary["pass_rate"] == 100.0
    assert summary["categories"]
    assert summary["latest_run"]["run_id"] == payload["run_id"]


def test_history_filters_and_details(service: TestLabService):
    first = service.run_test_suite("SUITE-SMOKE")

    all_runs = service.list_history_runs()
    assert len(all_runs) == 1
    assert all_runs[0]["run_id"] == first["run_id"]
    assert all_runs[0]["counts"]["PASS"] == 2

    today = date.today()
    in_range = service.list_history_runs(
        start_date=today - timedelta(days=1), end_date=today + timedelta(days=1)
    )
    assert len(in_range) == 1
    out_of_range = service.list_history_runs(
        start_date=today + timedelta(days=5), end_date=today + timedelta(days=6)
    )
    assert out_of_range == []
    assert service.list_history_runs(mode="normal")
    assert service.list_history_runs(mode="reliability") == []
    assert service.list_history_runs(case_id="TC001")
    assert service.list_history_runs(case_id="TC999") == []
    assert service.list_history_runs(run_id_query=first["run_id"][:8])

    details = service.get_run_details(first["run_id"])
    assert details["summary"]["PASS"] == 2
    assert len(details["results"]) == 2
    assert details["results"][0]["checks"]
    assert details["fault_events"] == []
    assert details["is_reliability"] is False

    artifacts = service.get_run_artifacts(first["run_id"])
    assert artifacts["exists"] is True
    assert "metadata.json" in artifacts["files"]
    assert "results.jsonl" in artifacts["files"]


def test_export_csv_json_html(service: TestLabService):
    payload = service.run_test_suite("SUITE-SMOKE")
    csv_bytes = service.export_run_csv(payload["run_id"])
    rows = list(
        csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig")))
    )
    assert len(rows) == 2
    assert rows[0]["case_id"] == "TC001"

    json_payload = json.loads(service.export_run_json(payload["run_id"]))
    assert json_payload["summary"]["PASS"] == 2

    html_text = service.export_run_html(payload["run_id"]).decode("utf-8")
    assert "TestLab 运行报告" in html_text
    assert payload["run_id"] in html_text
    assert "SIMULATION" in html_text


def test_export_unknown_run_rejected(service: TestLabService):
    with pytest.raises(ValueError, match="运行不存在"):
        service.export_run_csv("not-exist")


# ---------------------------------------------------------------------------
# 仪器会话
# ---------------------------------------------------------------------------


def test_instrument_discovery(service: TestLabService):
    payload = service.discover_instruments()
    assert payload["data_source"] == "pyvisa-sim SCPI"
    assert len(payload["resources"]) == 3
    serials = {item["serial"] for item in payload["instruments"]}
    assert serials == {"PS001", "DMM001", "LOAD001"}
    assert all(item["status"] == "CONNECTED" for item in payload["instruments"])
    assert payload["final_close_error"] is None


def test_instrument_session_psu_sets_and_shuts_down(service: TestLabService):
    payload = service.run_instrument_session(
        "psu", voltage=12.0, current_limit=3.0, output=True
    )
    assert payload["ok"] is True
    assert "VirtualPowerSupply" in payload["identity"]
    assert payload["readback"]["voltage"] == pytest.approx(12.0)
    assert payload["readback"]["current_limit"] == pytest.approx(3.0)
    assert payload["readback"]["output"] is True
    assert payload["cleanup_status"] == "VERIFIED_OFF"
    assert payload["cleanup_errors"] == []


def test_instrument_session_load_rejects_non_cc_but_cleans_up(service: TestLabService):
    payload = service.run_instrument_session(
        "load", mode="CV", load_current=1.0
    )
    assert payload["ok"] is False
    assert "CC" in payload["error"]
    assert payload["cleanup_status"] == "VERIFIED_OFF"


def test_instrument_session_dmm_is_static_mock(service: TestLabService):
    payload = service.run_instrument_session("dmm")
    assert payload["ok"] is True
    assert payload["data_source"] == "static_mock"
    assert payload["measurements"]["voltage"]["source"] == "static_mock"
    assert payload["cleanup_status"] == "NOT_APPLICABLE"


def test_instrument_session_unknown_instrument(service: TestLabService):
    with pytest.raises(ValueError, match="未知仪器"):
        service.run_instrument_session("scope")


# ---------------------------------------------------------------------------
# 性能扫描
# ---------------------------------------------------------------------------


def test_sweep_rejects_over_limit(service: TestLabService):
    currents = [index * (2.5 / MAX_SWEEP_POINTS) for index in range(MAX_SWEEP_POINTS + 1)]
    with pytest.raises(ValueError, match="超过上限"):
        service.run_performance_sweep("load", currents=currents)


def test_sweep_rejects_empty_points(service: TestLabService):
    with pytest.raises(ValueError, match="不能为空"):
        service.run_performance_sweep("load", currents=[])


def test_sweep_load_runs_real_points(service: TestLabService):
    payload = service.run_performance_sweep(
        "load", vin=12.0, currents=[0.0, 0.5, 1.0]
    )
    assert payload["points"] == 3
    assert len(payload["records"]) == 3
    assert payload["cleanup_status"] == "VERIFIED_OFF"
    assert payload["summary"]["normal_points"] == 3
    assert all(
        row["data_source"] == "behavioral_model" for row in payload["records"]
    )
    # 空载效率不可定义，不能填 0 或 100
    assert payload["records"][0]["efficiency_percent"] is None
    assert payload["summary"]["min_efficiency_percent"] is not None


def test_sweep_matrix_protection_is_separate(service: TestLabService):
    payload = service.run_performance_sweep(
        "matrix", input_voltages=[9.0, 12.0], load_currents=[0.0, 2.5]
    )
    assert payload["points"] == 4
    states = {row["dut_state"] for row in payload["records"]}
    assert "NORMAL" in states
    assert payload["summary"]["normal_points"] + payload["summary"]["protection_points"] == 4


# ---------------------------------------------------------------------------
# 可靠性与任务锁
# ---------------------------------------------------------------------------


def test_fault_scenario_list_has_expectations(service: TestLabService):
    scenarios = service.list_fault_scenarios()
    assert [item["scenario_id"] for item in scenarios] == [
        f"F00{index}" for index in range(1, 10)
    ]
    f001 = scenarios[0]
    assert f001["fault_type"] == "TIMEOUT"
    assert f001["expected"]["expected_status"] == "PASS"
    assert f001["expected"]["expected_retry_count"] == 1


def test_run_fault_scenario_f001_recovers_with_retry(service: TestLabService):
    payload = service.run_fault_scenario("F001")
    assert payload["business_status"] == "PASS"
    assert payload["retry_count"] == 1
    assert payload["recovered"] is True
    assert payload["retry_exhausted"] is False
    assert payload["cleanup_status"] == "VERIFIED_OFF"
    assert payload["experiment"]["passed"] is True
    assert payload["events"]
    assert any(
        event.get("event_type") == "FAULT_INJECTED" for event in payload["events"]
    )

    store = SQLiteStore(service.db_path)
    assert store.count_fault_events(payload["run_id"]) == len(payload["events"])
    details = service.get_run_details(payload["run_id"])
    assert details["is_reliability"] is True
    assert details["fault_events"]


def test_run_reliability_validation_subset(service: TestLabService):
    payload = service.run_reliability_validation(["F001", "F002"])
    assert payload["summary"]["scenario_count"] == 2
    assert payload["summary"]["experiment_passed_count"] == 2
    assert payload["summary"]["total_retries"] == 3
    statuses = {row["scenario_id"]: row["business_status"] for row in payload["scenarios"]}
    assert statuses == {"F001": "PASS", "F002": "ERROR"}


def test_task_lock_is_exclusive_and_released():
    with exclusive_task():
        assert task_is_running() is True
        with pytest.raises(TaskBusyError):
            with exclusive_task():
                pass
    assert task_is_running() is False


def test_service_rejects_concurrent_task(service: TestLabService):
    with exclusive_task():
        with pytest.raises(TaskBusyError):
            service.run_test_suite("SUITE-SMOKE")
    assert service.run_test_suite("SUITE-SMOKE")["status"] == "COMPLETED"
