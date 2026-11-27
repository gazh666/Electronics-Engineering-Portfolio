"""导出服务测试（第九阶段 Task 6）。"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pandas as pd
import pytest

from jobs.models import JobRecord, JobStatus
from ui import export_service


def _install_bundle(monkeypatch, *, performance=None, summary=None, run_dir=None):
    bundle = SimpleNamespace(
        run_dir=run_dir,
        performance=performance,
        summary=summary,
        metadata={},
    )
    monkeypatch.setattr(
        export_service, "load_run_bundle", lambda run_id, with_waveform=False: bundle
    )
    return bundle


def test_csv_bytes_has_utf8_bom():
    payload = export_service._csv_bytes(pd.DataFrame({"a": [1]}))
    assert payload.startswith(b"\xef\xbb\xbf")
    assert "a" in payload.decode("utf-8-sig")


def test_waveform_csv_uses_original_file(monkeypatch, tmp_path):
    _install_bundle(monkeypatch, run_dir=tmp_path)
    monkeypatch.setattr(
        export_service,
        "load_waveform",
        lambda directory: pd.DataFrame({"time_s": [0.0, 1e-3], "vout": [0.0, 5.0]}),
    )
    name, mime, data = export_service.waveform_csv("20261125_120000_aaaaaaaa")
    assert name == "run_20261125_120000_aaaaaaaa_waveform.csv"
    assert mime == "text/csv"
    assert "vout" in data.decode("utf-8-sig")


def test_waveform_csv_missing_waveform(monkeypatch, tmp_path):
    _install_bundle(monkeypatch, run_dir=tmp_path)
    monkeypatch.setattr(export_service, "load_waveform", lambda directory: None)
    with pytest.raises(FileNotFoundError):
        export_service.waveform_csv("run")


def test_metrics_csv_exports_metric_rows(monkeypatch):
    _install_bundle(
        monkeypatch,
        performance={
            "metrics": {
                "output_voltage_mean_v": {
                    "value": 5.0,
                    "unit": "V",
                    "status": "PASS",
                    "data_source": "spice_simulation",
                }
            }
        },
    )
    name, _, data = export_service.metrics_csv("run1")
    text = data.decode("utf-8-sig")
    assert name == "run_run1_metrics.csv"
    assert "output_voltage_mean_v" in text
    assert "spice_simulation" in text


def test_metrics_csv_requires_metrics(monkeypatch):
    _install_bundle(monkeypatch, performance=None)
    with pytest.raises(FileNotFoundError):
        export_service.metrics_csv("run1")


def test_checks_csv_exports_rows(monkeypatch):
    _install_bundle(
        monkeypatch,
        performance={"checks": [{"name": "output_voltage", "status": "PASS"}]},
    )
    _, _, data = export_service.checks_csv("run1")
    assert "output_voltage" in data.decode("utf-8-sig")


def test_summary_json_roundtrip(monkeypatch):
    _install_bundle(monkeypatch, summary={"run_id": "run1", "point_count": 10})
    name, mime, data = export_service.summary_json("run1")
    assert name == "run_run1_summary.json"
    assert mime == "application/json"
    assert '"point_count": 10' in data.decode("utf-8")


def test_summary_json_requires_summary(monkeypatch):
    _install_bundle(monkeypatch, summary=None)
    with pytest.raises(FileNotFoundError):
        export_service.summary_json("run1")


def test_table_csv_name():
    name, mime, data = export_service.table_csv("sweep", pd.DataFrame({"x": [1, 2]}))
    assert name == "sweep.csv"
    assert mime == "text/csv"
    assert "x" in data.decode("utf-8-sig")


def test_html_report_contains_real_metadata(monkeypatch, tmp_path):
    (tmp_path / "web_run.json").write_text(
        json.dumps({"job_id": "job_20261125_120000_deadbeef", "model": "nonideal_buck"}),
        encoding="utf-8",
    )
    bundle = SimpleNamespace(
        run_id="abc",
        run_dir=tmp_path,
        metadata={"run_id": "abc", "point_count": 100, "created_at": "2026-11-25T12:00:00"},
        analysis_type="transient",
        run_kind="simulation",
        data_source="spice_simulation",
        performance={
            "metrics": {
                "output_voltage_mean_v": {
                    "value": 5.0,
                    "unit": "V",
                    "status": "PASS",
                    "data_source": "spice_simulation",
                }
            },
            "checks": [{"name": "output_voltage", "status": "PASS"}],
        },
        summary={"run_id": "abc"},
    )
    monkeypatch.setattr(
        export_service, "load_run_bundle", lambda run_id, with_waveform=False: bundle
    )
    name, mime, data = export_service.html_report("abc")
    text = data.decode("utf-8")
    assert name == "run_abc_report.html"
    assert mime == "text/html"
    assert "job_20261125_120000_deadbeef" in text
    assert "output_voltage_mean_v" in text
    assert "不是硬件实测" in text


def test_html_report_requires_existing_run(monkeypatch):
    monkeypatch.setattr(
        export_service, "load_run_bundle", lambda run_id, with_waveform=False: None
    )
    with pytest.raises(FileNotFoundError):
        export_service.html_report("missing")


def test_job_report_marks_simulation_only():
    record = JobRecord(
        job_id="job_20261125_120000_deadbeef",
        job_type="circuit_simulation",
        status=JobStatus.COMPLETED,
        created_at="2026-11-25T12:00:00",
        finished_at="2026-11-25T12:00:05",
    )
    name, mime, data = export_service.job_report_markdown(
        record,
        {
            "planned_cases": 1,
            "completed_cases": 1,
            "failed_cases": 0,
            "spice_runs": 1,
            "result_run_ids": ["20261125_120000_aaaaaaaa"],
        },
    )
    text = data.decode("utf-8")
    assert name.endswith("_report.md")
    assert mime == "text/markdown"
    assert "simulation" in text
    assert "不是硬件实测" in text
    assert record.job_id in text


def test_job_report_includes_error_section():
    record = JobRecord(
        job_id="job_20261125_120000_deadbeef",
        job_type="circuit_simulation",
        status=JobStatus.FAILED,
        created_at="2026-11-25T12:00:00",
        error_message="RuntimeError: solver failed",
    )
    _, _, data = export_service.job_report_markdown(record, {})
    text = data.decode("utf-8")
    assert "## 错误" in text
    assert "solver failed" in text
