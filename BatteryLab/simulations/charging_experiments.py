"""20 个充电工况的统一调度与汇总。

不同层次严格分开：
- ``spice_simulation``：真实 ngspice 开关级双闭环（C01–C10、C19、C20）；
- ``ecm_charge_envelope``：秒级 ECM 长时包络 + 真实保护控制器（C11、C16、C18）；
- ``behavioral_charging_simulation``：行为级终止判定（C14）；
- ``software_test``：纯离散事件保护/终止逻辑（C12、C13、C15、C17）。

任何层次的结论只在自身层次成立，汇总中始终保留 ``method`` 字段。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from charging.config import ChargingCase, load_charger_config, load_charging_cases
from simulations.charger_spice_runner import CaseRun, run_case
from simulations.long_duration_charge import (
    LongChargeParameters,
    latched_restart_test,
    measurement_invalid_test,
    simulate_long_charge,
    simulate_termination_interruption,
    temperature_gate_test,
)
from storage.result_store import RunDirectory


class ExperimentError(RuntimeError):
    """工况调度失败。"""


def _status(result: Mapping[str, Any]) -> str:
    return str(result.get("status") or result.get("case_status") or "NOT_MEASURED")


def _long_parameters(case: ChargingCase, *, default_initial_socs: Sequence[float] = (0.3, 0.3, 0.3)) -> LongChargeParameters:
    charger = load_charger_config()
    parameters = dict(case.parameters)
    socs = parameters.get("initial_socs", list(default_initial_socs))
    return LongChargeParameters(
        initial_socs=tuple(float(value) for value in socs),
        current_limit_a=float(parameters.get("current_limit_a", charger.charging.constant_current_a)),
        voltage_target_v=charger.charging.constant_voltage_v,
        termination_current_a=float(
            parameters.get("termination_current_a", charger.charging.termination_current_a)
        ),
        termination_hold_s=float(parameters.get("hold_s", charger.charging.termination_hold_time_s)),
        maximum_charge_time_s=float(
            parameters.get("maximum_charge_time_s", charger.charging.maximum_charge_time_s)
        ),
        voltage_regulation_enabled=bool(parameters.get("voltage_regulation_enabled", True)),
        capacities_ah=(
            tuple(float(value) for value in parameters["capacity_ah"])
            if "capacity_ah" in parameters
            else None
        ),
        model_id=charger.battery.identified_model_id,
    )


def _envelope_verdict(case: ChargingCase, summary: Mapping[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    checks: list[dict[str, Any]] = []
    if case.id == "C11":
        fault = bool(summary.get("protection", {}).get("latched_faults"))
        max_cell = float(summary.get("max_cell_voltage_v", 0.0))
        pack_at_trip = summary.get("max_cell_voltage_at_pack_v")
        checks.append(
            {
                "name": "protection_latched_overvoltage",
                "measured": max_cell,
                "limit": 4.25,
                "unit": "V",
                "status": "PASS" if fault and max_cell >= 4.25 else "FAIL",
            }
        )
        checks.append(
            {
                "name": "pack_below_cv_target_at_trip",
                "measured": pack_at_trip,
                "limit": 12.15,
                "unit": "V",
                "status": "PASS"
                if pack_at_trip is not None and float(pack_at_trip) < 12.15
                else "FAIL",
            }
        )
    elif case.id == "C16":
        timed_out = summary.get("state") == "TIMEOUT"
        duration = float(summary.get("duration_s", 0.0))
        checks.append(
            {
                "name": "timeout_reached",
                "measured": duration,
                "limit": float(_long_parameters(case).maximum_charge_time_s),
                "unit": "s",
                "status": "PASS" if timed_out else "FAIL",
            }
        )
    elif case.id == "C18":
        allowed = summary.get("protection", {}).get("charge_allowed")
        consistency = summary.get("soc_consistency_ah")
        checks.append(
            {
                "name": "charge_allowed_no_fault",
                "measured": 1.0 if allowed else 0.0,
                "limit": 1.0,
                "unit": "bool",
                "status": "PASS" if allowed else "FAIL",
            }
        )
        checks.append(
            {
                "name": "soc_consistency_tolerance_ah",
                "measured": consistency,
                "limit": 0.005,
                "unit": "Ah",
                "status": "PASS"
                if consistency is not None and abs(float(consistency)) <= 0.005
                else "FAIL",
            }
        )
    status = "PASS" if checks and all(item["status"] == "PASS" for item in checks) else "FAIL"
    return status, checks


def _run_envelope_case(case: ChargingCase) -> dict[str, Any]:
    parameters = _long_parameters(case)
    result = simulate_long_charge(parameters)
    status, checks = _envelope_verdict(case, result.summary)
    return {
        "case_id": case.id,
        "name": case.name,
        "method": case.method,
        "status": status,
        "checks": checks,
        "summary": result.summary,
        "waveform": result,
    }


def _run_behavioral_case(case: ChargingCase) -> dict[str, Any]:
    parameters = _long_parameters(case)
    result = simulate_long_charge(parameters)
    completed = result.state == "COMPLETE" and result.termination_reason == "TERMINATION_CURRENT"
    checks = [
        {
            "name": "termination_complete",
            "measured": float(result.time_s[-1]),
            "limit": None,
            "unit": "s",
            "status": "PASS" if completed else "FAIL",
        },
        {
            "name": "final_current_below_limit",
            "measured": float(result.charging_current_a[-1]),
            "limit": parameters.termination_current_a,
            "unit": "A",
            "status": "PASS"
            if float(result.charging_current_a[-1]) <= parameters.termination_current_a
            else "FAIL",
        },
    ]
    return {
        "case_id": case.id,
        "name": case.name,
        "method": case.method,
        "status": "PASS" if all(item["status"] == "PASS" for item in checks) else "FAIL",
        "checks": checks,
        "summary": result.summary,
        "waveform": result,
    }


def _run_software_case(case: ChargingCase) -> dict[str, Any]:
    parameters = dict(case.parameters)
    if case.id == "C12":
        payload = temperature_gate_test(float(parameters.get("temperature_c", 50.0)))
    elif case.id == "C13":
        payload = measurement_invalid_test()
    elif case.id == "C15":
        payload = simulate_termination_interruption()
    elif case.id == "C17":
        payload = latched_restart_test()
    else:
        raise ExperimentError(f"未实现的软件工况: {case.id}")
    return {
        "case_id": case.id,
        "name": case.name,
        "method": case.method,
        "status": _status(payload),
        "checks": [],
        "summary": payload,
        "waveform": None,
    }


def run_experiment(case: ChargingCase, *, persist_spice: bool = False) -> dict[str, Any]:
    if case.method == "spice_simulation":
        run: CaseRun = run_case(case.id, persist=persist_spice)
        return {
            "case_id": case.id,
            "name": case.name,
            "method": case.method,
            "status": run.summary["case_status"],
            "checks": run.checks,
            "summary": run.summary,
            "waveform": run.waveform,
            "run_dir": None if run.run_dir is None else str(run.run_dir.path),
        }
    if case.method == "ecm_charge_envelope":
        return _run_envelope_case(case)
    if case.method == "behavioral_charging_simulation":
        return _run_behavioral_case(case)
    if case.method == "software_test":
        return _run_software_case(case)
    raise ExperimentError(f"未实现的仿真层次: {case.method}")


def run_all(
    *,
    case_ids: Sequence[str] | None = None,
    persist_spice: bool = False,
    persist_summary: bool = True,
) -> dict[str, Any]:
    cases = load_charging_cases()
    if case_ids is not None:
        selected = set(case_ids)
        cases = [case for case in cases if case.id in selected]
    results: list[dict[str, Any]] = []
    for case in cases:
        results.append(run_experiment(case, persist_spice=persist_spice))

    failed = [item["case_id"] for item in results if item["status"] != "PASS"]
    summary = {
        "stage": "stage6",
        "case_count": len(results),
        "passed": len(results) - len(failed),
        "failed_cases": failed,
        "status": "PASS" if not failed else "FAIL",
        "cases": [
            {
                "case_id": item["case_id"],
                "name": item["name"],
                "method": item["method"],
                "status": item["status"],
                "checks": item["checks"],
                "summary": item["summary"],
                "run_dir": item.get("run_dir"),
            }
            for item in results
        ],
    }
    if persist_summary:
        run_dir = RunDirectory("stage6")
        run_dir.write_metadata({"stage": "stage6", "kind": "charging_experiments"})
        run_dir.write_config_snapshot(
            {
                "charger": load_charger_config().to_dict(),
                "cases": [case.to_dict() for case in cases],
            }
        )
        run_dir.write_summary(summary)
        for item in results:
            waveform = item.get("waveform")
            if waveform is None:
                continue
            columns = waveform.to_columns()
            header = list(columns)
            rows = (
                tuple(columns[name][index] for name in header)
                for index in range(waveform.time_s.size)
            )
            run_dir.write_waveform(header, rows, name=f"{item['case_id']}_waveform.csv")
        run_dir.flush_log()
        summary["run_dir"] = str(run_dir.path)
    return summary


def method_matrix() -> list[dict[str, Any]]:
    return [
        {"case_id": case.id, "name": case.name, "method": case.method}
        for case in load_charging_cases()
    ]


def method_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for case in load_charging_cases():
        counts[case.method] = counts.get(case.method, 0) + 1
    return counts
