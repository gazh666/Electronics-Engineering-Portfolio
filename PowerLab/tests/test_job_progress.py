"""任务进度记录测试（第九阶段 Task 12）。"""

from __future__ import annotations

import json

from jobs.progress import ProgressTracker, read_progress


def test_progress_without_plan_has_no_fraction(tmp_path):
    tracker = ProgressTracker(job_dir=tmp_path)
    assert tracker.to_dict()["fraction"] is None


def test_progress_after_start_reports_zero(tmp_path):
    tracker = ProgressTracker(job_dir=tmp_path)
    tracker.start(planned_cases=2)
    payload = tracker.to_dict()
    assert payload["phase"] == "running"
    assert payload["fraction"] == 0.0


def test_progress_counts_completed_cases(tmp_path):
    tracker = ProgressTracker(job_dir=tmp_path)
    tracker.start(planned_cases=2)
    tracker.finish_case(success=True)
    assert tracker.completed_cases == 1
    assert tracker.to_dict()["fraction"] == 0.5


def test_progress_counts_failed_cases(tmp_path):
    tracker = ProgressTracker(job_dir=tmp_path)
    tracker.start(planned_cases=4)
    tracker.finish_case(success=False)
    payload = tracker.to_dict()
    assert payload["failed_cases"] == 1
    assert payload["fraction"] == 0.25


def test_progress_counts_spice_runs_and_cache_hits(tmp_path):
    tracker = ProgressTracker(job_dir=tmp_path)
    tracker.start(planned_cases=1)
    tracker.finish_case(success=True, spice_runs=3)
    tracker.record_cache_hit()
    payload = tracker.to_dict()
    assert payload["spice_runs"] == 3
    assert payload["cache_hits"] == 1


def test_progress_flush_is_readable_and_atomic(tmp_path):
    tracker = ProgressTracker(job_dir=tmp_path)
    tracker.start(planned_cases=1)
    tracker.finish("done")
    assert not (tmp_path / "progress.json.tmp").exists()
    payload = read_progress(tmp_path)
    assert payload is not None
    assert payload["phase"] == "finished"
    assert payload["message"] == "done"


def test_read_progress_missing_file(tmp_path):
    assert read_progress(tmp_path) is None


def test_read_progress_ignores_broken_json(tmp_path):
    (tmp_path / "progress.json").write_text("{not json", encoding="utf-8")
    assert read_progress(tmp_path) is None


def test_current_case_cleared_after_finish(tmp_path):
    tracker = ProgressTracker(job_dir=tmp_path)
    tracker.begin_case("run A")
    assert json.loads((tmp_path / "progress.json").read_text(encoding="utf-8"))[
        "current_case"
    ] == "run A"
    tracker.finish_case(success=True)
    assert tracker.current_case is None
