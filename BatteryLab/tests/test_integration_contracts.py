"""跨项目接口契约、哈希快照与测量包校验测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from integration.environment_adapter import SKIP_DIRECTORIES, compare_snapshots, hash_tree
from integration.measurement_exchange import (
    SystemMeasurement,
    build_bundle,
    measurement_from_dict,
)
from integration.interface_validator import validate_measurement_bundle, validate_schema_file
from integration.project_registry import PROJECT_ROOT, inspect_all, load_project_paths


def test_project_paths_are_declared_and_present() -> None:
    projects = load_project_paths()
    assert set(projects) == {"testlab", "powerlab", "batterylab"}
    for info in projects.values():
        assert Path(info["root"]).is_dir()


def test_inspect_all_reports_key_files() -> None:
    manifest = inspect_all()
    assert manifest["all_present"] is True
    assert manifest["manifest"] if "manifest" in manifest else True
    assert all(record["key_files"]["missing"] == [] for record in manifest["projects"].values())


def test_hash_tree_skips_results(tmp_path: Path) -> None:
    (tmp_path / "module.py").write_text("print('x')", encoding="utf-8")
    (tmp_path / "results").mkdir()
    (tmp_path / "results" / "run.json").write_text("{}", encoding="utf-8")
    digests = hash_tree(tmp_path)
    assert "module.py" in digests
    assert not any(key.startswith("results/") for key in digests)
    assert "results" in SKIP_DIRECTORIES


def test_compare_snapshots_detects_changes() -> None:
    before = {"a.py": "1", "b.py": "2"}
    after = {"a.py": "1", "b.py": "3", "c.py": "4"}
    result = compare_snapshots(before, after)
    assert result["unchanged"] is False
    assert result["changed"] == ["b.py"]
    assert result["added"] == ["c.py"]
    assert result["removed"] == []


def verified_bundle(tmp_path: Path):
    evidence = tmp_path / "waveform.csv"
    evidence.write_text("time\n0\n", encoding="utf-8")
    measurement = SystemMeasurement("vout", 5.0, "V", "spice_coupled_simulation",
                                   "run1", str(evidence), "VERIFIED")
    return build_bundle(run_id="run1", source="spice_coupled_simulation", measurements=[measurement])


def test_valid_bundle_passes(tmp_path: Path) -> None:
    bundle = verified_bundle(tmp_path)
    report = validate_measurement_bundle(bundle, evidence_root=tmp_path)
    assert report["status"] == "PASS", report["issues"]


def test_bundle_missing_evidence_fails(tmp_path: Path) -> None:
    bundle = verified_bundle(tmp_path)
    bundle["measurements"][0]["evidence_path"] = "missing.csv"
    report = validate_measurement_bundle(bundle, evidence_root=tmp_path)
    assert report["status"] == "FAIL"
    assert any(item["reason"] == "EVIDENCE_NOT_FOUND" for item in report["issues"])


def test_verified_without_evidence_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        SystemMeasurement("vout", 5.0, "V", "spice_coupled_simulation", None, None, "VERIFIED")


def test_invalid_status_rejected() -> None:
    with pytest.raises(ValueError):
        SystemMeasurement("vout", 5.0, "V", "spice_coupled_simulation", "run", "p", "GREAT")


def test_measurement_roundtrip() -> None:
    measurement = SystemMeasurement("vout", 5.0, "V", "spice_coupled_simulation", "run", "p", "VERIFIED")
    restored = measurement_from_dict(measurement.to_dict())
    assert restored == measurement


def test_schema_files_are_draft07() -> None:
    for name in ("system_measurements_v1.schema.json", "system_test_result_v1.schema.json"):
        report = validate_schema_file(PROJECT_ROOT / "schemas" / name)
        assert report["status"] == "OK"
