"""真实 ngspice 单体与 3S 电池组对照（Task 18/23）。

运行：conda run -n kaifa_battery python -m scripts.spice_battery_demo
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
from battery_models.ecm_solver import simulate_ecm
from battery_models.ocv_model import ConstantOcvModel
from battery_models.parameters import load_ecm_models
from battery_models.states import CellState
from simulations.load_profiles import single_pulse_profile
from simulations.spice_battery_runner import run_spice_pack, run_spice_single_cell
from storage.result_store import RunDirectory, write_csv, write_json
from visualization.plots import plot_multi_series

MODEL_NAMES = ("rint", "first_order_rc", "second_order_rc")


def nearest_value(frame: pd.DataFrame, column: str, target_s: float) -> float:
    index = int(np.argmin(np.abs(frame["time_s"].to_numpy(dtype=float) - target_s)))
    return float(frame[column].iloc[index])


def main() -> int:
    models = load_ecm_models()
    ocv = ConstantOcvModel(3.8)
    profile = single_pulse_profile()
    times, currents = profile.sample(0.1)
    combined = RunDirectory("spice_ecm")
    summary = {"script": "scripts/spice_battery_demo.py", "run_id": combined.run_id, "single_cell": {}, "pack": {}}
    comparison_rows = []

    for name in MODEL_NAMES:
        definition = models[name]
        spice = run_spice_single_cell(
            script="scripts/spice_battery_demo.py",
            model_name=name,
            parameters=definition.parameters,
            branches=definition.branches,
            ocv_v=3.8,
            profile=profile,
            step_s=0.05,
        )
        python_result = simulate_ecm(
            definition.parameters,
            definition.branches,
            CellState.initial(0.6, definition.order),
            times,
            currents,
            ocv,
            model_name=name,
        )
        metrics = compare_frames(
            spice["frame"],
            python_result.frame,
            reference_name="ngspice",
            exclude_times_s=(10.0, 70.0),
            exclude_window_s=0.15,
        )
        summary["single_cell"][name] = {
            "spice_run_id": spice["run_id"],
            "spice_netlist_path": spice["summary"]["netlist_path"],
            "spice_waveform_path": spice["summary"]["waveform_path"],
            "comparison": metrics,
            "spice_voltage_at_10p05s_v": nearest_value(spice["frame"], "terminal_voltage_v", 10.05),
            "spice_voltage_at_69p95s_v": nearest_value(spice["frame"], "terminal_voltage_v", 69.95),
        }
        for target in (0.0, 10.05, 40.0, 69.95, 70.05, 190.0):
            index = int(np.argmin(np.abs(spice["frame"]["time_s"].to_numpy(dtype=float) - target)))
            time_value = float(spice["frame"]["time_s"].iloc[index])
            spice_voltage = float(spice["frame"]["terminal_voltage_v"].iloc[index])
            python_voltage = float(np.interp(time_value, times, python_result.frame["terminal_voltage_v"].to_numpy(dtype=float)))
            comparison_rows.append([name, time_value, spice_voltage, python_voltage, python_voltage - spice_voltage])
        plot_multi_series(
            [
                ("ngspice", spice["frame"]["time_s"], spice["frame"]["terminal_voltage_v"]),
                ("Python ECM", python_result.frame["time_s"], python_result.frame["terminal_voltage_v"]),
            ],
            path=combined.path / "plots" / f"{name}_python_spice.png",
            xlabel="时间 (s)",
            ylabel="端电压 (V)",
            title=f"{name}: Python 与 ngspice 对照",
            annotation=f"阶跃转换区间已排除 | 来源: spice_simulation | Run: {combined.run_id}",
        )

    definition = models["second_order_rc"]
    spice_pack = run_spice_pack(
        script="scripts/spice_battery_demo.py",
        parameters=definition.parameters,
        branches=definition.branches,
        ocv_v=3.8,
        profile=profile,
        cells=3,
        step_s=0.05,
    )
    from battery_models.battery_pack import build_uniform_pack, simulate_series_pack

    python_pack = simulate_series_pack(build_uniform_pack(definition, ocv), times, currents)["pack_frame"]
    pack_metrics = compare_frames(
        spice_pack["frame"],
        python_pack,
        reference_column="pack_voltage_v",
        model_column="pack_voltage_v",
        reference_name="ngspice",
        exclude_times_s=(10.0, 70.0),
        exclude_window_s=0.15,
    )
    summary["pack"] = {
        "spice_run_id": spice_pack["run_id"],
        "topology": "3S1P",
        "spice_netlist_path": spice_pack["summary"]["netlist_path"],
        "spice_waveform_path": spice_pack["summary"]["waveform_path"],
        "comparison": pack_metrics,
        "max_voltage_sum_error_v": spice_pack["summary"]["max_voltage_sum_error_v"],
        "spice_pack_voltage_at_69p95s_v": nearest_value(spice_pack["frame"], "pack_voltage_v", 69.95),
    }
    plot_multi_series(
        [
            ("ngspice", spice_pack["frame"]["time_s"], spice_pack["frame"]["pack_voltage_v"]),
            ("Python ECM", python_pack["time_s"], python_pack["pack_voltage_v"]),
        ],
        path=combined.path / "plots" / "pack_python_spice.png",
        xlabel="时间 (s)",
        ylabel="电池组端电压 (V)",
        title="3S1P: Python 与 ngspice 对照",
        annotation=f"来源: spice_simulation | Run: {combined.run_id}",
    )
    write_csv(
        combined.path / "python_spice_comparison.csv",
        ["model", "time_s", "spice_v", "python_v", "error_v"],
        comparison_rows,
    )
    summary["comparison_table_path"] = str(combined.path / "python_spice_comparison.csv")
    summary["note"] = "SPICE 结果来自真实 ngspice 瞬态求解，Python 使用相同参数与相同电流定义。"
    write_json(combined.path / "summary.json", summary)
    combined.write_metadata({"script": "scripts/spice_battery_demo.py", "case": "spice_single_and_pack", "summary": summary})
    combined.flush_log()
    print(
        json.dumps(
            {
                "run_id": combined.run_id,
                "single_cell": {name: summary["single_cell"][name]["comparison"] for name in MODEL_NAMES},
                "pack": summary["pack"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
