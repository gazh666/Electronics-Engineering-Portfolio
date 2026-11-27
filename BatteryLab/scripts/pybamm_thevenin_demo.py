"""Task 7：复现 PyBaMM 官方 Thevenin 等效电路模型。

默认参数集为官方教学示例（ECM_Example，100 Ah），本阶段不做真实电芯参数辨识。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import yaml

from analysis.battery_metrics import summarize_measurement
from battery_models.pybamm_backend import BatterySimulationConfig, PyBaMMBackend
from storage.result_store import RunDirectory
from visualization.plots import plot_dual_axis, plot_xy

ANNOTATION = "数据来源：PyBaMM Thevenin 仿真（官方教学参数集，非实测、非商业电芯辨识）"


def _first(solution, name: str) -> float | None:
    try:
        values = np.asarray(solution[name].entries, dtype=float).squeeze()
        return float(values.flat[0])
    except Exception:  # noqa: BLE001
        return None


def main() -> int:
    config_yaml = yaml.safe_load((PROJECT_ROOT / "configs" / "simulation_config.yaml").read_text(encoding="utf-8"))
    duration = float(config_yaml["pybamm"]["thevenin_duration_s"])

    backend = PyBaMMBackend("Thevenin")
    config = BatterySimulationConfig(model_name="Thevenin", duration_s=duration, output_points=400)
    result = backend.run(config)
    waveform = result["waveform"]
    solution = result["solution"]
    model = result["simulation"].model
    parameter_values = result["simulation"].parameter_values

    capacity_ah = float(parameter_values["Nominal cell capacity [A.h]"])
    summary = summarize_measurement(
        waveform["time_s"].to_numpy(),
        waveform["voltage_v"].to_numpy(),
        waveform["current_a"].to_numpy(),
        capacity_ah=capacity_ah,
        initial_soc=float(parameter_values["Initial SoC"]),
    )
    summary.update(
        {
            "data_source": "pybamm_simulation",
            "initial_soc_set": float(parameter_values["Initial SoC"]),
            "cell_capacity_ah": capacity_ah,
            "rc_elements": int(model.options["number of rc elements"]),
            "ocv_function": repr(parameter_values["Open-circuit voltage [V]"]),
            "upper_voltage_cutoff_v": float(parameter_values["Upper voltage cut-off [V]"]),
            "lower_voltage_cutoff_v": float(parameter_values["Lower voltage cut-off [V]"]),
            "r0_ohm_at_start": _first(solution, "R0 [Ohm]"),
            "r1_ohm_at_start": _first(solution, "R1 [Ohm]"),
            "c1_f_at_start": _first(solution, "C1 [F]"),
            "tau1_s_at_start": _first(solution, "tau1 [s]"),
            "ocv_at_start_v": _first(solution, "Open-circuit voltage [V]"),
            "termination": result["metadata"]["termination"],
        }
    )

    run = RunDirectory("pybamm")
    run.write_metadata(
        {
            "script": "scripts/pybamm_thevenin_demo.py",
            **result["metadata"],
            "note": "官方教学参数集 ECM_Example（100 Ah），不代表真实电芯辨识结果",
        }
    )
    run.write_config_snapshot(
        {
            "model_name": "Thevenin",
            "duration_s": duration,
            "parameter_set": None,
            "initial_soc": None,
            "output_points": 400,
            "data_source": "pybamm_simulation",
        }
    )
    run.write_waveform(["time_s", "voltage_v", "current_a", "soc", "temperature_c"], waveform.itertuples(index=False, name=None))
    run.write_summary(summary)
    plot_xy(
        waveform["time_s"],
        waveform["voltage_v"],
        path=run.path / "voltage.png",
        xlabel="时间 (s)",
        ylabel="端电压 (V)",
        title="PyBaMM Thevenin 端电压（ECM_Example）",
        annotation=f"{ANNOTATION}；run={run.run_id}",
    )
    plot_dual_axis(
        waveform,
        path=run.path / "voltage_soc.png",
        x="time_s",
        y_left="voltage_v",
        y_right="soc",
        xlabel="时间 (s)",
        left_label="端电压 (V)",
        right_label="SOC",
        title="Thevenin 端电压与 SOC",
        annotation=f"{ANNOTATION}；run={run.run_id}",
    )
    run.log(f"Thevenin 求解完成: t_end={result['metadata']['time_end_s']:.3f}s")
    run.flush_log()

    report = {
        "run_id": run.run_id,
        "run_path": str(run.path),
        "model": result["metadata"]["model_name"],
        "parameter_set": result["metadata"]["parameter_set_effective"],
        "solver": result["metadata"]["solver"],
        "rc_elements": summary["rc_elements"],
        "cell_capacity_ah": capacity_ah,
        "initial_soc": summary["initial_soc_set"],
        "duration_requested_s": duration,
        "actual_end_time_s": result["metadata"]["time_end_s"],
        "termination": summary["termination"],
        "initial_voltage_v": summary["voltage_start_v"],
        "final_voltage_v": summary["voltage_end_v"],
        "soc_start": summary.get("soc_start"),
        "soc_end": summary.get("soc_end"),
        "discharge_capacity_ah": summary["discharge_capacity_ah"],
        "discharge_energy_wh": summary["discharge_energy_wh"],
        "r0_ohm_at_start": summary["r0_ohm_at_start"],
        "r1_ohm_at_start": summary["r1_ohm_at_start"],
        "c1_f_at_start": summary["c1_f_at_start"],
        "tau1_s_at_start": summary["tau1_s_at_start"],
        "waveform_csv": str(run.path / "waveform.csv"),
        "plots": [str(run.path / "voltage.png"), str(run.path / "voltage_soc.png")],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
