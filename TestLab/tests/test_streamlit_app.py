"""Streamlit AppTest：六页渲染、真实执行、状态保持与输入校验。

AppTest 使用临时数据库与临时结果目录，不污染 results/ 下的真实历史。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from ui.service import TestLabService

ROOT = Path(__file__).resolve().parents[1]
PAGES = [
    "运行概览",
    "仪器控制",
    "自动化测试",
    "性能扫描",
    "可靠性验证",
    "历史记录",
]


@pytest.fixture()
def results_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "results"
    monkeypatch.setenv("TESTLAB_RESULTS_ROOT", str(root))
    monkeypatch.setenv("TESTLAB_DB_PATH", str(root / "testlab.db"))
    return root


def _app() -> AppTest:
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)


def _radio(at: AppTest, label: str):
    return next(item for item in at.radio if item.label == label)


def _button(at: AppTest, label: str):
    return next(item for item in at.button if item.label == label)


def _selectbox(at: AppTest, label: str):
    return next(item for item in at.selectbox if item.label == label)


def _number(at: AppTest, label: str):
    return next(item for item in at.number_input if item.label == label)


def _count_results(db_path: Path) -> int:
    if not db_path.exists():
        return 0
    connection = sqlite3.connect(db_path)
    try:
        return int(
            connection.execute("SELECT COUNT(*) FROM test_results").fetchone()[0]
        )
    finally:
        connection.close()


def test_initial_dashboard_empty_state_and_no_execution(results_root: Path):
    at = _app().run()
    assert not at.exception
    assert not (results_root / "testlab.db").exists()
    rendered = " ".join(item.value for item in at.markdown)
    assert "暂无测试历史" in rendered
    navigation = _radio(at, "功能导航")
    assert navigation.options == PAGES
    assert navigation.value == "运行概览"


def test_all_six_pages_render_without_exception(results_root: Path):
    at = _app().run()
    for page in PAGES:
        _radio(at, "功能导航").set_value(page)
        at.run()
        assert not at.exception, f"{page}: {[str(e) for e in at.exception]}"
    assert _count_results(results_root / "testlab.db") == 0


def test_automation_submit_runs_real_suite(results_root: Path):
    at = _app().run()
    _radio(at, "功能导航").set_value("自动化测试")
    at.run()
    assert _count_results(results_root / "testlab.db") == 0

    _button(at, "开始执行").click()
    at.run(timeout=120)
    assert not at.exception
    assert at.session_state["last_run_id"]
    assert len(at.session_state["last_test_results"]) == 2
    assert at.session_state["last_test_summary"]["pass_count"] == 2
    assert at.session_state["task_running"] is False
    assert _count_results(results_root / "testlab.db") == 2
    assert [item.label for item in at.get("download_button")] == [
        "下载 CSV",
        "下载 JSON",
        "下载 HTML 报告",
    ]


def test_state_persists_across_navigation_without_reexecution(results_root: Path):
    at = _app().run()
    _radio(at, "功能导航").set_value("自动化测试")
    at.run()
    _button(at, "开始执行").click()
    at.run(timeout=120)
    run_id = at.session_state["last_run_id"]
    assert run_id
    count = _count_results(results_root / "testlab.db")
    assert count == 2

    for page in ("运行概览", "性能扫描", "历史记录", "自动化测试"):
        _radio(at, "功能导航").set_value(page)
        at.run()
        assert not at.exception
        assert at.session_state["last_run_id"] == run_id
        assert len(at.session_state["last_test_results"]) == 2
        assert _count_results(results_root / "testlab.db") == count


def test_custom_mode_rejects_empty_selection(results_root: Path):
    at = _app().run()
    _radio(at, "功能导航").set_value("自动化测试")
    at.run()
    _radio(at, "执行方式").set_value("自定义用例")
    at.run()
    assert not at.exception
    next(item for item in at.multiselect if item.label == "选择用例").set_value([])
    _button(at, "开始执行").click()
    at.run()
    assert not at.exception
    assert at.session_state["task_running"] is False
    assert at.session_state["last_error"]
    assert any("至少选择" in item.value for item in at.error)
    assert _count_results(results_root / "testlab.db") == 0


def test_performance_over_limit_is_blocked(results_root: Path):
    at = _app().run()
    _radio(at, "功能导航").set_value("性能扫描")
    at.run()
    _radio(at, "扫描类型").set_value("二维扫描")
    at.run()

    _number(at, "Vin 起点 (V)").set_value(9.0)
    _number(at, "Vin 终点 (V)").set_value(16.0)
    _number(at, "Iload 起点 (A)").set_value(0.0)
    _number(at, "Iload 终点 (A)").set_value(2.5)
    _number(at, "Vin 步长 (V)").set_value(0.1)
    _number(at, "Iload 步长 (A)").set_value(0.01)
    at.run()

    assert not at.exception
    assert any("超过上限" in item.value for item in at.error)
    assert _button(at, "开始扫描").disabled is True
    assert _count_results(results_root / "testlab.db") == 0


def test_download_button_does_not_reexecute_test(results_root: Path):
    at = _app().run()
    _radio(at, "功能导航").set_value("自动化测试")
    at.run()
    _button(at, "开始执行").click()
    at.run(timeout=120)
    run_id = at.session_state["last_run_id"]
    count = _count_results(results_root / "testlab.db")
    assert count == 2

    at.get("download_button")[0].click().run()
    assert not at.exception
    assert at.session_state["last_run_id"] == run_id
    assert _count_results(results_root / "testlab.db") == count


def test_running_flag_is_reported_and_recoverable(results_root: Path):
    at = _app().run()
    at.session_state["task_running"] = True
    _radio(at, "功能导航").set_value("自动化测试")
    at.run()
    assert not at.exception
    warnings = " ".join(item.value for item in at.warning)
    assert "正在执行" in warnings or "请等待" in warnings

    at.session_state["task_running"] = False
    at.run()
    assert not at.exception
    _button(at, "开始执行").click()
    at.run(timeout=120)
    assert not at.exception
    assert at.session_state["task_running"] is False
    assert _count_results(results_root / "testlab.db") == 2


def test_reliability_page_runs_selected_scenario(results_root: Path):
    at = _app().run()
    _radio(at, "功能导航").set_value("可靠性验证")
    at.run()
    assert not at.exception
    _button(at, "运行选中场景").click()
    at.run(timeout=120)
    assert not at.exception
    memory = at.session_state["last_reliability_results"]
    assert memory["scenario_id"] == "F001"
    assert memory["business_status"] == "PASS"
    assert memory["retry_count"] == 1
    assert memory["experiment"]["passed"] is True
    assert memory["events"]
    assert at.session_state["task_running"] is False


def test_history_displays_reliability_run(results_root: Path):
    service = TestLabService(
        results_root=results_root,
        db_path=results_root / "testlab.db",
        reliability_root=results_root / "reliability",
    )
    fault = service.run_fault_scenario("F001")
    assert fault["experiment"]["passed"] is True

    at = _app().run()
    _radio(at, "功能导航").set_value("历史记录")
    at.run()
    assert not at.exception
    detail_select = _selectbox(at, "查看运行详情")
    assert any("REL-F001" in option for option in detail_select.options)
    assert any(
        "可靠性" in option or "F001" in option for option in detail_select.options
    )
