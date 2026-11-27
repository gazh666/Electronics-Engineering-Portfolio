"""三种模型统一 2A 脉冲对照实验（Task 12/14）。

同一 OCV、同一初始 SOC、同一电流工况，差异只反映模型结构。
运行：conda run -n kaifa_battery python -m scripts.battery_pulse_demo
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
from analysis.pulse_response import analyze_pulse
from battery_models.ocv_model import ConstantOcvModel
from battery_models.parameters import load_ecm_models
from simulations.ecm_runner import run_ecm_case
from simulations.load_profiles import single_pulse_profile
from storage.result_store import RunDirectory, write_csv, write_json
from visualization.plots import plot_multi_series

MODEL_NAMES = ("rint", "first_order_rc", "second_order_rc")
REFERENCE_TIMES = (9.9, 10.0, 69.9, 70.0, 190.0)


def analytic_series(definition, time_s: np.ndarray, *, ocv_v: float = 3.8, current_a: float = 2.0, start_s: float = 10.0, end_s: float = 70.0) -> np.ndarray:
    r0 = definition.parameters.r0_ohm
    branches = [(branch.resistance_ohm, branch.capacitance_f) for branch in definition.branches]
    result = np.empty_like(time_s, dtype=float)
    for index, value in enumerate(time_s):
        if value < start_s:
            result[index] = ocv_v
            continue
        total = 0.0
        if value < end_s:
            for resistance, capacitance in branches:
                tau = resistance * capacitance
                total += current_a * resistance * (1.0 - math.exp(-(value - start_s) / tau))
            result[index] = ocv_v - current_a * r0 - total
        else:
            for resistance, capacitance in branches:
                tau = resistance * capacitance
                end_value = current_a * resistance * (1.0 - math.exp(-(end_s - start_s) / tau))
                total += end_value * math.exp(-(value - end_s) / tau)
            result[index] = ocv_v - total
    return result


def main() -> int:
    models = load_ecm_models()
    ocv = ConstantOcvModel(3.8)
    profile = single_pulse_profile()
    cases = {}
    for name in MODEL_NAMES:
        definition = models[name]
        cases[name] = run_ecm_case(
            script="scripts/battery_pulse_demo.py",
            definition=definition,
            ocv_model=ocv,
            profile=profile,
            output_step_s=0.1,
        )

    combined = RunDirectory("ecm")
    comparison_rows = []
    theory_errors = {}
    pulse_metrics = {}
    for name in MODEL_NAMES:
        definition = models[name]
        frame = cases[name]["result"].frame
        times = frame["time_s"].to_numpy(dtype=float)
        theory = analytic_series(definition, times)
        errors = error_metrics(theory, frame["terminal_voltage_v"].to_numpy(dtype=float), reference_name="analytical_theory")
        theory_errors[name] = errors
        pulse_metrics[name] = analyze_pulse(frame, step_time_s=10.0, release_time_s=70.0, observation_window_s=120.0)
        for target in REFERENCE_TIMES:
            simulated = float(frame.loc[np.isclose(frame["time_s"], target), "terminal_voltage_v"].iloc[0])
            reference = float(analytic_series(definition, np.array([target]))[0])
            comparison_rows.append([name, target, reference, simulated, simulated - reference])

    write_csv(
        combined.path / "theory_comparison.csv",
        ["model", "time_s", "analytical_v", "simulated_v", "error_v"],
        comparison_rows,
    )
    plot_multi_series(
        [
            (name, cases[name]["result"].frame["time_s"], cases[name]["result"].frame["terminal_voltage_v"])
            for name in MODEL_NAMES
        ],
        path=combined.path / "plots" / "three_model_pulse.png",
        xlabel="时间 (s)",
        ylabel="端电压 (V)",
        title="Rint / 一阶 RC / 二阶 RC 脉冲响应对照",
        annotation=f"OCV=3.8V, 2A 60s | 来源: custom_ecm_simulation | Run: {combined.run_id}",
    )
    first = cases["first_order_rc"]["result"].frame
    second = cases["second_order_rc"]["result"].frame
    difference_at_end = float(
        second.loc[np.isclose(second["time_s"], 69.9), "terminal_voltage_v"].iloc[0]
        - first.loc[np.isclose(first["time_s"], 69.9), "terminal_voltage_v"].iloc[0]
    )
    summary = {
        "script": "scripts/battery_pulse_demo.py",
        "run_id": combined.run_id,
        "profile": profile.metadata(),
        "runs": {name: cases[name]["run_id"] for name in MODEL_NAMES},
        "theory_errors": theory_errors,
        "pulse_metrics": pulse_metrics,
        "model_voltage_difference_at_69p9s_v": difference_at_end,
        "note": "模型之间电压差异属于模型结构差异，不是实测准确率。",
        "waveforms": {name: cases[name]["waveform_path"] for name in MODEL_NAMES},
    }
    write_json(combined.path / "summary.json", summary)
    write_json(combined.path / "pulse_response_metrics.json", pulse_metrics)
    combined.write_metadata({"script": "scripts/battery_pulse_demo.py", "case": "three_model_pulse", "summary": summary})
    combined.log("三种模型统一脉冲对照完成")
    combined.flush_log()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
