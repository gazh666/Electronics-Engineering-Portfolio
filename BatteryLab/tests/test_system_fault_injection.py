"""故障注入与保护许可测试。"""

from __future__ import annotations

from validation.system_fault_injection import default_scenarios, run_fault_scenarios


def test_all_default_scenarios_pass() -> None:
    report = run_fault_scenarios()
    assert report["scenario_count"] >= 10
    failed = [item for item in report["records"] if item["status"] != "PASS"]
    assert not failed, failed
    assert report["fail_count"] == 0
    assert report["error_count"] == 0


def test_thresholds_are_not_claimed_as_register_values() -> None:
    report = run_fault_scenarios()
    assert report["thresholds_are_bq76922_register_values"] is False


def test_undervoltage_blocks_discharge() -> None:
    report = run_fault_scenarios()
    record = next(item for item in report["records"] if item["scenario"] == "single_cell_undervoltage")
    assert record["discharge_allowed"] is False
    assert record["latched_faults"]


def test_invalid_measurement_is_safe() -> None:
    report = run_fault_scenarios()
    record = next(item for item in report["records"] if item["scenario"] == "invalid_measurement")
    assert record["charge_allowed"] is False
    assert record["discharge_allowed"] is False


def test_latched_fault_requires_explicit_recovery() -> None:
    report = run_fault_scenarios()
    record = next(item for item in report["records"] if item["scenario"] == "latch_requires_explicit_reset")
    assert record["recovery_request_accepted"] is False
    assert record["recovered_permission"] is None


def test_no_fault_scenario_does_not_trip() -> None:
    report = run_fault_scenarios()
    record = next(item for item in report["records"] if item["scenario"] == "no_fault_nominal")
    assert record["charge_allowed"] is True
    assert record["discharge_allowed"] is True
    assert record["latched_faults"] == []


def test_scenario_list_is_stable() -> None:
    first = {item.name for item in default_scenarios(__import__("protection.limits", fromlist=["load_limits"]).load_limits())}
    second = {item.name for item in default_scenarios(__import__("protection.limits", fromlist=["load_limits"]).load_limits())}
    assert first == second
