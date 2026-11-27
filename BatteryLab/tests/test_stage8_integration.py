import json
from pathlib import Path

from eda_tools import board_metrics, report_parser, release_manifest
from scripts.battery_stage8_demo import BMS_MAP, CHG_MAP
from scripts.generate_hardware_bom import BMS_BOM, CHARGER_BOM, build_rows, summarize
from scripts.hardware_design_calculation import compute_design

ROOT = Path(__file__).resolve().parents[1]


def test_real_mapping_files_are_complete():
    from eda_tools.pin_mapping_audit import audit_mapping_completeness

    bms = audit_mapping_completeness(ROOT / BMS_MAP, 32)
    charger = audit_mapping_completeness(ROOT / CHG_MAP, 24)

    assert bms["complete"] is True
    assert charger["complete"] is True
    assert bms["non_numeric_rows"] == ["PAD"]
    assert charger["non_numeric_rows"] == ["PAD"]


def test_design_calculation_uses_real_datasheet_values():
    import pytest

    design = compute_design()
    summary = design["summary"]

    assert summary["shunt_selected_ohm"] == 0.01
    assert summary["shunt_power_at_2p5a_w"] == pytest.approx(0.0625)
    assert summary["charge_voltage_actual_v"] == pytest.approx(12.075)
    assert summary["charge_voltage_actual_v"] / 3.0 < 4.25
    assert summary["charge_current_actual_a"] == pytest.approx(1.0060975609756098)
    assert summary["balancing_worst_external_power_w"] > 0.2
    assert 11.0 < summary["lc_resonance_khz"] < 11.2


def test_balancing_resistor_power_is_a_real_finding():
    design = compute_design()
    cases = design["balancing"]["cases"]
    worst = max(case["resistor_power_w"] for case in cases)
    assert worst > 0.2  # 47 Ω 在最小内部电阻下超过 0.25 W 的 80%
    assert design["balancing"]["finding"]


def test_design_sources_are_datasheets():
    design = compute_design()
    for value in design["sources"].values():
        assert value


def test_bom_projects_have_no_validation_issues():
    rows = build_rows("BatteryLab_BMS_V1", BMS_BOM) + build_rows("BatteryLab_Charger_V1", CHARGER_BOM)
    from eda_tools.bom_validator import validate_bom_rows

    assert validate_bom_rows(rows) == []
    assert summarize([r for r in rows if r["project"] == "BatteryLab_BMS_V1"])["critical_tbd"] == 0
    assert summarize([r for r in rows if r["project"] == "BatteryLab_Charger_V1"])["critical_tbd"] == 0


def test_pcbnew_is_not_available_without_kicad():
    assert board_metrics.pcbnew_available() in {True, False}


def test_report_parser_missing_report(tmp_path):
    result = report_parser.summarize_report(tmp_path / "missing.json")
    assert result["status"] == "ERROR"
    assert result["reason"] == "REPORT_MISSING"


def test_report_parser_unrecognized_structure(tmp_path):
    path = tmp_path / "weird.json"
    path.write_text(json.dumps({"foo": "bar"}), encoding="utf-8")
    result = report_parser.summarize_report(path)
    assert result["status"] == "NOT_VERIFIED"
    assert result["reason"] == "UNRECOGNIZED_STRUCTURE"


def test_report_parser_counts_violations(tmp_path):
    path = tmp_path / "drc.json"
    path.write_text(
        json.dumps({
            "violations": [
                {"severity": "error", "type": "clearance"},
                {"severity": "warning", "type": "silk"},
                {"severity": "excluded", "type": "courtyard"},
            ],
            "unconnected_items": [{"x": 1}],
        }),
        encoding="utf-8",
    )
    result = report_parser.summarize_report(path)
    assert result["status"] == "PARSED"
    assert result["severities"]["error"] == 1
    assert result["severities"]["warning"] == 1
    assert result["severities"]["excluded"] == 1
    assert result["unconnected_count"] == 1


def test_release_manifest_hashes_files(tmp_path):
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "a.txt").write_text("hello", encoding="utf-8")
    (artifact_dir / "sub").mkdir()
    (artifact_dir / "sub" / "b.txt").write_text("world", encoding="utf-8")

    manifest = release_manifest.create_release_manifest(
        artifact_dir, artifact_dir / "release_manifest.json"
    )

    assert manifest["hardware_validated"] is False
    assert manifest["production_released"] is False
    assert manifest["file_count"] == 2
    assert all(len(record["sha256"]) == 64 for record in manifest["files"])


def test_release_manifest_requires_artifacts(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    import pytest

    with pytest.raises(ValueError):
        release_manifest.create_release_manifest(empty, empty / "manifest.json")
