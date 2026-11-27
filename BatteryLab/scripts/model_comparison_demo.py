"""多模型动态工况对照、PyBaMM 交叉验证与 CALCE 电流重放（Task 14/18/26）。

运行：conda run -n kaifa_battery python -m scripts.model_comparison_demo
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

from analysis.energy_balance import energy_balance
from analysis.model_comparison import align_series, compare_frames, error_metrics
from battery_models.ecm_solver import EcmResult, simulate_ecm
from battery_models.ocv_model import ConstantOcvModel, TableOcvModel, load_ocv_reference
from battery_models.parameters import load_ecm_models, load_yaml
from battery_models.states import CellState
from simulations.load_profiles import LoadProfile, piecewise_profile, profile_from_frame, single_pulse_profile
from storage.result_store import RunDirectory, write_csv, write_json
from visualization.plots import plot_multi_series

MODEL_NAMES = ("rint", "first_order_rc", "second_order_rc")


def run_case(models, ocv, profile: LoadProfile, *, stop_on_limits: bool = True) -> dict[str, EcmResult]:
    times, currents = profile.sample(0.1)
    results = {}
    for name in MODEL_NAMES:
        definition = models[name]
        results[name] = simulate_ecm(
            definition.parameters,
            definition.branches,
            CellState.initial(0.6, definition.order),
            times,
            currents,
            ocv,
            model_name=name,
            output_step_s=0.1,
            stop_on_limits=stop_on_limits,
            data_source="custom_ecm_simulation",
        )
    return results


def main() -> int:
    models = load_ecm_models()
    table_ocv = load_ocv_reference()
    config = load_yaml(PROJECT_ROOT / "configs" / "stage2_cases.yaml")
    run = RunDirectory("stage2")
    summary: dict = {"script": "scripts/model_comparison_demo.py", "run_id": run.run_id, "cases": {}, "pybamm": {}, "calce": {}}
    rows = []
    first_result = None
    second_result = None

    for case_id, case in config["dynamic_cases"].items():
        profile = piecewise_profile(
            case["segments"],
            name=case_id,
            description=str(case.get("description", "")),
        )
        results = run_case(models, table_ocv, profile)
        case_rows = {}
        for name in MODEL_NAMES:
            definition = models[name]
            frame = results[name].frame
            balance = energy_balance(frame, definition.parameters, definition.branches)
            case_rows[name] = {
                "min_voltage_v": float(frame["terminal_voltage_v"].min()),
                "max_voltage_v": float(frame["terminal_voltage_v"].max()),
                "start_voltage_v": float(frame["terminal_voltage_v"].iloc[0]),
                "end_voltage_v": float(frame["terminal_voltage_v"].iloc[-1]),
                "soc_start": float(frame["soc"].iloc[0]),
                "soc_end": float(frame["soc"].iloc[-1]),
                "capacity_throughput_ah": float(frame["capacity_throughput_ah"].iloc[-1]),
                "terminal_energy_j": balance["terminal_energy_j"],
                "ohmic_energy_j": balance["ohmic_energy_j"],
                "polarization_energy_j": balance["polarization_energy_j"],
                "energy_balance_status": balance["status"],
                "relative_residual": balance["relative_residual"],
            }
            rows.append(
                [
                    case_id,
                    name,
                    case_rows[name]["min_voltage_v"],
                    case_rows[name]["max_voltage_v"],
                    case_rows[name]["soc_end"],
                    case_rows[name]["capacity_throughput_ah"],
                    case_rows[name]["terminal_energy_j"],
                    case_rows[name]["ohmic_energy_j"],
                    case_rows[name]["polarization_energy_j"],
                    case_rows[name]["energy_balance_status"],
                ]
            )
        differences = {}
        for name in ("rint", "first_order_rc"):
            alignment = align_series(
                results["second_order_rc"].frame["time_s"].to_numpy(),
                results["second_order_rc"].frame["terminal_voltage_v"].to_numpy(),
                results[name].frame["time_s"].to_numpy(),
                results[name].frame["terminal_voltage_v"].to_numpy(),
            )
            differences[f"second_minus_{name}_max_abs_v"] = float(np.max(np.abs(alignment[2] - alignment[1])))
        summary["cases"][case_id] = {
            "description": case.get("description", ""),
            "profile": profile.metadata(),
            "models": case_rows,
            "model_differences": differences,
        }
        if case_id == "C_2a_pulse":
            first_result = results["first_order_rc"]
            second_result = results["second_order_rc"]
        plot_multi_series(
            [(name, results[name].frame["time_s"], results[name].frame["terminal_voltage_v"]) for name in MODEL_NAMES],
            path=run.path / "plots" / f"{case_id}.png",
            xlabel="时间 (s)",
            ylabel="端电压 (V)",
            title=f"{case_id}: {case.get('description', '')}",
            annotation=f"OCV 查表教学曲线 | 来源: custom_ecm_simulation | Run: {run.run_id}",
        )

    write_csv(
        run.path / "model_comparison.csv",
        [
            "case_id",
            "model",
            "min_voltage_v",
            "max_voltage_v",
            "soc_end",
            "capacity_throughput_ah",
            "terminal_energy_j",
            "ohmic_energy_j",
            "polarization_energy_j",
            "energy_balance_status",
        ],
        rows,
    )

    from battery_models.pybamm_backend import run_thevenin_teaching_case

    pulse = single_pulse_profile()
    pulse_times, pulse_currents = pulse.sample(0.1)
    pybamm_result = run_thevenin_teaching_case(
        capacity_ah=2.0,
        r0_ohm=0.03,
        branches=[(0.02, 1000.0), (0.015, 4000.0)],
        ocv_v=3.8,
        initial_soc=0.6,
        schedule=[(10.0, 0.0), (60.0, 2.0), (120.0, 0.0)],
        output_time_s=pulse_times,
    )
    definition = models["second_order_rc"]
    python_pulse = simulate_ecm(
        definition.parameters,
        definition.branches,
        CellState.initial(0.6, 2),
        pulse_times,
        pulse_currents,
        ConstantOcvModel(3.8),
        model_name="second_order_rc",
    )
    renamed = pybamm_result["frame"].rename(columns={"voltage_v": "terminal_voltage_v"})
    pybamm_metrics = compare_frames(
        renamed,
        python_pulse.frame,
        reference_name="pybamm_thevenin",
        exclude_times_s=(10.0, 70.0),
        exclude_window_s=0.15,
    )
    summary["pybamm"] = {
        "metadata": pybamm_result["metadata"],
        "comparison": pybamm_metrics,
        "note": "PyBaMM 官方 Thevenin 模型仅作功能性交叉验证，不代表自主求解器。",
        "waveform_path": str(run.path / "pybamm_comparison.csv"),
    }
    write_csv(
        run.path / "pybamm_comparison.csv",
        ["time_s", "pybamm_voltage_v", "python_voltage_v", "error_v"],
        [
            [
                float(time_value),
                float(pybamm_voltage),
                float(python_voltage),
                float(python_voltage - pybamm_voltage),
            ]
            for time_value, pybamm_voltage, python_voltage in zip(
                renamed["time_s"].to_numpy(),
                renamed["terminal_voltage_v"].to_numpy(),
                python_pulse.frame["terminal_voltage_v"].to_numpy(),
            )
        ],
    )
    plot_multi_series(
        [
            ("PyBaMM Thevenin", renamed["time_s"], renamed["terminal_voltage_v"]),
            ("BatteryLab ECM", python_pulse.frame["time_s"], python_pulse.frame["terminal_voltage_v"]),
        ],
        path=run.path / "plots" / "pybamm_comparison.png",
        xlabel="时间 (s)",
        ylabel="端电压 (V)",
        title="PyBaMM Thevenin 与自研 ECM 交叉验证",
        annotation=f"params: educational_assumption | Run: {run.run_id}",
    )

    candidates = sorted(
        PROJECT_ROOT.glob("results/calce/run_*/processed/*_dst.csv.gz"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if candidates:
        dataset_path = candidates[0]
        frame = pd.read_csv(dataset_path)
        start = float(frame["time_s"].iloc[0])
        segment = frame[frame["time_s"] <= start + 1500.0]
        profile = profile_from_frame(segment, name="calce_dst_replay", max_gap_s=15.0, max_points=1200)
        replay_frames = {}
        for name in ("rint", "second_order_rc"):
            definition = models[name]
            replay_frames[name] = simulate_ecm(
                definition.parameters,
                definition.branches,
                CellState.initial(0.6, definition.order),
                profile.time_s,
                profile.current_a,
                table_ocv,
                model_name=name,
                stop_on_limits=False,
                data_source="public_experimental_data",
            )
        measured = np.interp(
            profile.time_s,
            frame["time_s"].to_numpy(dtype=float),
            frame["voltage_v"].to_numpy(dtype=float),
        )
        summary["calce"] = {
            "dataset_path": str(dataset_path),
            "segment_start_s": float(profile.time_s[0]),
            "segment_end_s": float(profile.time_s[-1]),
            "points": int(profile.time_s.size),
            "notes": profile.notes,
            "status": "UNCALIBRATED_BASELINE",
            "models": {},
        }
        for name, result in replay_frames.items():
            metrics = error_metrics(measured, result.frame["terminal_voltage_v"].to_numpy(), reference_name="calce_measured")
            summary["calce"]["models"][name] = metrics
        write_csv(
            run.path / "calce_replay_comparison.csv",
            ["time_s", "measured_voltage_v", "rint_voltage_v", "second_order_voltage_v", "current_a"],
            [
                [
                    float(time_value),
                    float(measured[index]),
                    float(replay_frames["rint"].frame["terminal_voltage_v"].iloc[index]),
                    float(replay_frames["second_order_rc"].frame["terminal_voltage_v"].iloc[index]),
                    float(profile.current_a[index]),
                ]
                for index, time_value in enumerate(profile.time_s)
            ],
        )
        plot_multi_series(
            [
                ("CALCE 实测", profile.time_s, measured),
                ("Rint", profile.time_s, replay_frames["rint"].frame["terminal_voltage_v"].to_numpy()),
                ("二阶 RC", profile.time_s, replay_frames["second_order_rc"].frame["terminal_voltage_v"].to_numpy()),
            ],
            path=run.path / "plots" / "calce_replay.png",
            xlabel="时间 (s)",
            ylabel="端电压 (V)",
            title="CALCE DST 电流重放（未辨识参数基线）",
            annotation=f"教学 SOC0 与参数 | 来源: public_experimental_data | Run: {run.run_id}",
        )
        summary["calce"]["comparison_path"] = str(run.path / "calce_replay_comparison.csv")
    else:
        summary["calce"] = {"status": "NOT_VERIFIED", "reason": "未找到 CALCE DST 处理数据"}

    summary["note"] = "动态工况差异反映模型结构差异；CALCE 重放为未辨识参数基线，不代表标定后精度。"
    write_json(run.path / "summary.json", summary)
    write_json(run.path / "pybamm_comparison.json", summary["pybamm"])
    write_json(run.path / "calce_replay_summary.json", summary["calce"])
    run.write_metadata({"script": "scripts/model_comparison_demo.py", "case": "dynamic_and_external", "summary": summary})
    run.flush_log()
    print(
        json.dumps(
            {
                "run_id": run.run_id,
                "cases": {case_id: {name: summary["cases"][case_id]["models"][name]["end_voltage_v"] for name in MODEL_NAMES} for case_id in summary["cases"]},
                "pybamm": pybamm_metrics,
                "calce": summary["calce"].get("models", summary["calce"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
