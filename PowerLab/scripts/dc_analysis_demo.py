"""分压电路工作点与 0–12 V 直流扫描演示。

运行：``python -m scripts.dc_analysis_demo``
产物：``results/basic_circuits/run_<run_id>/`` 下的真实仿真数据与对比。
"""

from __future__ import annotations

import json
import sys
from typing import Any

import numpy as np
import pandas as pd

from analysis.error_metrics import calculate_error_metrics, relative_error_percent
from analysis.theory import (
    DATA_SOURCE,
    voltage_divider_current,
    voltage_divider_voltage,
)
from circuits.voltage_divider import build_voltage_divider, divider_transfer_slope
from simulations.config import BasicCircuitsConfig, load_basic_circuits_config
from simulations.runner import SimulationRunner
from storage.result_store import ResultStore
from visualization.plots import plot_dc_transfer, plot_error


def analyze(
    config: BasicCircuitsConfig | None = None,
    store: ResultStore | None = None,
) -> dict[str, Any]:
    config = config or load_basic_circuits_config()
    store = store or ResultStore()
    runner = SimulationRunner(config.simulation_temperature_c)

    divider_config = config.voltage_divider
    circuit = build_voltage_divider(
        divider_config.vin_v,
        divider_config.r1_ohm,
        divider_config.r2_ohm,
    )

    # ---------------------------------------------------------------- OP
    op = runner.run_operating_point(circuit, parameters=divider_config.to_dict())
    vin = float(op.data["vin_v"].iloc[0])
    vout = float(op.data["out_v"].iloc[0])
    branch_current = float(op.data["vinput_branch_current_a"].iloc[0])
    supply_current = -branch_current

    theory_vout = voltage_divider_voltage(
        divider_config.vin_v, divider_config.r1_ohm, divider_config.r2_ohm
    )
    theory_current = voltage_divider_current(
        divider_config.vin_v, divider_config.r1_ohm, divider_config.r2_ohm
    )
    kcl_residual = (vin - vout) / divider_config.r1_ohm - vout / divider_config.r2_ohm
    kvl_residual = vin - supply_current * divider_config.r1_ohm - vout

    op_waveform = op.data.copy()
    op_waveform["supply_current_a"] = supply_current
    op_theory = pd.DataFrame(
        [
            {
                "vin_v": divider_config.vin_v,
                "theoretical_vout_v": theory_vout,
                "theoretical_current_a": theory_current,
                "data_source": DATA_SOURCE,
            }
        ]
    )
    op_comparison = pd.DataFrame(
        [
            {
                "simulated_vout_v": vout,
                "theoretical_vout_v": theory_vout,
                "absolute_error_v": vout - theory_vout,
                "simulated_supply_current_a": supply_current,
                "theoretical_current_a": theory_current,
                "current_error_a": supply_current - theory_current,
                "kcl_residual_a": kcl_residual,
                "kvl_residual_v": kvl_residual,
            }
        ]
    )
    op_summary = {
        "status": "PASS",
        "vin_v": vin,
        "vout_v": vout,
        "theoretical_vout_v": theory_vout,
        "absolute_error_v": vout - theory_vout,
        "supply_current_a": supply_current,
        "theoretical_current_a": theory_current,
        "kcl_residual_a": kcl_residual,
        "kvl_residual_v": kvl_residual,
        "point_count": op.point_count,
        "duration_ms": op.duration_ms,
        "analysis_command": op.metadata.get("analysis_command"),
    }
    _, op_dir = store.create_run_dir(op.run_id)
    store.save_result(
        op,
        run_dir=op_dir,
        analysis_parameters={
            "vin_v": divider_config.vin_v,
            "r1_ohm": divider_config.r1_ohm,
            "r2_ohm": divider_config.r2_ohm,
        },
        config_snapshot=config.to_dict(),
        theory=op_theory,
        comparison=op_comparison,
        waveform=op_waveform,
        summary=op_summary,
        log_lines=["operating point solved with real ngspice"],
    )

    # ---------------------------------------------------------------- DC
    dc_config = config.divider_dc_sweep
    dc = runner.run_dc(
        circuit,
        "input",
        dc_config.start_v,
        dc_config.stop_v,
        dc_config.step_v,
        parameters=divider_config.to_dict(),
    )
    sweep = dc.data["sweep_v"].to_numpy()
    simulated_vout = dc.data["out_v"].to_numpy()
    theoretical_vout = sweep * divider_transfer_slope(
        divider_config.r1_ohm, divider_config.r2_ohm
    )
    supplied_current = -dc.data["vinput_branch_current_a"].to_numpy()
    theoretical_current = sweep / (divider_config.r1_ohm + divider_config.r2_ohm)

    slope = float(np.polyfit(sweep, simulated_vout, 1)[0])
    metrics = calculate_error_metrics(simulated_vout, theoretical_vout)
    current_metrics = calculate_error_metrics(supplied_current, theoretical_current)
    kcl_residuals = (
        (dc.data["vin_v"].to_numpy() - simulated_vout) / divider_config.r1_ohm
        - simulated_vout / divider_config.r2_ohm
    )
    kvl_residuals = (
        dc.data["vin_v"].to_numpy() - supplied_current * divider_config.r1_ohm - simulated_vout
    )

    waveform = dc.data.copy()
    waveform["supply_current_a"] = supplied_current
    waveform["resistor_r1_current_a"] = (
        waveform["vin_v"] - waveform["out_v"]
    ) / divider_config.r1_ohm
    waveform["resistor_r2_current_a"] = waveform["out_v"] / divider_config.r2_ohm

    theory_frame = pd.DataFrame(
        {
            "sweep_v": sweep,
            "theoretical_out_v": theoretical_vout,
            "theoretical_current_a": theoretical_current,
            "data_source": DATA_SOURCE,
        }
    )
    relative = relative_error_percent(simulated_vout, theoretical_vout)
    comparison = pd.DataFrame(
        {
            "sweep_v": sweep,
            "simulated_out_v": simulated_vout,
            "theoretical_out_v": theoretical_vout,
            "absolute_error_v": simulated_vout - theoretical_vout,
            "relative_error_percent": relative,
            "simulated_supply_current_a": supplied_current,
            "theoretical_current_a": theoretical_current,
            "current_absolute_error_a": supplied_current - theoretical_current,
        }
    )

    _, dc_dir = store.create_run_dir(dc.run_id)
    figure = plot_dc_transfer(
        sweep,
        simulated_vout,
        theoretical_vout,
        dc_dir / "waveform.png",
        title="Voltage Divider DC Sweep (R1=R2=1 kOhm)",
    )
    error_figure = plot_error(
        sweep,
        simulated_vout - theoretical_vout,
        dc_dir / "error.png",
        title="Voltage Divider DC Error",
        y_label="Absolute error (V)",
    )

    dc_summary = {
        "status": "PASS",
        "points": dc.point_count,
        "slope_dvout_dvin": slope,
        "theoretical_slope": divider_transfer_slope(
            divider_config.r1_ohm, divider_config.r2_ohm
        ),
        "max_absolute_error_v": metrics["max_absolute_error"],
        "mae_v": metrics["mae"],
        "rmse_v": metrics["rmse"],
        "max_current_error_a": current_metrics["max_absolute_error"],
        "kcl_max_residual_a": float(np.max(np.abs(kcl_residuals))),
        "kvl_max_residual_v": float(np.max(np.abs(kvl_residuals))),
        "duration_ms": dc.duration_ms,
        "analysis_command": dc.metadata.get("analysis_command"),
        "zero_reference_count": metrics["zero_reference_count"],
    }
    store.save_result(
        dc,
        run_dir=dc_dir,
        analysis_parameters={
            "source": "Vinput",
            "start_v": dc_config.start_v,
            "stop_v": dc_config.stop_v,
            "step_v": dc_config.step_v,
        },
        config_snapshot=config.to_dict(),
        theory=theory_frame,
        comparison=comparison,
        waveform=waveform,
        summary=dc_summary,
        figures={"waveform.png": figure, "error.png": error_figure},
        log_lines=[
            f"DC sweep points={dc.point_count}",
            f"fitted slope={slope:.12g}",
        ],
    )

    checks = {
        "op_vout_within_1uV": abs(vout - theory_vout) < 1e-6,
        "op_current_within_1nA": abs(supply_current - theory_current) < 1e-9,
        "slope_within_1e-6": abs(slope - 0.5) < 1e-6,
        "dc_error_within_1uV": metrics["max_absolute_error"] < 1e-6,
        "kcl_within_1nA": float(np.max(np.abs(kcl_residuals))) < 1e-9,
        "kvl_within_1uV": float(np.max(np.abs(kvl_residuals))) < 1e-6,
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "op": op_summary,
        "dc": dc_summary,
        "run_dirs": {"operating_point": str(op_dir), "dc_sweep": str(dc_dir)},
        "data_source": {"waveform": "spice_simulation", "theory": DATA_SOURCE},
    }


def main() -> int:
    try:
        summary = analyze()
    except Exception as exc:  # noqa: BLE001 - 命令行必须如实上报失败
        ResultStore().save_failure(analysis_name="dc_analysis_demo", error=exc)
        print(f"FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
