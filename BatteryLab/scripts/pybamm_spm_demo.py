"""Task 6：复现 PyBaMM 官方 SPM 模型，并进行真实放电仿真。

输出真实初始/结束电压、实际放电时间、容量、能量、终止原因与波形文件。
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
from visualization.plots import plot_xy

ANNOTATION = "数据来源：PyBaMM 官方 SPM 仿真（非硬件实测）"


def load_config() -> dict:
    path = PROJECT_ROOT / "configs" / "simulation_config.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def main() -> int:
    config_yaml = load_config()
    duration = float(config_yaml["pybamm"]["spm_duration_s"])
    backend = PyBaMMBackend("SPM")
    config = BatterySimulationConfig(model_name="SPM", duration_s=duration)
    result = backend.run(config)

    waveform = result["waveform"]
    metadata = result["metadata"]
    parameter_values = result["simulation"].parameter_values
    capacity_ah = float(parameter_values["Nominal cell capacity [A.h]"])

    summary = summarize_measurement(
        waveform["time_s"].to_numpy(),
        waveform["voltage_v"].to_numpy(),
        waveform["current_a"].to_numpy(),
        capacity_ah=capacity_ah,
        initial_soc=1.0,
    )
    summary.update(
        {
            "data_source": "pybamm_simulation",
            "nominal_capacity_ah": capacity_ah,
            "upper_voltage_cutoff_v": float(parameter_values["Upper voltage cut-off [V]"]),
            "lower_voltage_cutoff_v": float(parameter_values["Lower voltage cut-off [V]"]),
            "termination": metadata["termination"],
            "reached_requested_duration": bool(abs(metadata["time_end_s"] - duration) < 1e-6),
            "voltage_deviation_from_cutoff_v": float(waveform["voltage_v"].iloc[-1] - parameter_values["Lower voltage cut-off [V]"]),
        }
    )

    run = RunDirectory("pybamm")
    run.write_metadata({"script": "scripts/pybamm_spm_demo.py", **metadata})
    run.write_config_snapshot(
        {
            "model_name": "SPM",
            "duration_s": duration,
            "parameter_set": None,
            "initial_soc": None,
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
        title=f"PyBaMM SPM 端电压（{metadata['parameter_set_effective']}）",
        annotation=f"{ANNOTATION}；run={run.run_id}",
    )
    plot_xy(
        waveform["time_s"],
        waveform["current_a"],
        path=run.path / "current.png",
        xlabel="时间 (s)",
        ylabel="电流 (A)",
        title="PyBaMM SPM 电流（放电为正）",
        annotation=f"{ANNOTATION}；run={run.run_id}",
        color="#d62728",
    )
    run.log(f"SPM 求解完成: t_end={metadata['time_end_s']:.3f}s, 终止={metadata['termination']}")
    run.flush_log()

    report = {
        "run_id": run.run_id,
        "run_path": str(run.path),
        "model": metadata["model_name"],
        "parameter_set": metadata["parameter_set_effective"],
        "solver": metadata["solver"],
        "duration_requested_s": duration,
        "actual_discharge_time_s": metadata["time_end_s"],
        "termination": metadata["termination"],
        "initial_voltage_v": summary["voltage_start_v"],
        "final_voltage_v": summary["voltage_end_v"],
        "discharge_capacity_ah": summary["discharge_capacity_ah"],
        "discharge_energy_wh": summary["discharge_energy_wh"],
        "capacity_ratio_to_nominal": summary["discharge_capacity_ah"] / capacity_ah,
        "points": summary["points"],
        "wall_time_s": metadata["wall_time_s"],
        "waveform_csv": str(run.path / "waveform.csv"),
        "plots": [str(run.path / "voltage.png"), str(run.path / "current.png")],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
