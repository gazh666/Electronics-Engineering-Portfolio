"""3S1P 一致电芯基准实验与真实 ngspice 三串对照（Task 22/23）。

运行：conda run -n kaifa_battery python -m scripts.battery_pack_demo
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd

from analysis.model_comparison import compare_frames
from analysis.pack_consistency import consistency_metrics
from battery_models.battery_pack import build_uniform_pack, simulate_series_pack
from battery_models.ocv_model import ConstantOcvModel
from battery_models.parameters import load_ecm_models
from simulations.load_profiles import single_pulse_profile
from simulations.spice_battery_runner import run_spice_pack
from storage.result_store import RunDirectory, write_csv, write_json
from visualization.plots import plot_multi_series, plot_series_frame


def main() -> int:
    definition = load_ecm_models()["second_order_rc"]
    ocv = ConstantOcvModel(3.8)
    profile = single_pulse_profile()
    times, currents = profile.sample(0.1)
    pack = build_uniform_pack(definition, ocv, count=3, initial_soc=0.6)
    result = simulate_series_pack(pack, times, currents)
    pack_frame: pd.DataFrame = result["pack_frame"]
    cell_frame: pd.DataFrame = result["cell_frame"]
    metrics = consistency_metrics(pack_frame, cell_frame)

    run = RunDirectory("battery_pack")
    pack_frame.to_csv(run.path / "pack_waveform.csv", index=False, float_format="%.12g", encoding="utf-8")
    cell_frame.to_csv(run.path / "cell_waveforms.csv", index=False, float_format="%.12g", encoding="utf-8")
    write_json(run.path / "cell_parameters.json", {"cells": result["metadata"]["cells"]})
    write_json(run.path / "consistency_metrics.json", metrics)
    write_csv(
        run.path / "event_log.csv",
        ["event_type", "time_s", "current_before_a", "current_after_a", "reason", "cell_id"],
        [
            [
                event.get("event_type"),
                event.get("time_s"),
                event.get("current_before_a"),
                event.get("current_after_a"),
                event.get("reason"),
                event.get("cell_id"),
            ]
            for event in result["events"]
        ],
    )
    cell_pivot = cell_frame.pivot_table(index="time_s", columns="cell_id", values="terminal_voltage_v")
    plot_multi_series(
        [(cell_id, cell_pivot.index, cell_pivot[cell_id]) for cell_id in cell_pivot.columns],
        path=run.path / "plots" / "cell_voltages.png",
        xlabel="时间 (s)",
        ylabel="单体端电压 (V)",
        title="3S 一致电芯单体端电压",
        annotation=f"2A 60s 脉冲 | 来源: custom_ecm_simulation | Run: {run.run_id}",
    )
    plot_series_frame(
        pack_frame,
        path=run.path / "plots" / "pack_voltage.png",
        x="time_s",
        y="pack_voltage_v",
        xlabel="时间 (s)",
        ylabel="电池组端电压 (V)",
        title="3S1P 电池组端电压",
        annotation=f"理论 11.4V -> 11.22V -> 11.0491V | Run: {run.run_id}",
    )
    plot_series_frame(
        pack_frame,
        path=run.path / "plots" / "delta_cell_voltage.png",
        x="time_s",
        y="delta_cell_voltage_v",
        xlabel="时间 (s)",
        ylabel="最大单体压差 (V)",
        title="一致电芯最大单体压差",
        annotation=f"一致电芯理论压差 0V | Run: {run.run_id}",
    )

    spice = run_spice_pack(
        script="scripts/battery_pack_demo.py",
        parameters=definition.parameters,
        branches=definition.branches,
        ocv_v=3.8,
        profile=profile,
        cells=3,
        step_s=0.05,
    )
    comparison = compare_frames(
        spice["frame"],
        pack_frame,
        reference_column="pack_voltage_v",
        model_column="pack_voltage_v",
        reference_name="ngspice",
        exclude_times_s=(10.0, 70.0),
        exclude_window_s=0.15,
    )

    from simulations.power_delivery import simulate_constant_power, simulate_constant_resistance

    power_summary = {}
    for load_type, simulate, load_value in (
        ("constant_resistance", simulate_constant_resistance, 5.7),
        ("constant_power", simulate_constant_power, 10.0 / 0.9),
    ):
        coarse = simulate(build_uniform_pack(definition, ocv), load_value, duration_s=1800.0, dt_s=0.1)
        fine = simulate(build_uniform_pack(definition, ocv), load_value, duration_s=1800.0, dt_s=0.05)
        coarse_frame = coarse["frame"]
        fine_frame = fine["frame"]
        aligned_voltage = np.interp(
            coarse_frame["time_s"].to_numpy(dtype=float),
            fine_frame["time_s"].to_numpy(dtype=float),
            fine_frame["pack_voltage_v"].to_numpy(dtype=float),
        )
        aligned_current = np.interp(
            coarse_frame["time_s"].to_numpy(dtype=float),
            fine_frame["time_s"].to_numpy(dtype=float),
            fine_frame["current_a"].to_numpy(dtype=float),
        )
        refinement_voltage = float(np.max(np.abs(aligned_voltage - coarse_frame["pack_voltage_v"].to_numpy(dtype=float))))
        refinement_current = float(np.max(np.abs(aligned_current - coarse_frame["current_a"].to_numpy(dtype=float))))
        coarse_frame.to_csv(
            run.path / f"power_delivery_{load_type}.csv", index=False, float_format="%.12g", encoding="utf-8"
        )
        power_summary[load_type] = {
            "load_value": load_value,
            "load_unit": "ohm" if load_type == "constant_resistance" else "W",
            "duration_s": 1800.0,
            "points": int(len(coarse_frame)),
            "initial_current_a": float(coarse_frame["current_a"].iloc[0]),
            "final_current_a": float(coarse_frame["current_a"].iloc[-1]),
            "initial_pack_voltage_v": float(coarse_frame["pack_voltage_v"].iloc[0]),
            "final_pack_voltage_v": float(coarse_frame["pack_voltage_v"].iloc[-1]),
            "mean_power_w": float(coarse_frame["pack_power_w"].mean()),
            "termination": coarse["metadata"]["termination"],
            "termination_reason": coarse["metadata"]["termination_reason"],
            "step_refinement_max_voltage_diff_v": refinement_voltage,
            "step_refinement_max_current_diff_a": refinement_current,
            "data_source": coarse["metadata"]["data_source"],
            "assumption": coarse["metadata"]["assumption"],
        }
    write_json(run.path / "power_delivery_summary.json", power_summary)
    summary = {
        "script": "scripts/battery_pack_demo.py",
        "run_id": run.run_id,
        "spice_run_id": spice["run_id"],
        "topology": "3S1P",
        "data_source": "custom_ecm_simulation",
        "pack_voltage_open_circuit_v": float(pack_frame["pack_voltage_v"].iloc[0]),
        "pack_voltage_at_step_v": float(pack_frame.loc[pack_frame["time_s"] == 10.0, "pack_voltage_v"].iloc[0]),
        "pack_voltage_before_release_v": float(pack_frame.loc[pack_frame["time_s"] < 70.0, "pack_voltage_v"].iloc[-1]),
        "total_r0_ohm": result["metadata"]["total_r0_ohm"],
        "consistency": metrics,
        "spice_comparison": comparison,
        "power_delivery": power_summary,
        "spice_netlist_path": spice["summary"]["netlist_path"],
        "spice_waveform_path": spice["summary"]["waveform_path"],
        "pack_waveform_path": str(run.path / "pack_waveform.csv"),
        "cell_waveform_path": str(run.path / "cell_waveforms.csv"),
        "metadata": result["metadata"],
    }
    write_json(run.path / "summary.json", summary)
    run.write_metadata({"script": "scripts/battery_pack_demo.py", "case": "uniform_3s1p", "summary": summary})
    run.log("3S1P 基准实验与 ngspice 对照完成")
    run.flush_log()
    print(json.dumps({key: summary[key] for key in ("run_id", "spice_run_id", "pack_voltage_open_circuit_v", "pack_voltage_at_step_v", "pack_voltage_before_release_v", "consistency", "spice_comparison")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
