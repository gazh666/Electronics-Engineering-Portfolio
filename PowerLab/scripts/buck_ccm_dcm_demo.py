"""任务 16：CCM / 临界 / DCM 对比。

三个负载电阻分别真实仿真：

- 2.5 Ω：重载 CCM；
- 16.114 Ω：理想临界负载附近；
- 50 Ω：轻载 DCM。

识别结果必须给出谷值、近零时间占比等证据；数据不足或未稳态时不做强行分类。
"""

from __future__ import annotations

import sys
from dataclasses import replace
from typing import Any

import numpy as np
import pandas as pd

from analysis.steady_state import slice_window
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
from visualization.plots import plot_buck_mode_comparison

CASES = (
    ("CCM (2.5 ohm)", 2.5),
    ("boundary (16.114 ohm)", 16.1144),
    ("DCM (50 ohm)", 50.0),
)
SIMULATION_END_S = 20e-3


def _case_for_load(parameters: BuckParameters, resistance: float) -> BuckParameters:
    return replace(
        parameters,
        circuit=replace(parameters.circuit, load_resistance_ohm=resistance),
    )


def _last_cycles(case, count: int = 2) -> tuple[np.ndarray, np.ndarray]:
    bounds = case.steady_cycle_boundaries_s
    if len(bounds) < count + 1:
        raise ValueError("not enough complete cycles for comparison plot")
    start, end = bounds[-(count + 1)], bounds[-1]
    time, current = slice_window(
        case.waveforms["time_s"], case.waveforms["inductor_current_a"], start, end
    )
    return (time - time[0]) * 1e6, current


def main() -> int:
    parameters: BuckParameters | None = None
    try:
        parameters = load_buck_config()
        limits = default_validation_limits()
        store = ResultStore(root=BUCK_RESULTS_ROOT)
        rows: list[dict[str, Any]] = []
        curves: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        case_objects = []

        for label, resistance in CASES:
            case_parameters = _case_for_load(parameters, resistance)
            case = run_and_analyze(
                case_parameters,
                end_time_s=SIMULATION_END_S,
                allow_extension=False,
                validation_limits=limits,
            )
            _, run_dir = store.create_run_dir(case.result.run_id)
            save_case(case, store, run_dir)
            case_objects.append(case)

            rows.append(
                {
                    "label": label,
                    "load_resistance_ohm": resistance,
                    "vout_mean_v": (
                        None if case.metrics is None else case.metrics["output_voltage_mean_v"]
                    ),
                    "iout_mean_a": (
                        None if case.metrics is None else case.metrics["load_current_mean_a"]
                    ),
                    "peak_current_a": case.mode.peak_current_a,
                    "valley_current_a": case.mode.valley_current_a,
                    "near_zero_ratio": case.mode.near_zero_time_ratio,
                    "near_zero_duration_s": case.mode.near_zero_duration_s,
                    "mode": case.mode.mode.value,
                    "steady_state": case.window.status,
                    "theoretical_mode": case.dcm_theory.dcm_assumption_valid and "DCM" or "CCM",
                    "validation": None if case.validation is None else case.validation.status,
                    "run_id": case.result.run_id,
                    "run_dir": str(run_dir),
                }
            )
            if case.window.is_steady:
                curves[label] = _last_cycles(case)
            print(
                f"{label:<24} mode={rows[-1]['mode']:<22} "
                f"steady={rows[-1]['steady_state']:<18} "
                f"valley={rows[-1]['valley_current_a']:.4f} A "
                f"near_zero={rows[-1]['near_zero_ratio']:.4f}"
            )

        heavy = rows[0]
        boundary = rows[1]
        light = rows[2]
        boundary_case = case_objects[1]
        checks = [
            {
                "name": "heavy_load_ccm",
                "status": "PASS"
                if heavy["mode"] == "CCM" and heavy["steady_state"] == "STEADY_STATE"
                else "FAIL",
            },
            {
                "name": "light_load_dcm_with_evidence",
                "status": "PASS"
                if light["mode"] == "DCM"
                and light["steady_state"] == "STEADY_STATE"
                and light["near_zero_ratio"] >= 0.02
                else "FAIL",
            },
            {
                "name": "boundary_case_not_forced",
                "status": "PASS"
                if boundary["mode"] in ("BOUNDARY_OR_UNCERTAIN", "DCM")
                and boundary["steady_state"] == "STEADY_STATE"
                else "FAIL",
            },
            {
                "name": "theoretical_heavy_ccm",
                "status": "PASS" if heavy["theoretical_mode"] == "CCM" else "FAIL",
            },
            {
                "name": "theoretical_light_dcm",
                "status": "PASS" if light["theoretical_mode"] == "DCM" else "FAIL",
            },
        ]
        status = "PASS" if all(item["status"] == "PASS" for item in checks) else "FAIL"

        summary_id = new_run_id()
        output_dir = STAGE3_RESULTS_ROOT / f"ccm_dcm_{summary_id}"
        output_dir.mkdir(parents=True, exist_ok=True)
        figure_path: str | None = None
        if len(curves) == len(CASES):
            figure_path = str(
                plot_buck_mode_comparison(curves, output_dir / "inductor_current_modes.png")
            )

        summary = {
            "run_id": summary_id,
            "analysis": "buck_ccm_dcm_comparison",
            "data_source": "spice_simulation",
            "simulation_end_s": SIMULATION_END_S,
            "rows": rows,
            "checks": checks,
            "status": status,
            "figure": figure_path,
            "boundary_current_theory_a": boundary_case.theory.boundary_current_a,
        }
        write_json(output_dir / "ccm_dcm.json", summary)
        pd.DataFrame(rows).to_csv(
            output_dir / "ccm_dcm.csv", index=False, encoding="utf-8"
        )
        print(f"Buck CCM/DCM demo: {status}")
        print(f"  summary = {output_dir}")
        return 0 if status == "PASS" else 1
    except Exception as exc:  # noqa: BLE001
        directory = record_failure("buck_ccm_dcm_demo", exc, parameters=parameters)
        print(f"Buck CCM/DCM demo FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        print(f"failure log: {directory}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
