"""ECM 运行器：把一次真实数值求解完整落盘（配置、电流、波形、事件、日志、图表）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

import pandas as pd
import yaml

from analysis.energy_balance import energy_balance
from analysis.pulse_response import analyze_pulse
from battery_models.ecm_solver import EcmResult, simulate_ecm
from battery_models.parameters import ECMModelDefinition
from battery_models.states import CellState
from simulations.load_profiles import ArrayProfile, LoadProfile
from storage.result_store import RunDirectory, utc_now, write_csv, write_json
from visualization.plots import plot_dual_axis, plot_series_frame


def write_frame(path: Path, frame: pd.DataFrame) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, float_format="%.12g", encoding="utf-8")
    return path


def _profile_arrays(profile: LoadProfile | ArrayProfile, output_step_s: float) -> tuple[Any, Any]:
    if isinstance(profile, LoadProfile):
        return profile.sample(output_step_s)
    return profile.time_s, profile.current_a


def _write_plots(run: RunDirectory, frame: pd.DataFrame, title: str, annotation: str) -> list[str]:
    plots_dir = run.path / "plots"
    paths: list[str] = []
    dual = plots_dir / "01_current_terminal_voltage.png"
    plot_dual_axis(
        frame,
        path=dual,
        x="time_s",
        y_left="terminal_voltage_v",
        y_right="current_a",
        xlabel="时间 (s)",
        left_label="端电压 (V)",
        right_label="电流 (A)",
        title=title,
        annotation=annotation,
    )
    paths.append(str(dual))
    polarization = plots_dir / "02_polarization_voltages.png"
    plot_series_frame(
        frame,
        path=polarization,
        x="time_s",
        y="polarization_1_v",
        xlabel="时间 (s)",
        ylabel="极化电压 (V)",
        title="第一 RC 支路极化电压",
        annotation=annotation,
    )
    paths.append(str(polarization))
    soc = plots_dir / "03_soc.png"
    plot_series_frame(
        frame,
        path=soc,
        x="time_s",
        y="soc",
        xlabel="时间 (s)",
        ylabel="SOC",
        title="SOC 变化",
        annotation=annotation,
    )
    paths.append(str(soc))
    return paths


def run_ecm_case(
    *,
    script: str,
    definition: ECMModelDefinition,
    ocv_model: Any,
    profile: LoadProfile | ArrayProfile,
    output_step_s: float = 0.1,
    initial_soc: float | None = None,
    initial_polarization_v: float = 0.0,
    extra_metadata: dict[str, Any] | None = None,
    make_plots: bool = True,
    run: RunDirectory | None = None,
) -> dict[str, Any]:
    """执行一次 ECM 仿真并保存全部原始证据。"""
    times, currents = _profile_arrays(profile, output_step_s)
    soc = float(initial_soc if initial_soc is not None else profile.metadata().get("initial_soc", 0.6))
    initial_state = CellState.initial(soc, definition.order, initial_polarization_v)
    run = run or RunDirectory("ecm")
    run.log(f"开始 ECM 仿真: model={definition.name} profile={profile.name} points={len(times)}")

    result: EcmResult = simulate_ecm(
        definition.parameters,
        definition.branches,
        initial_state,
        times,
        currents,
        ocv_model,
        model_name=definition.name,
        output_step_s=output_step_s,
        data_source=str(profile.metadata().get("data_source", "custom_ecm_simulation")),
        extra_metadata=extra_metadata,
    )

    config_payload = {
        "script": script,
        "generated_at": utc_now(),
        "model": definition.describe(),
        "ocv": ocv_model.metadata(),
        "profile": profile.metadata(),
        "initial_state": {
            "soc": initial_state.soc,
            "polarization_voltages_v": list(initial_state.polarization_voltages_v),
        },
        "output_step_s": output_step_s,
        "solver": result.metadata.get("solver_method"),
    }
    (run.path / "config_snapshot.yaml").write_text(
        yaml.safe_dump(config_payload, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    write_frame(run.path / "current_profile.csv", pd.DataFrame({"time_s": times, "current_a": currents}))
    write_frame(run.path / "waveform.csv", result.frame)
    write_csv(
        run.path / "event_log.csv",
        ["event_type", "time_s", "current_before_a", "current_after_a", "delta_current_a", "reason", "soc", "terminal_voltage_v"],
        [
            [
                event.get("event_type"),
                event.get("time_s"),
                event.get("current_before_a"),
                event.get("current_after_a"),
                event.get("delta_current_a"),
                event.get("reason"),
                event.get("soc"),
                event.get("terminal_voltage_v"),
            ]
            for event in result.events
        ],
    )
    summary = result.summary()
    summary["profile"] = profile.name
    summary["data_source"] = result.metadata.get("data_source")
    summary["parameter_source"] = result.metadata.get("parameter_source")
    balance = energy_balance(result.frame, definition.parameters, definition.branches)
    summary["energy_balance_status"] = balance["status"]
    summary["energy_balance_relative_residual"] = balance["relative_residual"]
    write_json(run.path / "energy_balance.json", balance)
    write_json(run.path / "summary.json", summary)
    run.write_metadata({"script": script, **config_payload, "summary": summary})
    paths = []
    if make_plots:
        annotation = (
            f"模型: {definition.name} | 工况: {profile.name} | 范围: 0-{result.frame['time_s'].iloc[-1]:.1f}s\n"
            f"来源: custom_ecm_simulation | Run: {run.run_id} | 参数来源: {definition.parameter_source}"
        )
        paths = _write_plots(run, result.frame, f"{definition.name} ECM 响应", annotation)
    run.log(f"仿真完成: 终止={result.metadata.get('termination')} 点数={len(result.frame)}")
    run.flush_log()
    return {
        "run_id": run.run_id,
        "run_path": str(run.path),
        "summary": summary,
        "result": result,
        "plots": paths,
        "waveform_path": str(run.path / "waveform.csv"),
        "config_path": str(run.path / "config_snapshot.yaml"),
        "event_log_path": str(run.path / "event_log.csv"),
    }


def analyze_run_pulse(
    frame: pd.DataFrame,
    *,
    step_time_s: float,
    release_time_s: float,
    tolerance_v: float = 0.001,
    observation_window_s: float = 60.0,
) -> dict[str, Any]:
    """对一次过跑的波形执行脉冲指标提取。"""
    return analyze_pulse(
        frame,
        step_time_s=step_time_s,
        release_time_s=release_time_s,
        tolerance_v=tolerance_v,
        observation_window_s=observation_window_s,
    )
