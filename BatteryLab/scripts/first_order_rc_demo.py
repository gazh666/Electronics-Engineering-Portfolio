"""一阶 RC 模型演示：2A 脉冲、时间常数与解析对照。

运行：conda run -n kaifa_battery python -m scripts.first_order_rc_demo
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np

from analysis.model_comparison import error_metrics
from analysis.polarization_analysis import time_constant_checkpoints
from analysis.pulse_response import analyze_pulse
from battery_models.ocv_model import ConstantOcvModel
from battery_models.parameters import load_ecm_models
from simulations.ecm_runner import run_ecm_case
from simulations.load_profiles import single_pulse_profile
from storage.result_store import RunDirectory, write_json
from visualization.plots import plot_xy


def analytic_voltage(time_s: np.ndarray, *, ocv_v: float, r0: float, r1: float, c1: float, current_a: float, start_s: float, end_s: float) -> np.ndarray:
    tau = r1 * c1
    steady = current_a * r1
    voltages = np.empty_like(time_s, dtype=float)
    for index, value in enumerate(time_s):
        if value < start_s:
            voltages[index] = ocv_v
        elif value < end_s:
            voltages[index] = ocv_v - current_a * r0 - steady * (1.0 - math.exp(-(value - start_s) / tau))
        else:
            residual = steady * (1.0 - math.exp(-(end_s - start_s) / tau))
            voltages[index] = ocv_v - residual * math.exp(-(value - end_s) / tau)
    return voltages


def main() -> int:
    definition = load_ecm_models()["first_order_rc"]
    parameters = definition.parameters
    branch = definition.branches[0]
    ocv = ConstantOcvModel(3.8)
    profile = single_pulse_profile()
    run = RunDirectory("ecm")

    case = run_ecm_case(
        script="scripts/first_order_rc_demo.py",
        definition=definition,
        ocv_model=ocv,
        profile=profile,
        output_step_s=0.1,
        run=run,
    )
    frame = case["result"].frame
    times = frame["time_s"].to_numpy(dtype=float)
    theory = analytic_voltage(
        times,
        ocv_v=3.8,
        r0=parameters.r0_ohm,
        r1=branch.resistance_ohm,
        c1=branch.capacitance_f,
        current_a=2.0,
        start_s=10.0,
        end_s=70.0,
    )
    comparison = error_metrics(theory, frame["terminal_voltage_v"].to_numpy(dtype=float), reference_name="analytical_theory")
    metrics = analyze_pulse(frame, step_time_s=10.0, release_time_s=70.0, observation_window_s=120.0)
    checkpoints = time_constant_checkpoints(
        frame,
        pulse_start_s=10.0,
        pulse_end_s=70.0,
        tau_s=branch.time_constant_s,
        steady_voltage_v=2.0 * branch.resistance_ohm,
    )
    plot_xy(
        frame["time_s"],
        frame["polarization_1_v"],
        path=run.path / "plots" / "04_polarization_checkpoints.png",
        xlabel="时间 (s)",
        ylabel="第一极化电压 (V)",
        title="一阶 RC 极化建立与恢复",
        annotation=f"tau1=20s | 来源: custom_ecm_simulation | Run: {run.run_id}",
    )
    summary = {
        "script": "scripts/first_order_rc_demo.py",
        "run_id": run.run_id,
        "model": definition.describe(),
        "data_source": "custom_ecm_simulation",
        "theory_comparison": comparison,
        "pulse_metrics": metrics,
        "time_constant_checkpoints": checkpoints,
        "waveform_path": case["waveform_path"],
        "config_path": case["config_path"],
    }
    write_json(run.path / "summary.json", summary)
    run.write_metadata({"script": "scripts/first_order_rc_demo.py", "case": "first_order_pulse", "summary": summary})
    run.flush_log()
    print(json.dumps({"run_id": run.run_id, "run_path": str(run.path), "theory_error": comparison, "pulse_metrics": metrics}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
