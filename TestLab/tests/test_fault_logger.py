"""故障事件日志单元测试。"""

from __future__ import annotations

import json

from reliability.fault_logger import EventType, FaultLogger, new_event


def test_logger_creates_file_and_writes_standard_event(tmp_path):
    path = tmp_path / "events.jsonl"
    logger = FaultLogger(path, run_id="RUN1")
    event = logger.emit(
        new_event(EventType.FAULT_INJECTED, operation="VOLT?", fault_type="TIMEOUT")
    )
    assert event["event_id"]
    assert event["timestamp"]
    assert event["run_id"] == "RUN1"
    assert event["details"] == {}

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["event_type"] == "FAULT_INJECTED"
    assert payload["operation"] == "VOLT?"


def test_logger_event_ids_are_unique(tmp_path):
    logger = FaultLogger(tmp_path / "events.jsonl")
    first = logger.emit(new_event(EventType.ATTEMPT_FAILED))
    second = logger.emit(new_event(EventType.ATTEMPT_FAILED))
    assert first["event_id"] != second["event_id"]


def test_logger_serializes_nan_and_infinity_as_strings(tmp_path):
    path = tmp_path / "events.jsonl"
    logger = FaultLogger(path)
    logger.emit(
        new_event(
            EventType.FAULT_INJECTED,
            original_value=float("nan"),
            injected_value=float("inf"),
            details={"negative": float("-inf")},
        )
    )
    payload = json.loads(path.read_text(encoding="utf-8").strip())
    assert payload["original_value"] == "NaN"
    assert payload["injected_value"] == "Infinity"
    assert payload["details"]["negative"] == "-Infinity"


def test_logger_normalizes_enum_values(tmp_path):
    path = tmp_path / "events.jsonl"
    logger = FaultLogger(path)
    logger.emit(
        new_event(
            EventType.CLEANUP_COMPLETED,
            fault_type=EventType.FAULT_INJECTED,
            cleanup_status=EventType.CLEANUP_COMPLETED,
        )
    )
    payload = json.loads(path.read_text(encoding="utf-8").strip())
    assert payload["fault_type"] == "FAULT_INJECTED"
    assert payload["cleanup_status"] == "CLEANUP_COMPLETED"


def test_logger_write_failure_is_reported_not_raised(tmp_path):
    logger = FaultLogger(tmp_path / "events.jsonl")
    # 把目标改成目录，使打开写入失败
    logger.path = tmp_path
    event = logger.emit(new_event(EventType.FAULT_INJECTED))
    assert event["event_type"] == "FAULT_INJECTED"
    assert len(logger.events) == 1
    assert logger.has_write_errors
    assert "写入失败" in logger.write_errors[0]


def test_logger_rejects_missing_event_type(tmp_path):
    logger = FaultLogger(tmp_path / "events.jsonl")
    try:
        logger.emit({"run_id": "RUN1"})
    except ValueError as exc:
        assert "event_type" in str(exc)
    else:
        raise AssertionError("缺少 event_type 必须被拒绝")


def test_new_event_preserves_existing_id_and_timestamp():
    event = new_event(
        "RECOVERED",
        event_id="fixed-id",
        timestamp="2026-01-01T00:00:00+00:00",
        run_id="RUN1",
    )
    assert event["event_id"] == "fixed-id"
    assert event["timestamp"] == "2026-01-01T00:00:00+00:00"
