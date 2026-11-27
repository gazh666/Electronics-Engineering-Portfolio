from eda_tools.bom_validator import (
    cross_check_bom_with_netlist,
    load_bom_csv,
    validate_bom_rows,
)
from scripts.generate_hardware_bom import BMS_BOM, CHARGER_BOM, build_rows


def test_valid_critical_rows():
    rows = build_rows("BatteryLab_BMS_V1", BMS_BOM)
    issues = validate_bom_rows(rows)
    assert issues == []


def test_charger_critical_rows():
    rows = build_rows("BatteryLab_Charger_V1", CHARGER_BOM)
    assert validate_bom_rows(rows) == []


def test_missing_reference():
    issues = validate_bom_rows([{"reference": "", "footprint": "X"}])
    assert issues[0]["reason"] == "MISSING_REFERENCE"


def test_duplicate_reference():
    issues = validate_bom_rows([
        {"reference": "R1", "footprint": "X"},
        {"reference": "R1", "footprint": "X"},
    ])
    assert any(issue["reason"] == "DUPLICATE_REFERENCE" for issue in issues)


def test_unexpanded_reference_group():
    issues = validate_bom_rows([{"reference": "R1, R2", "footprint": "X"}])
    assert issues[0]["reason"] == "REFERENCE_NOT_EXPANDED"


def test_missing_footprint():
    issues = validate_bom_rows([{"reference": "R1", "footprint": ""}])
    assert any(issue["reason"] == "MISSING_FOOTPRINT" for issue in issues)


def test_critical_missing_mpn_and_datasheet():
    issues = validate_bom_rows([
        {"reference": "U1", "footprint": "QFN", "critical": "true", "manufacturer": "TI",
         "mpn": "TBD", "datasheet_url": ""},
    ])
    reasons = {issue["reason"] for issue in issues}
    assert "MISSING_MPN" in reasons
    assert "MISSING_DATASHEET_URL" in reasons


def test_dnp_rows_skip_checks():
    issues = validate_bom_rows([{"reference": "R1", "dnp": "true", "footprint": ""}])
    assert issues == []


def test_cross_check_bom_with_netlist():
    bom = [{"reference": "U1"}, {"reference": "R1"}]
    netlist = {"components": {"U1": {}, "R1": {}, "C1": {}}}
    result = cross_check_bom_with_netlist(bom, netlist)
    assert result["in_netlist_not_in_bom"] == ["C1"]
    assert result["consistent"] is False


def test_load_bom_csv(tmp_path):
    path = tmp_path / "bom.csv"
    path.write_text("reference,footprint\nR1,R_0603\n", encoding="utf-8-sig")
    rows = load_bom_csv(path)
    assert rows[0]["footprint"] == "R_0603"
