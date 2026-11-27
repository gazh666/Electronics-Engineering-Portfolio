"""第三阶段综合演示：理论、基础瞬态、启动、稳态、占空比、CCM/DCM、时间步长。

本脚本只做汇总与额外实验，不替代各专项脚本；所有数值均来自本次真实运行。
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
    startup_metrics,
)
from storage.result_store import ResultStore, new_run_id, write_json
from visualization.plots import (
    plot_buck_duty_relation,
    plot_buck_mode_comparison,
    plot_buck_startup,
    plot_buck_startup_current,
    plot_buck_switching_overview,
    plot_buck_timestep_comparison,
)

DUTY_CYCLES = (0.25, 5.0 / 12.0, 0.5, 0.6)
LOAD_CASES = (
    ("CCM (2.5 ohm)", 2.5),
    ("boundary (16.114 ohm)", 16.1144),
    ("DCM (50 ohm)", 50.0),
)
TIMESTEP_CASES = (("100 ns", 100e-9), ("50 ns", 50e-9), ("25 ns", 25e-9))
DUTY_END_S = 3e-3
MODE_END_S = 20e-3
BASE_END_S = 5e-3


def _with_duty(parameters: BuckParameters, duty: float) -> BuckParameters:
    return replace(
        parameters,
        circuit=replace(parameters.circuit, duty_cycle=duty),
        pwm=replace(parameters.pwm, duty_cycle=duty),
    )


def _with_load(parameters: BuckParameters, resistance: float) -> BuckParameters:
    return replace(
        parameters,
        circuit=replace(parameters.circuit, load_resistance_ohm=resistance),
    )


def _with_timestep(parameters: BuckParameters, max_step_s: float) -> BuckParameters:
    return replace(
        parameters,
        transient=replace(
            parameters.transient,
            max_step_time_s=max_step_s,
            step_time_s=max(parameters.transient.step_time_s, max_step_s),
        ),
    )


def _last_cycles(case, count: int = 2) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    bounds = case.steady_cycle_boundaries_s
    if len(bounds) < count + 1:
        raise ValueError("not enough complete cycles for comparison plot")
    start, end = bounds[-(count + 1)], bounds[-1]
    time, voltage = slice_window(
        case.waveforms["time_s"], case.waveforms["vout_v"], start, end
    )
    _, current = slice_window(
        case.waveforms["time_s"], case.waveforms["inductor_current_a"], start, end
    )
    return (time - time[0]) * 1e6, voltage, current


def _save_plain(case, store: ResultStore) -> str:
    _, run_dir = store.create_run_dir(case.result.run_id)
    save_case(case, store, run_dir)
    return str(run_dir)


def main() -> int:
    parameters: BuckParameters | None = None
    try:
        parameters = load_buck_config()
        limits = default_validation_limits()
        store = ResultStore(root=BUCK_RESULTS_ROOT)

        print("1/5 default 5 ms transient")
        base_case = run_and_analyze(parameters, validation_limits=limits)
        base_startup = startup_metrics(base_case)

        print("2/5 duty sweep")
        duty_rows: list[dict[str, Any]] = []
        duty_cases: dict[float, Any] = {}
        for duty in DUTY_CYCLES:
            case = run_and_analyze(
                _with_duty(parameters, duty),
                end_time_s=DUTY_END_S,
                validation_limits=limits,
            )
            duty_cases[duty] = case
            duty_rows.append(
                {
                    "duty_configured": duty,
                    "duty_measured": case.pwm.mean_duty_cycle,
                    "vout_ideal_v": case.theory.ideal_output_voltage_v,
                    "vout_measured_v": (
                        None if case.metrics is None else case.metrics["output_voltage_mean_v"]
                    ),
                    "ripple_vpp": (
                        None if case.metrics is None else case.metrics["output_voltage_ripple_vpp"]
                    ),
                    "mode": case.mode.mode.value,
                    "steady_state": case.window.status,
                    "validation": None if case.validation is None else case.validation.status,
                    "run_id": case.result.run_id,
                    "run_dir": _save_plain(case, store),
                }
            )

        print("3/5 CCM / boundary / DCM")
        mode_rows: list[dict[str, Any]] = []
        mode_curves: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        for label, resistance in LOAD_CASES:
            case = run_and_analyze(
                _with_load(parameters, resistance),
                end_time_s=MODE_END_S,
                allow_extension=False,
                validation_limits=limits,
            )
            mode_rows.append(
                {
                    "label": label,
                    "load_resistance_ohm": resistance,
                    "vout_mean_v": (
                        None if case.metrics is None else case.metrics["output_voltage_mean_v"]
                    ),
                    "peak_current_a": case.mode.peak_current_a,
                    "valley_current_a": case.mode.valley_current_a,
                    "near_zero_ratio": case.mode.near_zero_time_ratio,
                    "mode": case.mode.mode.value,
                    "steady_state": case.window.status,
                    "validation": None if case.validation is None else case.validation.status,
                    "run_id": case.result.run_id,
                    "run_dir": _save_plain(case, store),
                }
            )
            if case.window.is_steady:
                time_us, _, current = _last_cycles(case)
                mode_curves[label] = (time_us, current)

        print("4/5 time-step comparison")
        timestep_rows: list[dict[str, Any]] = []
        output_curves: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        current_curves: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        timestep_cases: dict[str, Any] = {"50 ns": base_case}
        for label, max_step in TIMESTEP_CASES:
            if label == "50 ns":
                case = base_case
            else:
                case = run_and_analyze(
                    _with_timestep(parameters, max_step),
                    end_time_s=BASE_END_S,
                    allow_extension=False,
                    validation_limits=limits,
                )
                timestep_cases[label] = case
                _save_plain(case, store)
            statistics = case.result.metadata.get("time_step_statistics", {})
            timestep_rows.append(
                {
                    "max_step": label,
                    "max_step_s": max_step,
                    "point_count": case.result.point_count,
                    "duration_ms": case.result.duration_ms,
                    "actual_max_step_s": statistics.get("max_step_s"),
                    "max_step_respected": statistics.get("max_step_respected"),
                    "vout_mean_v": (
                        None if case.metrics is None else case.metrics["output_voltage_mean_v"]
                    ),
                    "vout_ripple_vpp": (
                        None if case.metrics is None else case.metrics["output_voltage_ripple_vpp"]
                    ),
                    "il_ripple_app": (
                        None if case.metrics is None else case.metrics["inductor_current_ripple_app"]
                    ),
                    "steady_state": case.window.status,
                    "run_id": case.result.run_id,
                    "run_dir": str(BUCK_RESULTS_ROOT / f"run_{case.result.run_id}"),
                }
            )
            if case.window.is_steady:
                time_us, voltage, current = _last_cycles(case)
                output_curves[label] = (time_us, voltage)
                current_curves[label] = (time_us, current)

        print("5/5 summary and plots")
        _, run_dir = store.create_run_dir(base_case.result.run_id)
        plots_dir = run_dir / "plots"
        plots_dir.mkdir(parents=True, exist_ok=True)
        starts = base_case.pwm.cycle_start_times_s
        switching_start, switching_end = starts[-3], base_case.pwm.cycle_end_times_s[-1]

        figures: dict[str, str] = {
            "plots/startup_output_voltage.png": str(
                plot_buck_startup(
                    base_case.waveforms["time_s"],
                    base_case.waveforms["vout_v"],
                    plots_dir / "startup_output_voltage.png",
                    target_voltage_v=parameters.circuit.target_output_voltage_v,
                    steady_window=(
                        base_case.window.start_time_s,
                        base_case.window.end_time_s,
                    ),
                )
            ),
            "plots/startup_inductor_current.png": str(
                plot_buck_startup_current(
                    base_case.waveforms["time_s"],
                    base_case.waveforms["inductor_current_a"],
                    plots_dir / "startup_inductor_current.png",
                    steady_mean_a=(
                        base_case.metrics["inductor_current_mean_a"]
                        if base_case.metrics
                        else None
                    ),
                    startup_peak_a=base_startup["peak_inductor_current_a"],
                )
            ),
            "plots/switching_waveforms.png": str(
                plot_buck_switching_overview(
                    base_case.waveforms["time_s"],
                    base_case.waveforms["gate_v"],
                    base_case.waveforms["switch_node_v"],
                    base_case.waveforms["inductor_current_a"],
                    base_case.waveforms["vout_v"],
                    plots_dir / "switching_waveforms.png",
                    start_s=switching_start,
                    end_s=switching_end,
                )
            ),
        }
        if len(duty_cases) == len(DUTY_CYCLES) and all(
            case.metrics is not None for case in duty_cases.values()
        ):
            figures["plots/vout_vs_duty.png"] = str(
                plot_buck_duty_relation(
                    [case.pwm.mean_duty_cycle for case in duty_cases.values()],
                    [case.theory.ideal_output_voltage_v for case in duty_cases.values()],
                    [case.metrics["output_voltage_mean_v"] for case in duty_cases.values()],
                    plots_dir / "vout_vs_duty.png",
                )
            )
        if len(mode_curves) == len(LOAD_CASES):
            figures["plots/inductor_current_modes.png"] = str(
                plot_buck_mode_comparison(
                    mode_curves, plots_dir / "inductor_current_modes.png"
                )
            )
        if output_curves:
            figures["plots/timestep_comparison.png"] = str(
                plot_buck_timestep_comparison(
                    output_curves,
                    current_curves,
                    plots_dir / "timestep_comparison.png",
                    output_zoom_v=(
                        base_case.metrics["output_voltage_ripple_vpp"]
                        if base_case.metrics
                        else None
                    ),
                )
            )

        limits_payload = limits.to_dict()
        checks: list[dict[str, Any]] = [
            {
                "name": "default_case_steady",
                "status": "PASS" if base_case.window.is_steady else "FAIL",
                "detail": base_case.window.status,
            },
            {
                "name": "default_validation",
                "status": (
                    "PASS"
                    if base_case.validation is not None
                    and base_case.validation.status == "PASS"
                    else "FAIL"
                ),
                "detail": None if base_case.validation is None else base_case.validation.status,
            },
            {
                "name": "duty_sweep_all_steady",
                "status": "PASS" if all(row["steady_state"] == "STEADY_STATE" for row in duty_rows) else "FAIL",
            },
            {
                "name": "mode_heavy_ccm",
                "status": "PASS"
                if mode_rows[0]["mode"] == "CCM"
                and mode_rows[0]["steady_state"] == "STEADY_STATE"
                else "FAIL",
            },
            {
                "name": "mode_light_dcm",
                "status": "PASS"
                if mode_rows[2]["mode"] == "DCM"
                and mode_rows[2]["steady_state"] == "STEADY_STATE"
                else "FAIL",
            },
            {
                "name": "time_step_respected",
                "status": "PASS"
                if all(row["max_step_respected"] for row in timestep_rows)
                else "FAIL",
            },
        ]
        if len(timestep_rows) == 3 and timestep_rows[0]["vout_ripple_vpp"]:
            base_ripple = timestep_rows[1]["vout_ripple_vpp"]
            ripple_spread = max(
                abs(row["vout_ripple_vpp"] - base_ripple) / base_ripple
                for row in timestep_rows
                if row["vout_ripple_vpp"]
            )
            checks.append(
                {
                    "name": "timestep_ripple_sensitivity",
                    "status": "PASS" if ripple_spread <= 0.20 else "FAIL",
                    "detail": ripple_spread,
                }
            )
        else:
            ripple_spread = None

        status = "PASS" if all(item["status"] == "PASS" for item in checks) else "FAIL"

        summary_id = new_run_id()
        summary_dir = STAGE3_RESULTS_ROOT / f"stage3_{summary_id}"
        summary_dir.mkdir(parents=True, exist_ok=True)

        payload = {
            "run_id": summary_id,
            "analysis": "buck_stage3_comprehensive",
            "data_source": "spice_simulation",
            "specification_type": "project_assumption",
            "base_run_id": base_case.result.run_id,
            "base_run_dir": str(run_dir),
            "default_case": {
                "mode": base_case.mode.mode.value,
                "steady_state": base_case.window.to_dict(),
                "metrics": base_case.metrics,
                "startup": base_startup,
                "validation": (
                    None if base_case.validation is None else base_case.validation.status
                ),
                "time_step_statistics": base_case.result.metadata.get("time_step_statistics"),
            },
            "duty_sweep": duty_rows,
            "mode_comparison": mode_rows,
            "timestep_comparison": timestep_rows,
            "validation_limits": limits_payload,
            "checks": checks,
            "status": status,
            "figures_dir": str(plots_dir),
        }
        write_json(summary_dir / "stage3_summary.json", payload)
        pd.DataFrame(duty_rows).to_csv(
            summary_dir / "duty_sweep.csv", index=False, encoding="utf-8"
        )
        pd.DataFrame(mode_rows).to_csv(
            summary_dir / "mode_comparison.csv", index=False, encoding="utf-8"
        )
        pd.DataFrame(timestep_rows).to_csv(
            summary_dir / "timestep_comparison.csv", index=False, encoding="utf-8"
        )

        saved = save_case(
            base_case,
            store,
            run_dir,
            figures=figures,
            extra_json_files={
                "stage3_summary.json": payload,
                "startup_metrics.json": base_startup,
            },
            summary_extra={
                "stage3_status": status,
                "duty_runs": len(duty_rows),
                "mode_runs": len(mode_rows),
                "timestep_runs": len(timestep_rows),
            },
        )

        print("Buck stage 3 comprehensive")
        print(f"  base run dir   = {saved}")
        print(f"  summary dir    = {summary_dir}")
        print(f"  default Vout   = {base_case.metrics['output_voltage_mean_v']:.6f} V")
        print(f"  default ripple = {base_case.metrics['output_voltage_ripple_vpp'] * 1e3:.3f} mVpp")
        print(f"  mode           = {base_case.mode.mode.value}")
        print(f"  validation     = {base_case.validation.status}")
        print(f"  status         = {status}")
        return 0 if status == "PASS" else 1
    except Exception as exc:  # noqa: BLE001
        directory = record_failure("buck_stage3_demo", exc, parameters=parameters)
        print(f"Buck stage 3 demo FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        print(f"failure log: {directory}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
