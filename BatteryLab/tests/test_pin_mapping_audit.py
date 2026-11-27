import csv

import pytest

from eda_tools.pin_mapping_audit import (
    audit_mapping_completeness,
    audit_pin_mapping,
    summarize_audit,
)

NETLIST = {
    "components": {"U1": {"value": "BQ76922"}, "R1": {"value": "47"}},
    "nets": {},
    "pin_to_net": {
        ("U1", "2"): "CELL_2_POS",
        ("U1", "3"): "CELL_2_NEG",
        ("U1", "4"): "CELL_2_NEG",
        ("U1", "7"): "CELL_1_POS",
        ("U1", "10"): "GND",
    },
}

FIELDS = [
    "reference", "pin_number", "pin_name", "expected_net",
    "connection_rule", "source_document", "source_page", "verified",
]


def write_mapping(tmp_path, rows):
    path = tmp_path / "mapping.csv"
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_exact_net_pass(tmp_path):
    path = write_mapping(tmp_path, [
        {"reference": "U1", "pin_number": "2", "pin_name": "VC5", "expected_net": "CELL_2_POS",
         "connection_rule": "EXACT_NET", "source_document": "SLUSE86A", "source_page": "3", "verified": "true"},
    ])
    results = audit_pin_mapping(NETLIST, path)
    assert results[0]["status"] == "PASS"


def test_exact_net_fail(tmp_path):
    path = write_mapping(tmp_path, [
        {"reference": "U1", "pin_number": "2", "pin_name": "VC5", "expected_net": "WRONG",
         "connection_rule": "EXACT_NET", "source_document": "SLUSE86A", "source_page": "3", "verified": "true"},
    ])
    results = audit_pin_mapping(NETLIST, path)
    assert results[0]["status"] == "FAIL"
    assert results[0]["actual_net"] == "CELL_2_POS"


def test_unverified_row_is_not_pass(tmp_path):
    path = write_mapping(tmp_path, [
        {"reference": "U1", "pin_number": "2", "pin_name": "VC5", "expected_net": "CELL_2_POS",
         "connection_rule": "EXACT_NET", "source_document": "TBD", "source_page": "TBD", "verified": "false"},
    ])
    results = audit_pin_mapping(NETLIST, path)
    assert results[0]["status"] == "NOT_VERIFIED"


def test_same_net_as(tmp_path):
    path = write_mapping(tmp_path, [
        {"reference": "U1", "pin_number": "4", "pin_name": "VC4B", "expected_net": "U1.3",
         "connection_rule": "SAME_NET_AS", "source_document": "SLUSE86A", "source_page": "3", "verified": "true"},
    ])
    results = audit_pin_mapping(NETLIST, path)
    assert results[0]["status"] == "PASS"


def test_allowed_unconnected(tmp_path):
    path = write_mapping(tmp_path, [
        {"reference": "U1", "pin_number": "26", "pin_name": "PDSG", "expected_net": "",
         "connection_rule": "ALLOWED_UNCONNECTED", "source_document": "SLUSE86A", "source_page": "62", "verified": "true"},
    ])
    results = audit_pin_mapping(NETLIST, path)
    assert results[0]["status"] == "PASS"


def test_unknown_rule_requires_manual_review(tmp_path):
    path = write_mapping(tmp_path, [
        {"reference": "U1", "pin_number": "2", "pin_name": "VC5", "expected_net": "CELL_2_POS",
         "connection_rule": "SOME_NEW_RULE", "source_document": "SLUSE86A", "source_page": "3", "verified": "true"},
    ])
    results = audit_pin_mapping(NETLIST, path)
    assert results[0]["status"] == "MANUAL_REVIEW"


def test_summarize_audit():
    summary = summarize_audit([
        {"status": "PASS"}, {"status": "FAIL"}, {"status": "NOT_VERIFIED"}, {"status": "PASS"},
    ])
    assert summary["PASS"] == 2
    assert summary["FAIL"] == 1
    assert summary["total"] == 4


def test_completeness_accepts_thermal_pad_row(tmp_path):
    rows = [
        {"reference": "U1", "pin_number": str(i), "pin_name": f"P{i}", "expected_net": "N",
         "connection_rule": "EXACT_NET", "source_document": "DS", "source_page": "1", "verified": "true"}
        for i in range(1, 5)
    ]
    rows.append({
        "reference": "U1", "pin_number": "PAD", "pin_name": "Thermal Pad", "expected_net": "GND",
        "connection_rule": "EXACT_NET", "source_document": "DS", "source_page": "1", "verified": "true",
    })
    path = write_mapping(tmp_path, rows)
    result = audit_mapping_completeness(path, 4)
    assert result["complete"] is True
    assert result["numeric_rows"] == 4
    assert result["non_numeric_rows"] == ["PAD"]


def test_completeness_detects_missing_pin(tmp_path):
    rows = [
        {"reference": "U1", "pin_number": "1", "pin_name": "A", "expected_net": "N",
         "connection_rule": "EXACT_NET", "source_document": "DS", "source_page": "1", "verified": "true"},
    ]
    path = write_mapping(tmp_path, rows)
    result = audit_mapping_completeness(path, 3)
    assert result["complete"] is False
    assert result["missing_pin_numbers"] == ["2", "3"]
