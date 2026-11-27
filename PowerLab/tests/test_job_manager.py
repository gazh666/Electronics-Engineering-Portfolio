"""任务管理器测试（第九阶段 Task 9、13、14）。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from jobs.manager import JobManager
from jobs.models import (
    ConcurrencyLimitError,
    DuplicateJobError,
    InvalidJobRequest,
    JobRecord,
    JobStatus,
)
from jobs.registry import MODEL_SPECS
from jobs.resource_budget import JobLimits

DEAD_PID = 2_000_000_000


def _limits(**overrides) -> JobLimits:
    payload = {
        "maximum_concurrent_jobs": 1,
        "maximum_single_job_seconds": 3600,
        "maximum_case_seconds": 300,
        "maximum_unique_spice_runs": 120,
        "maximum_monte_carlo_samples": 30,
        "maximum_plot_points": 30000,
        "minimum_free_disk_space_mb": 0,
        "maximum_log_bytes": 2_000_000,
        "profiles": {"standard": {"maximum_unique_spice_runs": 120}},
    }
    payload.update(overrides)
    return JobLimits(**payload)


def _request(model: str = "voltage_divider", **overrides) -> dict:
    payload = {field.name: field.default for field in MODEL_SPECS[model].fields}
    payload["model"] = model
    payload.update(overrides)
    return payload


@pytest.fixture
def manager(tmp_path, monkeypatch) -> JobManager:
    instance = JobManager(root=tmp_path / "jobs", limits=_limits(), max_concurrency=1)
    monkeypatch.setattr(
        instance, "_spawn", lambda directory, job_id: SimpleNamespace(pid=DEAD_PID)
    )
    return instance


def _place(
    manager: JobManager,
    *,
    status: JobStatus,
    job_id: str,
    created_at: str | None = None,
    started_at: str | None = None,
    worker_pid: int | None = None,
) -> JobRecord:
    record = JobRecord(
        job_id=job_id,
        job_type="circuit_simulation",
        status=status,
        created_at=created_at or datetime.now().isoformat(timespec="seconds"),
        started_at=started_at,
        worker_pid=worker_pid,
    )
    record.save(manager.job_dir(job_id))
    return record


def test_submit_persists_validated_request(manager):
    record = manager.submit(
        "circuit_simulation", _request("nonideal_buck"), session_id="sess"
    )
    assert record.status is JobStatus.QUEUED
    assert record.session_id == "sess"
    assert record.worker_pid == DEAD_PID
    directory = manager.job_dir(record.job_id)
    assert (directory / "job.json").is_file()
    request = json.loads((directory / "request.json").read_text(encoding="utf-8"))
    assert request["end_time_s"] == pytest.approx(5e-3)
    assert request["inductance_h"] == pytest.approx(47e-6)


def test_duplicate_active_request_rejected(manager):
    first = manager.submit("circuit_simulation", _request())
    with pytest.raises(DuplicateJobError) as info:
        manager.submit("circuit_simulation", _request())
    assert info.value.existing_job_id == first.job_id


def test_concurrency_limit_rejects_second_job(manager):
    manager.submit("circuit_simulation", _request())
    with pytest.raises(ConcurrencyLimitError):
        manager.submit("circuit_simulation", _request(vin_v=10.0))


def test_invalid_request_rejected_before_spawn(manager):
    with pytest.raises(InvalidJobRequest):
        manager.submit("circuit_simulation", {"model": "voltage_divider", "vin_v": 12.0})
    assert manager.list_jobs() == []


def test_unknown_job_type_rejected(manager):
    with pytest.raises(InvalidJobRequest):
        manager.submit("shell", {})


def test_list_jobs_newest_first(manager):
    older = _place(
        manager,
        status=JobStatus.COMPLETED,
        job_id="job_20261125_100000_aaaaaaaa",
        created_at="2026-11-25T10:00:00",
    )
    newer = _place(
        manager,
        status=JobStatus.COMPLETED,
        job_id="job_20261125_110000_bbbbbbbb",
        created_at="2026-11-25T11:00:00",
    )
    listed = manager.list_jobs()
    assert [item.job_id for item in listed] == [newer.job_id, older.job_id]
    assert manager.active_jobs() == []


def test_get_job_includes_progress(manager):
    record = manager.submit("circuit_simulation", _request())
    progress = {
        "planned_cases": 1,
        "completed_cases": 0,
        "phase": "running",
        "current_case": "voltage divider OP",
        "fraction": 0.0,
    }
    (manager.job_dir(record.job_id) / "progress.json").write_text(
        json.dumps(progress), encoding="utf-8"
    )
    loaded = manager.get_job(record.job_id)
    assert loaded.progress["current_case"] == "voltage divider OP"
    assert loaded.current_operation == "voltage divider OP"


def test_running_job_over_time_budget_times_out(manager):
    started = (datetime.now() - timedelta(hours=2)).isoformat(timespec="seconds")
    job_id = "job_20261125_080000_cccccccc"
    _place(manager, status=JobStatus.RUNNING, job_id=job_id, started_at=started)
    record = manager.get_job(job_id)
    assert record.status is JobStatus.TIMED_OUT
    assert "budget" in (record.error_message or "")


def test_running_job_with_dead_worker_is_interrupted(manager):
    job_id = "job_20261125_090000_dddddddd"
    _place(
        manager,
        status=JobStatus.RUNNING,
        job_id=job_id,
        started_at=datetime.now().isoformat(timespec="seconds"),
        worker_pid=DEAD_PID,
    )
    record = manager.get_job(job_id)
    assert record.status is JobStatus.INTERRUPTED


def test_queued_job_with_dead_worker_is_interrupted(manager):
    created = (datetime.now() - timedelta(seconds=10)).isoformat(timespec="seconds")
    job_id = "job_20261125_090500_eeeeeeee"
    _place(
        manager,
        status=JobStatus.QUEUED,
        job_id=job_id,
        created_at=created,
        worker_pid=DEAD_PID,
    )
    record = manager.get_job(job_id)
    assert record.status is JobStatus.INTERRUPTED
    assert "before entering RUNNING" in (record.error_message or "")


def test_cancel_queued_job_writes_flag(manager):
    job_id = "job_20261125_091000_ffffffff"
    _place(manager, status=JobStatus.QUEUED, job_id=job_id)
    record = manager.request_cancel(job_id)
    assert record.status is JobStatus.CANCEL_REQUESTED
    assert (manager.job_dir(job_id) / "cancel.flag").is_file()


def test_cancel_terminal_job_is_noop(manager):
    job_id = "job_20261125_092000_11111111"
    _place(manager, status=JobStatus.COMPLETED, job_id=job_id)
    record = manager.request_cancel(job_id)
    assert record.status is JobStatus.COMPLETED
    assert not (manager.job_dir(job_id) / "cancel.flag").exists()


def test_force_stop_aliases_cancel(manager):
    job_id = "job_20261125_093000_22222222"
    _place(manager, status=JobStatus.QUEUED, job_id=job_id)
    assert manager.force_stop(job_id).status is JobStatus.CANCEL_REQUESTED


def test_wait_for_terminal_job_returns_immediately(manager):
    job_id = "job_20261125_094000_33333333"
    _place(manager, status=JobStatus.FAILED, job_id=job_id)
    record = manager.wait_for(job_id, timeout_s=0.1, interval_s=0.01)
    assert record.status is JobStatus.FAILED
