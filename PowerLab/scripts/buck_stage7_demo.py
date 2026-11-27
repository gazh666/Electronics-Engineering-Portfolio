"""第七阶段总验收：真实运行全部实验，汇总为可追溯的验收 JSON。

本脚本只编排已有实验模块，不修改任何波形；所有结论都来自实际运行结果与
``results/stage7`` 下的运行目录。真实未通过项保留为 FAIL，缺测项为 NOT_RESOLVED。
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import platform
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from analysis.stability_analysis import (
    carrier_small_signal_gain,
    solve_operating_duty,
    stability_report,
)
from circuits.closed_loop_config import load_closed_loop_config
from experiments import (
    STAGE7_RESULTS_ROOT,
    BudgetCounter,
    load_transient_limits,
)
from experiments.closed_loop_validation import (
    run_closed_loop_validation,
    steady_state_metrics,
)
from experiments.controller_tuning import run_controller_tuning_experiment
from experiments.line_step import run_line_step_experiment
from experiments.load_step import run_load_step_experiment
from experiments.soft_start import run_soft_start_experiment
from simulations.averaged_model_runner import (
    averaged_metrics,
    averaged_parameters_from_config,
    run_averaged_closed_loop,
)
from simulations.closed_loop_runner import (
    calibrated_open_loop_duty,
    run_closed_loop_with_fallback,
)
from storage.result_store import write_dataframe, write_json

ACCEPTANCE_PATH = STAGE7_RESULTS_ROOT / "stage7_acceptance.json"
CHECKS_CSV_PATH = STAGE7_RESULTS_ROOT / "stage7_acceptance_checks.csv"


def _check(name: str, value: Any, *, low: float | None = None, high: float | None = None) -> dict[str, Any]:
    if value is None or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        return {"name": name, "value": value, "status": "NOT_RESOLVED"}
    numeric = float(value)
    if low is not None and numeric < low:
        return {"name": name, "value": numeric, "low": low, "status": "FAIL"}
    if high is not None and numeric > high:
        return {"name": name, "value": numeric, "high": high, "status": "FAIL"}
    return {"name": name, "value": numeric, "status": "PASS"}


def _environment() -> dict[str, Any]:
    def version(name: str) -> str | None:
        try:
            return importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            return None

    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "pyspice": version("PySpice"),
        "numpy": version("numpy"),
        "pandas": version("pandas"),
        "scipy": version("scipy"),
    }


def _validation_checks(report: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    variants = report.get("model_variants", {})
    for variant, payload in variants.items():
        if payload.get("status") not in ("PASS", "FAIL"):
            checks.append(
                {"name": f"{variant}_closed_loop_validation", "value": payload.get("status"), "status": "NOT_RESOLVED"}
            )
            continue
        for item in payload.get("checks", []):
            checks.append({**item, "name": f"{variant}_{item['name']}"})
    for variant, payload in report.get("open_loop_baseline", {}).items():
        if payload.get("status") != "OK":
            continue
        steady = payload.get("steady_state") or {}
        checks.append(
            _check(f"{variant}_open_loop_steady_mean_v", steady.get("mean_v"), low=4.95, high=5.05)
        )
    averaged = report.get("averaged_model_reference") or {}
    metrics = averaged.get("metrics") or {}
    checks.append(
        _check(
            "averaged_model_load_step_max_deviation_v",
            metrics.get("maximum_absolute_deviation_v"),
            high=0.60,
        )
    )
    return checks


def _experiment_checks(
    load_report: dict[str, Any],
    line_report: dict[str, Any],
    soft_report: dict[str, Any],
    tuning_report: dict[str, Any],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    def event_metric(record: dict[str, Any]) -> dict[str, Any]:
        items = record.get("metrics") or []
        if isinstance(items, dict):
            return items
        return items[0] if items else {}

    closed_records = [
        record
        for record in load_report.get("records", [])
        if record.get("scheme") == "closed_loop" and record.get("model") != "averaged_model"
    ]
    if closed_records:
        worst = max(
            closed_records,
            key=lambda item: float(
                event_metric(item).get("maximum_absolute_deviation_v", -math.inf)
            ),
        )
        checks.append(
            _check(
                "load_step_worst_max_deviation_v",
                event_metric(worst).get("maximum_absolute_deviation_v"),
                high=0.30,
            )
        )
        recovery = (
            event_metric(worst).get("recovery_strict") or {}
        ).get("recovery_time_s")
        checks.append(_check("load_step_worst_recovery_strict_s", recovery, high=0.010))
    else:
        checks.append({"name": "load_step_worst_max_deviation_v", "value": None, "status": "NOT_RESOLVED"})

    line_records = [
        record
        for record in line_report.get("records", [])
        if record.get("scheme") == "closed_loop" and record.get("model") != "averaged_model"
    ]
    if line_records:
        worst_line = max(
            line_records,
            key=lambda item: float(
                (item.get("metrics") or {}).get("maximum_absolute_deviation_v", -math.inf)
            ),
        )
        checks.append(
            _check(
                "line_step_worst_max_deviation_v",
                (worst_line.get("metrics") or {}).get("maximum_absolute_deviation_v"),
                high=0.50,
            )
        )
    else:
        checks.append({"name": "line_step_worst_max_deviation_v", "value": None, "status": "NOT_RESOLVED"})

    soft_records = soft_report.get("records", [])
    if soft_records:
        for record in soft_records:
            startup = record.get("startup") or {}
            checks.append(
                _check(
                    f"soft_start_{record['label']}_overshoot_percent",
                    startup.get("overshoot_percent"),
                    high=10.0,
                )
            )
            checks.append(
                _check(
                    f"soft_start_{record['label']}_peak_inductor_current_a",
                    startup.get("peak_inductor_current_a"),
                    high=4.0,
                )
            )
    else:
        checks.append({"name": "soft_start_overshoot_percent", "value": None, "status": "NOT_RESOLVED"})

    selected = tuning_report.get("selected_stability") or {}
    checks.append(_check("loop_phase_margin_deg", selected.get("phase_margin_deg"), low=45.0))
    gain_margin = selected.get("gain_margin_db")
    if gain_margin is None or (isinstance(gain_margin, float) and not math.isfinite(gain_margin)):
        checks.append(
            {
                "name": "loop_gain_margin_db",
                "value": gain_margin,
                "status": "NOT_RESOLVED",
                "note": "no -180 deg crossing; gain margin undefined for this plant",
            }
        )
    else:
        checks.append(_check("loop_gain_margin_db", gain_margin, low=6.0))
    checks.append(
        _check(
            "tuning_spice_selected_load_step_max_deviation_v",
            (
                (tuning_report.get("spice_checks") or [{}])[0].get("event_metrics") or {}
            ).get("maximum_absolute_deviation_v"),
            high=0.30,
        )
    )
    return checks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="stage 7 full acceptance")
    parser.add_argument("--profile", choices=("smoke", "standard"), default="smoke")
    args = parser.parse_args(argv)

    smoke = args.profile == "smoke"
    counter = BudgetCounter()
    base = load_closed_loop_config()
    limits = load_transient_limits()

    # 1) 平均模型（闭环/开环）与线性化环路分析
    averaged_closed = run_averaged_closed_loop(base, mode="closed_loop")
    counter.add_averaged()
    averaged_open = run_averaged_closed_loop(base, mode="open_loop")
    counter.add_averaged()
    parameters = averaged_parameters_from_config(base)
    duty = solve_operating_duty(parameters, base.target_voltage_v)
    pwm_gain = carrier_small_signal_gain(duty)
    loop_report = stability_report(
        parameters,
        base.controller.kp,
        base.controller.ki,
        target_v=base.target_voltage_v,
        pwm_gain=pwm_gain,
        limits={
            "phase_margin_deg": {"min": 45.0},
            "finite_gain_margin_db": {"min": 6.0},
        },
    )

    # 2) 真实开关级实验
    load_cases = ("load_step_1a_to_2a",) if smoke else (
        "load_step_1a_to_2a",
        "load_step_2a_to_1a",
        "load_step_0p5a_to_2a",
        "load_step_resistive_10_to_2p5",
    )
    line_cases = ("vin_step_down_12_to_9",) if smoke else (
        "vin_step_down_12_to_9",
        "vin_step_up_9_to_12",
        "vin_step_up_12_to_16",
        "vin_step_down_16_to_12",
    )
    durations = (0.0, 0.002) if smoke else (0.0, 0.002, 0.005, 0.010)

    load_report = run_load_step_experiment(
        cases=load_cases,
        budget=counter,
        save_waveform_cases=("load_step_1a_to_2a",),
    )
    line_report = run_line_step_experiment(
        cases=line_cases,
        budget=counter,
        save_waveform_cases=("vin_step_down_12_to_9",),
    )
    soft_report = run_soft_start_experiment(durations_s=durations, budget=counter)
    tuning_report = run_controller_tuning_experiment(budget=counter)

    if smoke:
        validation_report: dict[str, Any] = {
            "status": "NOT_RUN",
            "note": "smoke profile skips the full SW/E validation",
        }
        validation_checks: list[dict[str, Any]] = [
            {"name": "closed_loop_validation", "value": "NOT_RUN", "status": "NOT_RESOLVED"}
        ]
    else:
        validation_report = run_closed_loop_validation(budget=counter)
        validation_checks = _validation_checks(validation_report)

    checks = validation_checks + _experiment_checks(
        load_report, line_report, soft_report, tuning_report
    )
    failed = [item for item in checks if item["status"] == "FAIL"]
    unresolved = [item for item in checks if item["status"] == "NOT_RESOLVED"]

    averaged_metrics_closed = averaged_metrics(averaged_closed)
    averaged_metrics_open = averaged_metrics(averaged_open)
    acceptance = {
        "stage": 7,
        "profile": args.profile,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "data_source": "spice_simulation + averaged_model",
        "environment": _environment(),
        "budget": counter.to_dict(),
        "limits": limits,
        "averaged_model": {
            "closed_loop": {
                "run_id": averaged_closed.run_id,
                "metrics": averaged_metrics_closed,
                "metadata": averaged_closed.metadata,
            },
            "open_loop": {
                "run_id": averaged_open.run_id,
                "metrics": averaged_metrics_open,
                "open_loop_duty_cycle": base.open_loop_duty_cycle,
                "metadata": averaged_open.metadata,
            },
            "not_a_switching_waveform": True,
        },
        "loop_analysis": {
            key: value for key, value in loop_report.items() if key != "frequency_response"
        },
        "experiments": {
            "load_step": load_report,
            "line_step": line_report,
            "soft_start": soft_report,
            "controller_tuning": tuning_report,
            "closed_loop_validation": validation_report,
        },
        "checks": checks,
        "failed_checks": failed,
        "unresolved_checks": unresolved,
        "known_gaps": [
            "no stage 6 code/tests/docs were found in the repository; "
            "baselines come from the real stage 4/5 implementations",
            "the SPICE carrier is a sine wave with a smoothed comparator; "
            "sawtooth PWM exists only in the averaged/PWM analysis modules",
            "gain margin is NOT_RESOLVED because the loop gain never reaches -180 deg",
            "averaged model curves are never presented as switching waveforms",
        ],
        "notes": [
            "open-loop duty is calibrated offline with the averaged model",
            "closed-loop duty is produced by behavioral sources inside the SPICE netlist",
            "failed checks are retained as-is; no post-hoc waveform editing",
            "coarser time steps are only allowed via an explicitly recorded fallback",
        ],
        "artifacts": {
            "load_step_report": load_report.get("report_path"),
            "line_step_report": line_report.get("report_path"),
            "soft_start_report": soft_report.get("report_path"),
            "controller_tuning_report": tuning_report.get("report_path"),
            "closed_loop_validation_report": (
                validation_report.get("report_path") if validation_report else None
            ),
            "tuning_matrix_csv": (tuning_report.get("artifacts") or {}).get("matrix_csv"),
            "selected_loop_bode_csv": (tuning_report.get("artifacts") or {}).get("bode_csv"),
            "acceptance_json": str(ACCEPTANCE_PATH),
        },
    }
    acceptance["overall_status"] = (
        "PASS" if not failed and not unresolved else "PARTIAL_FAILURE"
    )

    STAGE7_RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    write_json(ACCEPTANCE_PATH, acceptance)
    write_dataframe(CHECKS_CSV_PATH, pd.DataFrame(checks))

    print(
        f"[stage7] profile={args.profile} checks={len(checks)} "
        f"failed={len(failed)} unresolved={len(unresolved)} "
        f"status={acceptance['overall_status']}"
    )
    print(
        f"  spice_runs={counter.spice_runs} averaged_runs={counter.averaged_runs} "
        f"wall={counter.wall_clock_s:.1f}s"
    )
    print(
        f"  averaged: closed Vout={averaged_metrics_closed['tail_mean_v']:.5f} V "
        f"peak_iL={averaged_metrics_closed['peak_inductor_current_a']:.3f} A | "
        f"open Vout={averaged_metrics_open['tail_mean_v']:.5f} V "
        f"peak_iL={averaged_metrics_open['peak_inductor_current_a']:.3f} A"
    )
    print(
        f"  loop: duty={duty:.5f} pwm_gain={pwm_gain:.4f} "
        f"PM={loop_report['phase_margin_deg']:.2f} deg "
        f"GM={loop_report['gain_margin_db']} bw={loop_report['bandwidth_hz']:.1f} Hz"
    )
    for item in checks:
        if item["status"] != "PASS":
            print(f"  {item['status']}: {item['name']} = {item['value']}")
    print(f"  acceptance={ACCEPTANCE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
