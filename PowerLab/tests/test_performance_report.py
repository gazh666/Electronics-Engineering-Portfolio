"""HTML 报告渲染测试（使用临时目录充当 results 根）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from reports.performance_report import (
    render_performance_report,
    snippet,
    write_performance_report,
)


def _write_run(directory: Path) -> Path:
    directory.mkdir(parents=True)
    payload = {
        "run_id": "run_test",
        "circuit_name": "nonideal_buck",
        "variant": "E",
        "data_source": "spice_simulation",
        "overall_status": "PASS",
        "steady_state": {"status": "STEADY_STATE", "complete_cycles": 20},
        "groups": {
            "voltage": {
                "label": "voltage",
                "metrics": {
                    "output_voltage_mean_v": {
                        "name": "output_voltage_mean_v",
                        "value": 4.668,
                        "unit": "V",
                        "status": "AVAILABLE",
                        "data_source": "spice_derived",
                        "method": "integration",
                        "message": "<script>alert(1)</script>",
                    }
                },
            }
        },
        "checks": [
            {
                "metric_name": "output_voltage_ripple_vpp",
                "actual_value": 0.019,
                "minimum_value": None,
                "maximum_value": 0.05,
                "status": "PASS",
                "reason": "within_limits",
            }
        ],
        "quality": {"passed": True, "issues": []},
        "notes": ["note <b>one</b>"],
        "spectrum": {"frequency_resolution_hz": 295.5, "window_name": "hann"},
    }
    (directory / "performance_metrics.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    (directory / "metadata.json").write_text(
        json.dumps({"created_at": "2026-11-25T00:00:00"}), encoding="utf-8"
    )
    (directory / "quality.json").write_text(
        json.dumps({"passed": True, "error_count": 0, "warning_count": 0, "issues": []}),
        encoding="utf-8",
    )
    (directory / "summary.json").write_text(
        json.dumps({"overall_status": "PASS", "total": 1}), encoding="utf-8"
    )
    (directory / "harmonics.csv").write_text(
        "order,expected_frequency_hz,detected_frequency_hz,amplitude_peak,status,note\n"
        "1,100000,100000,0.02,AVAILABLE,\n",
        encoding="utf-8",
    )
    return directory


def test_snippet_escapes_and_truncates():
    assert snippet("<tag>") == "&lt;tag&gt;"
    long_text = "x" * 200
    assert len(snippet(long_text)) == 120
    assert snippet(long_text).endswith("...")


def test_render_performance_report_contains_sections(tmp_path: Path):
    run_dir = _write_run(tmp_path / "run_test")
    html = render_performance_report(run_dir, allowed_root=tmp_path)
    assert "Buck Converter Performance Report" in html
    assert "run_test" in html
    assert "output_voltage_mean_v" in html
    assert "Limit Checks" in html
    assert "Data Quality" in html
    assert "Harmonics" in html
    assert "hann" in html


def test_render_escapes_untrusted_text(tmp_path: Path):
    run_dir = _write_run(tmp_path / "run_test")
    html = render_performance_report(run_dir, allowed_root=tmp_path)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<b>one</b>" not in html


def test_render_rejects_directories_outside_allowed_root(tmp_path: Path):
    run_dir = _write_run(tmp_path / "outside" / "run_test")
    with pytest.raises(ValueError):
        render_performance_report(run_dir, allowed_root=tmp_path / "outside" / "root")


def test_render_requires_metrics_file(tmp_path: Path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ValueError):
        render_performance_report(empty, allowed_root=tmp_path)
    with pytest.raises(ValueError):
        render_performance_report(tmp_path / "missing", allowed_root=tmp_path)


def test_write_performance_report_creates_html(tmp_path: Path):
    run_dir = _write_run(tmp_path / "run_test")
    output = write_performance_report(run_dir, allowed_root=tmp_path)
    assert output == run_dir / "performance_report.html"
    assert output.stat().st_size > 0
    assert "Performance Report" in output.read_text(encoding="utf-8")
