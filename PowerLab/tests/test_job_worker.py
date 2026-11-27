"""工作进程执行测试（第九阶段 Task 10）。"""

from __future__ import annotations

import io
import json
import os

import pytest

from jobs import worker
from jobs.handlers import JobContext
from jobs.models import JobCancelled, JobRecord, JobStatus, utc_now
from jobs.progress import ProgressTracker

JOB_ID = "job_20261125_120000_abcdef12"


def _prepare(tmp_path) -> tuple:
    job_dir = tmp_path / JOB_ID
    record = JobRecord(
        job_id=JOB_ID,
        job_type="circuit_simulation",
        status=JobStatus.QUEUED,
        created_at=utc_now(),
    )
    record.save(job_dir)
    (job_dir / "request.json").write_text(
        json.dumps({"model": "voltage_divider"}), encoding="utf-8"
    )
    return job_dir, record


def _use_handler(monkeypatch, handler) -> None:
    monkeypatch.setattr(worker, "resolve_handler", lambda job_type: handler)


def test_worker_completes_and_records_runs(tmp_path, monkeypatch):
    job_dir, _ = _prepare(tmp_path)

    def handler(context, request):
        context.log("fake handler running")
        context.progress.start(planned_cases=1)
        context.progress.finish_case(success=True)
        context.progress.finish("ok")
        return ["run_fake"]

    _use_handler(monkeypatch, handler)
    assert worker.run_job(job_dir) == 0
    record = JobRecord.load(job_dir)
    assert record.status is JobStatus.COMPLETED
    assert record.result_run_ids == ["run_fake"]
    assert record.exit_code == 0
    assert record.worker_pid == os.getpid()
    assert record.solver_calls == 1


def test_worker_writes_log(tmp_path, monkeypatch):
    job_dir, _ = _prepare(tmp_path)
    _use_handler(monkeypatch, lambda context, request: ["run_fake"])
    worker.run_job(job_dir)
    log = (job_dir / "log.txt").read_text(encoding="utf-8")
    assert "worker started" in log
    assert "job_type=circuit_simulation" in log


def test_worker_marks_failure_with_real_exception(tmp_path, monkeypatch):
    job_dir, _ = _prepare(tmp_path)

    def handler(context, request):
        raise ValueError("boom")

    _use_handler(monkeypatch, handler)
    assert worker.run_job(job_dir) == 1
    record = JobRecord.load(job_dir)
    assert record.status is JobStatus.FAILED
    assert "ValueError: boom" in (record.error_message or "")
    log = (job_dir / "log.txt").read_text(encoding="utf-8")
    assert "Traceback" in log
    assert "boom" in log


def test_worker_records_cancellation(tmp_path, monkeypatch):
    job_dir, _ = _prepare(tmp_path)

    def handler(context, request):
        raise JobCancelled("stop here")

    _use_handler(monkeypatch, handler)
    assert worker.run_job(job_dir) == 1
    record = JobRecord.load(job_dir)
    assert record.status is JobStatus.CANCELLED
    assert record.exit_code == 1


def test_worker_syncs_progress_counters(tmp_path, monkeypatch):
    job_dir, _ = _prepare(tmp_path)

    def handler(context, request):
        context.progress.start(planned_cases=2)
        context.progress.finish_case(success=True)
        context.progress.finish_case(success=False)
        return []

    _use_handler(monkeypatch, handler)
    worker.run_job(job_dir)
    record = JobRecord.load(job_dir)
    assert record.planned_cases == 2
    assert record.completed_cases == 1
    assert record.failed_cases == 1
    assert record.solver_calls == 2


def test_worker_main_rejects_invalid_job_id():
    with pytest.raises(ValueError):
        worker.main(["--job-id", "job_bad"])


def test_context_truncates_oversized_log(tmp_path):
    record = JobRecord(
        job_id=JOB_ID,
        job_type="circuit_simulation",
        status=JobStatus.RUNNING,
        created_at=utc_now(),
    )
    handle = io.StringIO()
    context = JobContext(
        record=record,
        job_dir=tmp_path,
        progress=ProgressTracker(job_dir=tmp_path),
        log_handle=handle,
        cancel_requested=lambda: False,
        max_log_bytes=100,
    )
    for _ in range(50):
        context.log("x" * 50)
    text = handle.getvalue()
    assert "log truncated" in text
    assert len(text.encode("utf-8")) < 1000
