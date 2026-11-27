"""Web 报告导出：生成、下载不重跑、非法 run_id 与路径隔离。"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from reports.generator import ReportError
from ui.service import TestLabService

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def results_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "results"
    monkeypatch.setenv("TESTLAB_RESULTS_ROOT", str(root))
    monkeypatch.setenv("TESTLAB_DB_PATH", str(root / "testlab.db"))
    return root


def _service(root: Path) -> TestLabService:
    return TestLabService(
        results_root=root,
        db_path=root / "testlab.db",
        reliability_root=root / "reliability",
    )


def _app() -> AppTest:
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)


def _count_results(db_path: Path) -> int:
    if not db_path.exists():
        return 0
    with closing(sqlite3.connect(db_path)) as connection:
        return int(connection.execute("SELECT COUNT(*) FROM test_results").fetchone()[0])


def _radio(at: AppTest, label: str):
    return next(item for item in at.radio if item.label == label)


def _button(at: AppTest, label: str):
    return next(item for item in at.button if item.label == label)


def test_service_generates_report_without_rerun(results_root: Path):
    service = _service(results_root)
    payload = service.run_test_suite("SUITE-SMOKE")
    run_id = payload["run_id"]
    count = _count_results(results_root / "testlab.db")

    first = service.generate_run_report(run_id)
    assert Path(first["path"]).is_file()
    assert first["file_name"].startswith(f"test_report_{run_id}_")
    assert Path(first["path"]).parent == (results_root / "reports").resolve()
    content = Path(first["path"]).read_text(encoding="utf-8")
    assert run_id in content
    assert "SIMULATION" in content

    second = service.generate_run_report(run_id)
    assert second["path"] != first["path"]
    assert Path(second["path"]).is_file()

    # 生成与读取报告不得新增测试结果
    assert _count_results(results_root / "testlab.db") == count


def test_service_rejects_invalid_run_id(results_root: Path):
    service = _service(results_root)
    service.run_test_suite("SUITE-SMOKE")
    for bad in ("../escape", "a/b", "no_such_run"):
        with pytest.raises(ReportError):
            service.generate_run_report(bad)


def test_history_page_generate_and_download_does_not_rerun(results_root: Path):
    service = _service(results_root)
    service.run_test_suite("SUITE-SMOKE")
    count = _count_results(results_root / "testlab.db")

    at = _app().run()
    _radio(at, "功能导航").set_value("历史记录")
    at.run()
    assert not at.exception

    _button(at, "生成综合报告").click()
    at.run(timeout=120)
    assert not at.exception

    labels = [item.label for item in at.get("download_button")]
    assert "下载综合报告 (HTML)" in labels
    download = next(
        item
        for item in at.get("download_button")
        if item.label == "下载综合报告 (HTML)"
    )
    download.click().run()
    assert _count_results(results_root / "testlab.db") == count
