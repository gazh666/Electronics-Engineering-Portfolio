"""综合工程测试报告：正常/FAIL/ERROR/SKIP/清理失败/中断/快照缺失/转义/NaN。

所有用例使用临时数据库与临时结果目录，不触碰 ``results/testlab.db``。
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
import yaml

from core.paths import RESULTS_DIR
from engine.models import TestResult, TestStatus
from reports.generator import (
    ReportError,
    build_test_report,
    generate_test_report,
    render_report_html,
    validate_run_id,
    write_html_report,
)
from storage.result_store import ResultStore
from storage.sqlite_store import SQLiteStore

RUN_ID = "run_report_test"


def _result(
    index: int,
    case_id: str,
    status: TestStatus,
    *,
    vout: float | None = 5.0,
    efficiency: float | None = 90.0,
    error: str | None = None,
) -> TestResult:
    return TestResult(
        run_id=RUN_ID,
        case_id=case_id,
        case_name=f"用例{case_id}",
        started_at="2026-01-01T00:00:00.000+00:00",
        finished_at="2026-01-01T00:00:00.100+00:00",
        duration_ms=100.0,
        status=status,
        expected_state="NORMAL",
        actual_state="NORMAL" if status is not TestStatus.ERROR else None,
        raw_data={
            "vin_setpoint": 12.0,
            "input_current_limit": 3.0,
            "load_current_setpoint": 1.0,
            "vin": 12.0,
            "iin": 0.46,
            "vout": vout,
            "iout": 1.0,
            "pin": 5.52,
            "pout": 4.98,
            "source": "behavioral_model",
        },
        metrics={"efficiency_percent": efficiency, "voltage_error_percent": -0.4},
        error_message=error,
        data_source="behavioral_model",
        execution_index=index,
    )


@pytest.fixture()
def env(tmp_path: Path):
    results_root = tmp_path / "results"
    db_path = tmp_path / "testlab.db"
    store = SQLiteStore(db_path)
    store.start_run(
        run_id=RUN_ID,
        suite_id="SUITE-TEST",
        suite_name="报告测试方案",
        planned_count=4,
    )
    yield store, results_root, db_path
    # 关闭所有连接，避免 Windows 临时目录清理失败


def _write_snapshots(results_root: Path) -> None:
    directory = results_root / "automation" / f"run_{RUN_ID}"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "metadata.json").write_text(
        json.dumps(
            {
                "run_id": RUN_ID,
                "environment": {"python": "3.11.18", "platform": "test"},
                "data_mode": "SIMULATION",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (directory / "dut_config_snapshot.yaml").write_text(
        yaml.safe_dump(
            {
                "dut": {
                    "name": "Virtual Buck DC-DC Converter",
                    "nominal_input_voltage": 12.0,
                    "min_input_voltage": 9.0,
                    "max_input_voltage": 16.0,
                    "nominal_output_voltage": 5.0,
                    "max_output_current": 2.0,
                    "output_resistance": 0.02,
                    "nominal_efficiency": 0.90,
                    "protection_strategy": "模拟保护",
                }
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    (directory / "test_cases_snapshot.yaml").write_text(
        yaml.safe_dump(
            {
                "version": "1.0",
                "test_cases": [
                    {
                        "id": "TC001",
                        "name": "标称输入",
                        "limits": {"vout": {"min": 4.9, "max": 5.1}},
                    }
                ],
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )


def _finish(store: SQLiteStore, status: str = "COMPLETED") -> None:
    store.finish_run(
        RUN_ID,
        status,
        {
            "summary": {
                "total_cases": 4,
                "executed_cases": 4,
                "pass_count": 2,
                "fail_count": 1,
                "error_count": 1,
                "skip_count": 1,
                "pass_rate": 66.67,
                "completion_rate": 100.0,
            },
            "reliability": {
                "scenario_count": 1,
                "total_fault_injections": 1,
                "retry_count": 1,
                "recovery_rate": 100.0,
                "experiment_pass_count": 1,
                "experiment_fail_count": 0,
            },
        },
    )


def test_report_normal_pass(env, tmp_path: Path):
    store, results_root, db_path = env
    _write_snapshots(results_root)
    store.save_result(_result(0, "TC001", TestStatus.PASS))
    _finish(store)

    report = build_test_report(RUN_ID, db_path=db_path, results_root=results_root)
    assert report["summary"]["pass_count"] == 1
    assert "符合预设验证要求" in report["conclusion"]

    html = render_report_html(report)
    assert "综合工程测试报告" in html
    assert "Virtual Buck DC-DC Converter" in html
    assert "behavioral_model" in html
    assert "TC001" in html

    path = write_html_report(report, html, results_root=results_root)
    assert path.is_file()
    assert path.parent == (results_root / "reports").resolve()


def test_report_fail_and_error_and_skip(env):
    store, results_root, db_path = env
    store.save_result(_result(0, "TC001", TestStatus.PASS))
    store.save_result(
        _result(1, "TC002", TestStatus.FAIL, vout=5.3, error="vout 超限")
    )
    store.save_result(
        _result(2, "TC003", TestStatus.ERROR, efficiency=None, error="数据质量错误")
    )
    store.save_result(_result(3, "TC004", TestStatus.SKIP, error="未执行"))
    _finish(store)

    report = build_test_report(RUN_ID, db_path=db_path, results_root=results_root)
    html = render_report_html(report)
    assert "不存在" not in report["conclusion"]
    assert "异常" in report["conclusion"]  # ERROR 优先
    assert "FAIL" in html and "SKIP" in html
    assert "vout 超限" in html


def test_report_cleanup_not_verified(env):
    store, results_root, db_path = env
    store.save_result(_result(0, "TC001", TestStatus.PASS))
    store.save_fault_event(
        {
            "event_id": "evt-cleanup",
            "run_id": RUN_ID,
            "event_type": "CLEANUP_FAILED",
            "timestamp": "2026-01-01T00:00:01.000+00:00",
            "cleanup_status": "NOT_VERIFIED",
            "message": "输出关闭未确认",
        }
    )
    _finish(store)

    report = build_test_report(RUN_ID, db_path=db_path, results_root=results_root)
    assert "未确认" in report["conclusion"]
    assert "NOT_VERIFIED" in render_report_html(report)


def test_report_aborted_run(env):
    store, results_root, db_path = env
    store.save_result(_result(0, "TC001", TestStatus.PASS))
    _finish(store, status="ABORTED")
    report = build_test_report(RUN_ID, db_path=db_path, results_root=results_root)
    assert "未完整结束" in report["conclusion"]


def test_report_missing_snapshot(env):
    store, results_root, db_path = env
    store.save_result(_result(0, "TC001", TestStatus.PASS))
    _finish(store)
    report = build_test_report(RUN_ID, db_path=db_path, results_root=results_root)
    html = render_report_html(report)
    assert "无法追溯" in html
    assert "性能限值" in html


def test_report_chinese_and_escaping(env):
    store, results_root, db_path = env
    result = _result(0, "TC<01>", TestStatus.PASS)
    result.case_name = "中文<script>alert(1)</script>"
    result.error_message = "错误 & <b>加粗</b>"
    store.save_result(result)
    _finish(store)

    report = build_test_report(RUN_ID, db_path=db_path, results_root=results_root)
    html = render_report_html(report)
    assert "中文" in html
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "&amp;" in html


def test_report_nan_and_infinity(env):
    store, results_root, db_path = env
    result = _result(0, "TC001", TestStatus.ERROR)
    result.raw_data = {"vout": "NaN", "iout": "Infinity", "pin": None}
    result.metrics = {"efficiency_percent": None}
    store.save_result(result)
    _finish(store)

    report = build_test_report(RUN_ID, db_path=db_path, results_root=results_root)
    html = render_report_html(report)
    assert "NaN" in html and "Infinity" in html
    assert ">None<" not in html


def test_report_unknown_run_id(env):
    _, results_root, db_path = env
    with pytest.raises(ReportError):
        build_test_report("not_exists", db_path=db_path, results_root=results_root)


def test_report_rejects_unsafe_run_id():
    for bad in ("../etc", "a/b", "..", "", "run id", "x\\y"):
        with pytest.raises(ReportError):
            validate_run_id(bad)


def test_report_no_overwrite(env):
    store, results_root, db_path = env
    store.save_result(_result(0, "TC001", TestStatus.PASS))
    _finish(store)
    report = build_test_report(RUN_ID, db_path=db_path, results_root=results_root)
    html = render_report_html(report)
    first = write_html_report(report, html, results_root=results_root)
    second = write_html_report(report, html, results_root=results_root)
    assert first != second
    assert first.is_file() and second.is_file()


def test_report_rejects_output_outside_results(env, tmp_path: Path):
    store, results_root, db_path = env
    store.save_result(_result(0, "TC001", TestStatus.PASS))
    _finish(store)
    report = build_test_report(RUN_ID, db_path=db_path, results_root=results_root)
    with pytest.raises(ReportError):
        write_html_report(
            report,
            "<html></html>",
            results_root=results_root,
            output_dir=tmp_path / "outside",
        )


def test_generate_report_end_to_end(env):
    store, results_root, db_path = env
    _write_snapshots(results_root)
    store.save_result(_result(0, "TC001", TestStatus.PASS))
    _finish(store)
    payload = generate_test_report(
        RUN_ID, db_path=db_path, results_root=results_root
    )
    assert Path(payload["path"]).is_file()
    assert payload["run_id"] == RUN_ID
    content = Path(payload["path"]).read_text(encoding="utf-8")
    assert RUN_ID in content
    assert "测试结论" in content


def test_report_does_not_touch_real_database():
    """确认默认路径未被测试修改，真实数据库仍然可访问。"""
    from contextlib import closing

    real_db = RESULTS_DIR / "testlab.db"
    if real_db.exists():
        with closing(sqlite3.connect(real_db)) as conn:
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_report_store_kind(env):
    """ResultStore 与报告使用同一结果根目录约定。"""
    _, results_root, _ = env
    store = ResultStore(results_root / "automation")
    assert store.run_directory(RUN_ID).parent == results_root / "automation"
