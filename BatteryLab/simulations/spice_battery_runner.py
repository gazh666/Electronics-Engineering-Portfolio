"""SPICE 电池仿真落盘：网表、真实波形、求解日志与元数据。"""

from __future__ import annotations

from typing import Any, Sequence

import pandas as pd

from circuits.battery_ecm_circuit import build_and_run_single_cell, save_netlist
from circuits.battery_pack_circuit import build_and_run_pack
from battery_models.parameters import CellParameters, RCBranch
from simulations.load_profiles import LoadProfile
from storage.result_store import RunDirectory, utc_now, write_json


def _write_frame(path, frame: pd.DataFrame) -> None:
    frame.to_csv(path, index=False, float_format="%.12g", encoding="utf-8")


def run_spice_single_cell(
    *,
    script: str,
    model_name: str,
    parameters: CellParameters,
    branches: Sequence[RCBranch],
    ocv_v: float,
    profile: LoadProfile,
    step_s: float = 0.05,
    transition_s: float = 0.001,
) -> dict[str, Any]:
    run = RunDirectory("spice_ecm")
    run.log(f"构建真实 ngspice 单体网表: model={model_name} step={step_s}s")
    circuit, payload = build_and_run_single_cell(
        model_name,
        parameters,
        branches,
        ocv_v,
        profile,
        step_s=step_s,
        transition_s=transition_s,
    )
    netlist_path = save_netlist(circuit, run.path / "circuit.cir")
    frame = pd.DataFrame(payload["waveform"])
    frame["model"] = model_name
    _write_frame(run.path / "waveform.csv", frame)

    summary = {
        "kind": "single_cell",
        "model": model_name,
        "status": "PASS",
        "data_source": "spice_simulation",
        "solver": "ngspice transient (PySpice)",
        "points": int(len(frame)),
        "time_start_s": float(frame["time_s"].iloc[0]),
        "time_end_s": float(frame["time_s"].iloc[-1]),
        "terminal_voltage_start_v": float(frame["terminal_voltage_v"].iloc[0]),
        "terminal_voltage_end_v": float(frame["terminal_voltage_v"].iloc[-1]),
        "terminal_voltage_min_v": float(frame["terminal_voltage_v"].min()),
        "terminal_voltage_max_v": float(frame["terminal_voltage_v"].max()),
        "step_s": step_s,
        "transition_s": transition_s,
        "nodes": payload["nodes"],
        "netlist_path": str(netlist_path),
        "waveform_path": str(run.path / "waveform.csv"),
        "parameter_source": parameters.parameter_source,
        "profile": profile.name,
        "pwl_points": payload["pwl_points"],
    }
    write_json(run.path / "summary.json", summary)
    run.write_metadata({"script": script, "generated_at": utc_now(), **summary})
    run.log(f"ngspice 求解成功: 点数={len(frame)} 终止电压={frame['terminal_voltage_v'].iloc[-1]:.9f}V")
    run.flush_log()
    return {"run_id": run.run_id, "run_path": str(run.path), "frame": frame, "summary": summary}


def run_spice_pack(
    *,
    script: str,
    parameters: CellParameters,
    branches: Sequence[RCBranch],
    ocv_v: float,
    profile: LoadProfile,
    cells: int = 3,
    step_s: float = 0.05,
    transition_s: float = 0.001,
) -> dict[str, Any]:
    run = RunDirectory("spice_ecm")
    run.log(f"构建真实 ngspice {cells}S 电池组网表: step={step_s}s")
    circuit, payload = build_and_run_pack(
        branches,
        parameters.r0_ohm,
        ocv_v,
        profile,
        cells=cells,
        step_s=step_s,
        transition_s=transition_s,
    )
    netlist_path = save_netlist(circuit, run.path / "circuit.cir")
    frame = pd.DataFrame(payload["waveform"])
    _write_frame(run.path / "pack_waveform.csv", frame)

    summary = {
        "kind": "series_pack",
        "model": "second_order_rc",
        "topology": f"{cells}S1P",
        "status": "PASS",
        "data_source": "spice_simulation",
        "solver": "ngspice transient (PySpice)",
        "points": int(len(frame)),
        "time_start_s": float(frame["time_s"].iloc[0]),
        "time_end_s": float(frame["time_s"].iloc[-1]),
        "pack_voltage_start_v": float(frame["pack_voltage_v"].iloc[0]),
        "pack_voltage_end_v": float(frame["pack_voltage_v"].iloc[-1]),
        "pack_voltage_min_v": float(frame["pack_voltage_v"].min()),
        "pack_voltage_max_v": float(frame["pack_voltage_v"].max()),
        "max_voltage_sum_error_v": float(
            (frame["pack_voltage_v"] - frame["sum_cell_voltage_v"]).abs().max()
        ),
        "step_s": step_s,
        "transition_s": transition_s,
        "netlist_path": str(netlist_path),
        "waveform_path": str(run.path / "pack_waveform.csv"),
        "parameter_source": parameters.parameter_source,
        "profile": profile.name,
        "pwl_points": payload["pwl_points"],
    }
    write_json(run.path / "summary.json", summary)
    run.write_metadata({"script": script, "generated_at": utc_now(), **summary})
    run.log(f"ngspice 电池组求解成功: 点数={len(frame)} 末端组电压={frame['pack_voltage_v'].iloc[-1]:.9f}V")
    run.flush_log()
    return {"run_id": run.run_id, "run_path": str(run.path), "frame": frame, "summary": summary}
