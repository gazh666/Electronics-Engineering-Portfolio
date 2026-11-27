"""会话状态测试：默认键、任务标志与结果缓存，不保存资源对象。"""

from __future__ import annotations

from ui.state import (
    begin_task,
    default_state,
    ensure_state,
    finish_task,
    remember_instrument_snapshot,
    remember_performance,
    remember_reliability,
    remember_test_run,
    reset_results,
    set_error,
)


def test_default_state_contains_required_keys():
    state = default_state()
    assert state["task_running"] is False
    assert state["last_run_id"] is None
    assert state["last_test_results"] is None
    assert state["last_test_summary"] is None
    assert state["last_instrument_snapshot"] is None
    assert state["last_performance_results"] is None
    assert state["last_reliability_results"] is None
    assert state["last_error"] is None


def test_ensure_state_does_not_override_existing_values():
    state = {"last_run_id": "run-1", "navigation": "性能扫描"}
    ensure_state(state)
    assert state["last_run_id"] == "run-1"
    assert state["navigation"] == "性能扫描"
    assert state["task_running"] is False


def test_task_lifecycle_and_error():
    state = default_state()
    begin_task(state)
    assert state["task_running"] is True
    set_error(state, "boom")
    assert state["last_error"] == "boom"
    finish_task(state)
    assert state["task_running"] is False


def test_remember_test_run_keeps_summary_and_results():
    state = default_state()
    payload = {
        "run_id": "run-9",
        "suite_id": "SUITE-SMOKE",
        "suite_name": "冒烟测试",
        "status": "COMPLETED",
        "summary": {"pass_count": 2, "pass_rate": 100.0},
        "results": [{"case_id": "TC001", "status": "PASS"}],
        "stop_reason": None,
        "storage_errors": [],
        "callback_errors": [],
    }
    remember_test_run(state, payload)
    assert state["last_run_id"] == "run-9"
    assert state["last_test_results"][0]["case_id"] == "TC001"
    assert state["last_test_summary"]["suite_id"] == "SUITE-SMOKE"
    assert state["last_test_summary"]["pass_count"] == 2


def test_remember_other_payloads():
    state = default_state()
    remember_instrument_snapshot(state, {"instrument": "psu"})
    remember_performance(state, {"sweep_type": "load"})
    remember_reliability(state, {"scenario_id": "F001"})
    assert state["last_instrument_snapshot"] == {"instrument": "psu"}
    assert state["last_performance_results"] == {"sweep_type": "load"}
    assert state["last_reliability_results"] == {"scenario_id": "F001"}


def test_reset_results_preserves_navigation():
    state = default_state()
    state["navigation"] = "历史记录"
    state["last_run_id"] = "run-1"
    state["last_test_results"] = [{"case_id": "TC001"}]
    state["last_error"] = "x"
    reset_results(state)
    assert state["navigation"] == "历史记录"
    assert state["last_run_id"] is None
    assert state["last_test_results"] is None
    assert state["last_error"] is None


def test_default_state_has_no_connection_like_objects():
    state = default_state()
    for value in state.values():
        assert not hasattr(value, "close")
        assert not hasattr(value, "cursor")
