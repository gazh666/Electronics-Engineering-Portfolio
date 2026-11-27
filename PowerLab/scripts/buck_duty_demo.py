"""任务 17-18：占空比变化与输出电压关系。

对 0.25 / 5/12 / 0.5 / 0.6 四个占空比分别进行真实 ngspice 瞬态仿真，
每个运行单独保存，再汇总为一张对照表和一张关系图。
"""

from __future__ import annotations

import sys
from dataclasses import replace
from typing import Any

import pandas as pd

from circuits.buck_config import BuckParameters, load_buck_config
from scripts.buck_common import (
    BUCK_RESULTS_ROOT,
    STAGE3_RESULTS_ROOT,
    default_validation_limits,
    record_failure,
    run_and_analyze,
    save_case,
)
from storage.result_store import ResultStore, new_run_id, write_json
from visualization.plots import plot_buck_duty_relation

DUTY_CYCLES = (0.25, 5.0 / 12.0, 0.5, 0.6)
SIMULATION_END_S = 3e-3


def _case_for_duty(parameters: BuckParameters, duty: float) -> BuckParameters:
    return replace(
        parameters,
        circuit=replace(parameters.circuit, duty_cycle=duty),
        pwm=replace(parameters.pwm, duty_cycle=duty),
    )


def main() -> int:
    parameters: BuckParameters | None = None
    try:
        parameters = load_buck_config()
        limits = default_validation_limits()
        store = ResultStore(root=BUCK_RESULTS_ROOT)
        rows: list[dict[str, Any]] = []

        for duty in DUTY_CYCLES:
            case_parameters = _case_for_duty(parameters, duty)
            case = run_and_analyze(
                case_parameters,
                end_time_s=SIMULATION_END_S,
                validation_limits=limits,
            )
            _, run_dir = store.create_run_dir(case.result.run_id)
            save_case(case, store, run_dir)
            rows.append(
                {
                    "duty_configured": duty,
                    "duty_measured": case.pwm.mean_duty_cycle,
                    "frequency_measured_hz": case.pwm.mean_frequency_hz,
                    "vout_ideal_v": case.theory.ideal_output_voltage_v,
                    "vout_measured_v": (
                        None if case.metrics is None else case.metrics["output_voltage_mean_v"]
                    ),
                    "vout_ripple_vpp": (
                        None if case.metrics is None else case.metrics["output_voltage_ripple_vpp"]
                    ),
                    "mode": case.mode.mode.value,
                    "steady_state": case.window.status,
                    "validation": None if case.validation is None else case.validation.status,
                    "run_id": case.result.run_id,
                    "run_dir": str(run_dir),
                }
            )
            print(
                f"duty={duty:.6f}  Vout={rows[-1]['vout_measured_v']}  "
                f"mode={rows[-1]['mode']}  steady={rows[-1]['steady_state']}  "
                f"validation={rows[-1]['validation']}"
            )

        all_steady = all(row["steady_state"] == "STEADY_STATE" for row in rows)
        measured_duties_ok = all(
            abs(row["duty_measured"] - row["duty_configured"]) <= 0.005 for row in rows
        )
        voltages = [row["vout_measured_v"] for row in rows]
        monotonic = all(
            later is not None and earlier is not None and later > earlier
            for earlier, later in zip(voltages, voltages[1:])
        )
        voltage_errors_ok = all(
            row["vout_measured_v"] is not None
            and abs(row["vout_measured_v"] - row["vout_ideal_v"]) / row["vout_ideal_v"] <= 0.10
            for row in rows
        )

        checks = [
            {"name": "all_runs_steady", "status": "PASS" if all_steady else "FAIL"},
            {"name": "measured_duty_matches", "status": "PASS" if measured_duties_ok else "FAIL"},
            {"name": "vout_monotonic_with_duty", "status": "PASS" if monotonic else "FAIL"},
            {
                "name": "vout_within_10pct_of_ideal",
                "status": "PASS" if voltage_errors_ok else "FAIL",
            },
        ]
        status = "PASS" if all(item["status"] == "PASS" for item in checks) else "FAIL"

        summary_id = new_run_id()
        output_dir = STAGE3_RESULTS_ROOT / f"duty_sweep_{summary_id}"
        output_dir.mkdir(parents=True, exist_ok=True)

        if all_steady:
            figure = plot_buck_duty_relation(
                [row["duty_measured"] for row in rows],
                [row["vout_ideal_v"] for row in rows],
                [row["vout_measured_v"] for row in rows],
                output_dir / "vout_vs_duty.png",
            )
            figure_path: str | None = str(figure)
        else:
            figure_path = None

        summary = {
            "run_id": summary_id,
            "analysis": "buck_duty_sweep",
            "data_source": "spice_simulation",
            "simulation_end_s": SIMULATION_END_S,
            "rows": rows,
            "checks": checks,
            "status": status,
            "figure": figure_path,
        }
        write_json(output_dir / "duty_sweep.json", summary)
        pd.DataFrame(rows).to_csv(output_dir / "duty_sweep.csv", index=False, encoding="utf-8")

        print(f"Buck duty demo: {status}")
        print(f"  summary = {output_dir}")
        return 0 if status == "PASS" else 1
    except Exception as exc:  # noqa: BLE001
        directory = record_failure("buck_duty_demo", exc, parameters=parameters)
        print(f"Buck duty demo FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        print(f"failure log: {directory}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
