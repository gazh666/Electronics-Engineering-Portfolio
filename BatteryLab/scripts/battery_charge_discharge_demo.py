"""Task 9：复现 PyBaMM 官方 Experiment 充放电流程。

流程：恒流放电 -> 静置 -> 恒流充电（至上限电压）-> 恒压充电（至 C/20）-> 静置。
本脚本只复现官方实验流程，不代表自主设计了 CC-CV 控制器。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pybamm

from analysis.battery_metrics import segment_statistics, summarize_measurement
from battery_models.pybamm_backend import BatterySimulationConfig, PyBaMMBackend
from simulations.models import cc_cv_experiment_steps
from storage.result_store import RunDirectory, json_safe
from visualization.plots import plot_dual_axis, plot_step_segments, plot_xy

ANNOTATION = "数据来源：PyBaMM Experiment 仿真（官方参数集，非硬件实测）"


def main() -> int:
    backend = PyBaMMBackend("SPM")
    model = backend.create_model("SPM")
    parameter_values = model.default_parameter_values
    upper_voltage = float(parameter_values["Upper voltage cut-off [V]"])
    lower_voltage = float(parameter_values["Lower voltage cut-off [V]"])
    capacity_ah = float(parameter_values["Nominal cell capacity [A.h]"])

    steps = cc_cv_experiment_steps(upper_voltage, c_rate="C/2")
    experiment = pybamm.Experiment(steps)
    config = BatterySimulationConfig(model_name="SPM", duration_s=0.0, initial_soc=0.9)
    result = backend.run(config, experiment=experiment)

    waveform = result["waveform"]
    solution = result["solution"]
    time_s = waveform["time_s"].to_numpy()
    voltage = waveform["voltage_v"].to_numpy()
    current = waveform["current_a"].to_numpy()

    summary = summarize_measurement(time_s, voltage, current, capacity_ah=capacity_ah, initial_soc=0.9)
    segments = segment_statistics(time_s, current, min_segment_s=5.0)
    waveform = waveform.copy()
    waveform["stage"] = "rest"
    for segment in segments:
        mask = (waveform["time_s"] >= segment["start_s"]) & (waveform["time_s"] <= segment["end_s"])
        waveform.loc[mask, "stage"] = segment["label"]

    cycle_summary = {}
    raw_summary = getattr(solution, "summary_variables", None)
    getter = getattr(raw_summary, "get_summary_variables", None)
    if callable(getter):
        try:
            values = getter()
        except Exception:  # noqa: BLE001 - 摘要变量缺失不影响主结果
            values = {}
        for key, value in dict(values).items():
            cycle_summary[str(key)] = json_safe(value)

    summary.update(
        {
            "data_source": "pybamm_simulation",
            "experiment_steps_requested": steps,
            "experiment_step_count": len(steps),
            "cycles_reported": len(solution.cycles),
            "upper_voltage_cutoff_v": upper_voltage,
            "lower_voltage_cutoff_v": lower_voltage,
            "nominal_capacity_ah": capacity_ah,
            "initial_soc": 0.9,
            "termination": result["metadata"]["termination"],
            "segments": segments,
            "cycle_summary_variables": cycle_summary,
            "note": "SOC 为模型真实状态变量，非电流积分近似。",
        }
    )

    run = RunDirectory("pybamm")
    run.write_metadata({"script": "scripts/battery_charge_discharge_demo.py", **result["metadata"]})
    run.write_config_snapshot(
        {
            "model_name": "SPM",
            "experiment_steps": steps,
            "initial_soc": 0.9,
            "parameter_set": None,
            "data_source": "pybamm_simulation",
        }
    )
    run.write_waveform(
        ["time_s", "voltage_v", "current_a", "soc", "temperature_c", "stage"],
        waveform.itertuples(index=False, name=None),
    )
    run.write_summary(summary)

    plot_xy(
        waveform["time_s"],
        waveform["current_a"],
        path=run.path / "current.png",
        xlabel="时间 (s)",
        ylabel="电流 (A)",
        title="PyBaMM Experiment 电流（放电为正，充电为负）",
        annotation=f"{ANNOTATION}；run={run.run_id}",
        color="#d62728",
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
        title="Experiment 端电压与 SOC",
        annotation=f"{ANNOTATION}；run={run.run_id}",
    )
    plot_step_segments(
        waveform,
        path=run.path / "stage_segments.png",
        x="time_s",
        y="voltage_v",
        label_column="stage",
        xlabel="时间 (s)",
        ylabel="端电压 (V)",
        title="按电流方向划分的实验阶段",
        annotation=f"{ANNOTATION}；run={run.run_id}",
    )
    run.log(f"实验完成: t_end={result['metadata']['time_end_s']:.3f}s, cycles={len(solution.cycles)}")
    run.flush_log()

    report = {
        "run_id": run.run_id,
        "run_path": str(run.path),
        "model": result["metadata"]["model_name"],
        "parameter_set": result["metadata"]["parameter_set_effective"],
        "solver": result["metadata"]["solver"],
        "experiment_steps": steps,
        "experiment_step_count": len(steps),
        "cycles_reported": len(solution.cycles),
        "total_simulated_time_s": result["metadata"]["time_end_s"],
        "termination": result["metadata"]["termination"],
        "initial_voltage_v": summary["voltage_start_v"],
        "final_voltage_v": summary["voltage_end_v"],
        "voltage_min_v": summary["voltage_min_v"],
        "voltage_max_v": summary["voltage_max_v"],
        "current_min_a": summary["current_min_a"],
        "current_max_a": summary["current_max_a"],
        "discharge_capacity_ah": summary["discharge_capacity_ah"],
        "charge_capacity_ah": summary["charge_capacity_ah"],
        "discharge_energy_wh": summary["discharge_energy_wh"],
        "charge_energy_wh": summary["charge_energy_wh"],
        "coulombic_efficiency_pct": summary["coulombic_efficiency_pct"],
        "energy_efficiency_pct": summary["energy_efficiency_pct"],
        "efficiency_note": "本次实验起止 SOC 不同（0.9→1.0），充放电容量/能量比值仅作参考，不代表循环库仑效率",
        "soc_start": summary.get("soc_start"),
        "soc_end": summary.get("soc_end"),
        "segments": segments,
        "waveform_csv": str(run.path / "waveform.csv"),
        "plots": [
            str(run.path / "current.png"),
            str(run.path / "voltage_soc.png"),
            str(run.path / "stage_segments.png"),
        ],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
