"""运行索引测试（第九阶段 Task 6）。"""

from __future__ import annotations

import json
from pathlib import Path

from storage.run_index import (
    INDEX_SCHEMA_VERSION,
    build_index,
    get_index,
    index_path,
    load_index,
    save_index,
)


def _write_run(
    root: Path,
    name: str,
    metadata: dict,
    *,
    web_run: dict | None = None,
    waveform: bool = True,
) -> Path:
    directory = root / "stage_x" / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "metadata.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )
    if waveform:
        (directory / "waveform.csv").write_text("time_s,vout\n0,0\n", encoding="utf-8")
    if web_run is not None:
        (directory / "web_run.json").write_text(json.dumps(web_run), encoding="utf-8")
    return directory


def _sample_root(tmp_path: Path) -> Path:
    _write_run(
        tmp_path,
        "run_20261125_120000_aaaaaaaa",
        {
            "run_id": "20261125_120000_aaaaaaaa",
            "analysis_type": "transient",
            "circuit_name": "nonideal_buck",
            "status": "success",
            "environment": {"python": "3.11.18"},
            "point_count": 500,
            "duration_ms": 12.5,
            "created_at": "2026-11-25T12:00:00",
        },
    )
    _write_run(
        tmp_path,
        "run_20261125_120100_bbbbbbbb",
        {
            "run_id": "20261125_120100_bbbbbbbb",
            "run_kind": "derived_analysis",
            "analysis_type": "sweep",
            "circuit_name": "parameter_sweep",
            "status": "success",
            "created_at": "2026-11-25T12:01:00",
        },
        waveform=False,
    )
    _write_run(
        tmp_path,
        "run_20261125_120200_cccccccc",
        {
            "run_id": "20261125_120200_cccccccc",
            "analysis_type": "transient",
            "status": "success",
            "environment": {"python": "3.11.18"},
            "created_at": "2026-11-25T12:02:00",
        },
        web_run={"model": "nonideal_buck", "job_id": "job_20261125_120200_12345678"},
    )
    # 任务目录不进入运行索引
    _write_run(
        tmp_path,
        "web_jobs/job_20261125_120300_12345678/run_ignored",
        {"run_id": "ignored", "status": "success"},
    )
    return tmp_path


def test_build_index_discovers_runs(tmp_path):
    index = build_index(_sample_root(tmp_path))
    assert len(index.entries) == 3


def test_index_ignores_job_directories(tmp_path):
    index = build_index(_sample_root(tmp_path))
    assert index.get("ignored") is None


def test_index_maps_simulation_metadata(tmp_path):
    draft = build_index(_sample_root(tmp_path))
    entry = draft.get("20261125_120000_aaaaaaaa")
    assert entry is not None
    assert entry.run_kind == "simulation"
    assert entry.data_source == "spice_simulation"
    assert entry.point_count == 500
    assert entry.has_waveform is True


def test_index_marks_derived_analysis(tmp_path):
    index = build_index(_sample_root(tmp_path))
    entry = index.get("20261125_120100_bbbbbbbb")
    assert entry.run_kind == "derived_analysis"
    assert entry.data_source == "spice_derived"
    assert entry.has_waveform is False


def test_index_reads_web_run_metadata(tmp_path):
    index = build_index(_sample_root(tmp_path))
    entry = index.get("20261125_120200_cccccccc")
    assert entry.model == "nonideal_buck"
    assert entry.job_id == "job_20261125_120200_12345678"


def test_index_stats(tmp_path):
    stats = build_index(_sample_root(tmp_path)).stats()
    assert stats["total"] == 3
    assert stats["by_kind"]["simulation"] == 2
    assert stats["by_kind"]["derived_analysis"] == 1
    assert stats["by_data_source"]["spice_simulation"] == 2


def test_index_filtered_by_kind_and_search(tmp_path):
    index = build_index(_sample_root(tmp_path))
    assert len(index.filtered(run_kind="derived_analysis")) == 1
    assert len(index.filtered(search="nonideal")) == 2
    assert len(index.filtered(search="no-such-run")) == 0


def test_index_pagination(tmp_path):
    index = build_index(_sample_root(tmp_path))
    entries = index.filtered()
    assert len(index.page(entries, 1, 2)) == 2
    assert len(index.page(entries, 2, 2)) == 1
    assert len(index.page(entries, 0, 2)) == 2


def test_save_and_load_roundtrip(tmp_path):
    root = _sample_root(tmp_path)
    index = build_index(root)
    target = save_index(index, root)
    assert target == index_path(root)
    loaded = load_index(root)
    assert loaded is not None
    assert len(loaded.entries) == 3
    assert loaded.built_at == index.built_at


def test_load_rejects_other_schema(tmp_path):
    root = _sample_root(tmp_path)
    payload = {
        "schema_version": "0.9",
        "built_at": "x",
        "entries": [],
    }
    (root / "run_index.json").write_text(json.dumps(payload), encoding="utf-8")
    assert load_index(root) is None


def test_get_index_rebuilds_and_caches(tmp_path):
    root = _sample_root(tmp_path)
    first = get_index(root)
    assert index_path(root).is_file()
    assert first.schema_version == INDEX_SCHEMA_VERSION
    second = get_index(root)
    assert len(second.entries) == len(first.entries)
