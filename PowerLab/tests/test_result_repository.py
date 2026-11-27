"""结果读取与抽样测试（第九阶段 Task 6）。"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from storage.result_repository import (
    discover_run_dirs,
    downsample_frame,
    load_config_snapshot,
    load_metadata,
    load_run_bundle,
    load_waveform,
    locate_run,
)


def _make_run(root: Path, name: str, metadata: dict) -> Path:
    directory = root / "basic_circuits" / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    frame = pd.DataFrame(
        {
            "time_s": [i * 1e-6 for i in range(300)],
            "vout": [10.0 if i == 150 else 1.0 for i in range(300)],
        }
    )
    frame.to_csv(directory / "waveform.csv", index=False)
    (directory / "circuit.cir").write_text("* netlist\nV1 in 0 5\n", encoding="utf-8")
    (directory / "summary.json").write_text('{"run_id": "x"}', encoding="utf-8")
    (directory / "config_snapshot.yaml").write_text("model: rc\n", encoding="utf-8")
    return directory


def test_discover_run_dirs(tmp_path):
    _make_run(tmp_path, "run_20261125_120000_aaaaaaaa", {"run_id": "20261125_120000_aaaaaaaa"})
    found = discover_run_dirs(tmp_path)
    assert set(found) == {"20261125_120000_aaaaaaaa"}


def test_discover_ignores_web_jobs(tmp_path):
    _make_run(
        tmp_path,
        "web_jobs/job_20261125_120000_12345678/run_ignored",
        {"run_id": "ignored"},
    )
    assert discover_run_dirs(tmp_path) == {}


def test_locate_and_metadata(tmp_path):
    directory = _make_run(
        tmp_path,
        "run_20261125_120000_aaaaaaaa",
        {"run_id": "20261125_120000_aaaaaaaa", "circuit_name": "rc_transient"},
    )
    assert locate_run("20261125_120000_aaaaaaaa", tmp_path) == directory
    assert locate_run("missing", tmp_path) is None
    assert load_metadata(directory)["circuit_name"] == "rc_transient"


def test_load_waveform_selected_columns(tmp_path):
    directory = _make_run(tmp_path, "run_a", {"run_id": "a"})
    frame = load_waveform(directory, columns=["time_s", "vout"])
    assert list(frame.columns) == ["time_s", "vout"]
    assert len(frame) == 300


def test_downsample_keeps_extreme_points(tmp_path):
    directory = _make_run(tmp_path, "run_a", {"run_id": "a"})
    frame = load_waveform(directory, max_points=100)
    assert len(frame) <= 100
    assert frame["vout"].max() == 10.0


def test_downsample_noop_for_small_frames():
    frame = pd.DataFrame({"time_s": [0.0, 1.0], "vout": [0.0, 5.0]})
    result = downsample_frame(frame, max_points=100)
    assert result is frame


def test_load_run_bundle_reads_assets(tmp_path):
    directory = _make_run(
        tmp_path,
        "run_a",
        {"run_id": "a", "environment": {"python": "3.11"}, "analysis_type": "transient"},
    )
    bundle = load_run_bundle("a", results_root=tmp_path, with_waveform=True, max_points=50)
    assert bundle is not None
    assert bundle.netlist is not None and "V1" in bundle.netlist
    assert bundle.summary == {"run_id": "x"}
    assert bundle.config_snapshot == {"model": "rc"}
    assert bundle.waveform is not None and len(bundle.waveform) <= 50
    assert bundle.data_source == "spice_simulation"


def test_bundle_data_source_for_derived_analysis(tmp_path):
    _make_run(tmp_path, "run_b", {"run_id": "b", "run_kind": "derived_analysis"})
    bundle = load_run_bundle("b", results_root=tmp_path)
    assert bundle is not None
    assert bundle.data_source == "spice_derived"


def test_bundle_data_source_unknown_without_evidence(tmp_path):
    _make_run(tmp_path, "run_c", {"run_id": "c"})
    bundle = load_run_bundle("c", results_root=tmp_path)
    assert bundle is not None
    assert bundle.data_source == "unknown"


def test_missing_bundle_returns_none(tmp_path):
    assert load_run_bundle("missing", results_root=tmp_path) is None
    assert load_config_snapshot(tmp_path) is None
