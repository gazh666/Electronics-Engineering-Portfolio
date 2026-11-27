"""任务状态模型测试（第九阶段 Task 8）。"""

from __future__ import annotations

import json

import pytest

from jobs.models import (
    ACTIVE_STATUSES,
    TERMINAL_STATUSES,
    JobRecord,
    JobStatus,
    validate_job_id,
)

VALID_ID = "job_20261125_120000_deadbeef"


def _record(**overrides) -> JobRecord:
    payload = {
        "job_id": VALID_ID,
        "job_type": "circuit_simulation",
        "status": JobStatus.QUEUED,
        "created_at": "2026-11-25T12:00:00",
    }
    payload.update(overrides)
    return JobRecord(**payload)


def test_valid_job_id_accepted():
    assert validate_job_id(VALID_ID) == VALID_ID


@pytest.mark.parametrize(
    "value",
    [
        "job_2026_120000_deadbeef",
        "job_20261125_120000_DEADBEEF",
        "job_20261125_120000_deadbeef0",
        "task_20261125_120000_deadbeef",
        "",
        None,
    ],
)
def test_invalid_job_id_rejected(value):
    with pytest.raises(ValueError):
        validate_job_id(value)


def test_record_defaults_updated_at():
    record = _record()
    assert record.updated_at == record.created_at
    assert record.status is JobStatus.QUEUED


def test_status_sets_are_disjoint_and_complete():
    assert ACTIVE_STATUSES.isdisjoint(TERMINAL_STATUSES)
    assert set(JobStatus.__members__) == ACTIVE_STATUSES | TERMINAL_STATUSES
    assert "COMPLETED" in TERMINAL_STATUSES


@pytest.mark.parametrize("status", sorted(TERMINAL_STATUSES))
def test_terminal_status_flag(status):
    assert _record(status=JobStatus(status)).is_terminal is True
    assert _record(status=JobStatus(status)).is_active is False


@pytest.mark.parametrize("status", sorted(ACTIVE_STATUSES))
def test_active_status_flag(status):
    assert _record(status=JobStatus(status)).is_active is True
    assert _record(status=JobStatus(status)).is_terminal is False


def test_record_save_and_load_roundtrip(tmp_path):
    record = _record(planned_cases=3, session_id="abc", result_run_ids=["run_1"])
    record.save(tmp_path)
    loaded = JobRecord.load(tmp_path)
    assert loaded.job_id == record.job_id
    assert loaded.status is JobStatus.QUEUED
    assert loaded.planned_cases == 3
    assert loaded.session_id == "abc"
    assert loaded.result_run_ids == ["run_1"]


def test_save_is_atomic_and_writes_valid_json(tmp_path):
    record = _record()
    record.save(tmp_path)
    assert not (tmp_path / "job.json.tmp").exists()
    payload = json.loads((tmp_path / "job.json").read_text(encoding="utf-8"))
    assert payload["job_id"] == record.job_id
    assert payload["status"] == "QUEUED"


def test_from_dict_ignores_unknown_fields():
    payload = _record().to_dict()
    payload["future_field"] = 123
    loaded = JobRecord.from_dict(payload)
    assert loaded.job_id == VALID_ID
    assert not hasattr(loaded, "future_field")
