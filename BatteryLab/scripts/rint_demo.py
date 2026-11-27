"""Rint 模型演示：恒定 OCV 下电流扫描与 2A 脉冲实际响应。

运行：conda run -n kaifa_battery python -m scripts.rint_demo
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from analysis.pulse_response import analyze_pulse
from battery_models.ocv_model import ConstantOcvModel
from battery_models.parameters import load_ecm_models
from battery_models.rint import rint_benchmark_rows
from simulations.ecm_runner import run_ecm_case
from simulations.load_profiles import single_pulse_profile
from storage.result_store import RunDirectory, write_csv, write_json
from visualization.plots import plot_xy


def main() -> int:
    definition = load_ecm_models()["rint"]
    ocv = ConstantOcvModel(3.8)
    rows = rint_benchmark_rows(ocv_v=ocv.voltage_v, r0_ohm=definition.parameters.r0_ohm)

    run = RunDirectory("ecm")
    write_csv(
        run.path / "rint_sweep.csv",
        ["current_a", "ocv_v", "ohmic_drop_v", "terminal_voltage_v", "ohmic_loss_w", "mode"],
        [
            [
                row["current_a"],
                row["ocv_v"],
                row["ohmic_drop_v"],
                row["terminal_voltage_v"],
                row["ohmic_loss_w"],
                row["mode"],
            ]
            for row in rows
        ],
    )
    plot_xy(
        [row["current_a"] for row in rows],
        [row["terminal_voltage_v"] for row in rows],
        path=run.path / "plots" / "rint_voltage_vs_current.png",
        xlabel="负载电流 (A)",
        ylabel="端电压 (V)",
        title="Rint 端电压与负载电流关系",
        annotation=f"OCV=3.8V R0=30mΩ | 来源: analytical_theory/custom_ecm | Run: {run.run_id}",
    )
    plot_xy(
        [row["current_a"] for row in rows],
        [row["ohmic_loss_w"] for row in rows],
        path=run.path / "plots" / "rint_loss_vs_current.png",
        xlabel="负载电流 (A)",
        ylabel="欧姆损耗 (W)",
        title="Rint 内阻损耗与电流关系",
        annotation=f"P=I^2*R0 | 来源: analytical_theory/custom_ecm | Run: {run.run_id}",
    )

    profile = single_pulse_profile()
    case = run_ecm_case(
        script="scripts/rint_demo.py",
        definition=definition,
        ocv_model=ocv,
        profile=profile,
        output_step_s=0.1,
        run=run,
    )
    metrics = analyze_pulse(case["result"].frame, step_time_s=10.0, release_time_s=70.0, observation_window_s=120.0)
    summary = {
        "script": "scripts/rint_demo.py",
        "run_id": run.run_id,
        "model": definition.describe(),
        "data_source": "custom_ecm_simulation",
        "sweep_rows": rows,
        "pulse_metrics": metrics,
        "waveform_path": case["waveform_path"],
        "config_path": case["config_path"],
        "event_log_path": case["event_log_path"],
        "plots": case["plots"],
    }
    write_json(run.path / "summary.json", summary)
    run.write_metadata({"script": "scripts/rint_demo.py", "case": "rint_sweep_and_pulse", "summary": summary})
    run.flush_log()
    print(json.dumps({"run_id": run.run_id, "run_path": str(run.path), "sweep": rows, "pulse_metrics": metrics}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
