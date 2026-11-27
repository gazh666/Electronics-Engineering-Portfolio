"""联合 SPICE 运行器：通过只读桥接在 kaifa_power 环境执行真实开关级仿真。"""

from __future__ import annotations

import csv
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from battery_models.parameters import PROJECT_ROOT
from circuits.integrated_protection import protection_control_points
from integration.battery_port_adapter import BatteryPort, cell_ecm_parameters, load_system_config
from integration.environment_adapter import run_python_script

BRIDGE = PROJECT_ROOT / "integration" / "powerlab_bridge.py"
POWERLAB_ROOT = Path("PowerLab")
RESULTS_ROOT = PROJECT_ROOT / "results" / "system_spice"


def new_run_directory(prefix: str) -> tuple[str, Path]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = f"{prefix}_{stamp}_{uuid.uuid4().hex[:6]}"
    path = RESULTS_ROOT / run_id
    path.mkdir(parents=True, exist_ok=False)
    (path / "run_id.txt").write_text(run_id, encoding="utf-8")
    return run_id, path


def load_waveform(path: str | Path) -> dict[str, list[float]]:
    target = Path(path)
    with target.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        columns: dict[str, list[float]] = {name: [] for name in reader.fieldnames or []}
        for row in reader:
            for name, value in row.items():
                columns[name].append(float(value))
    return columns


def run_integrated_case(
    port: BatteryPort,
    *,
    name: str,
    run_directory: str | Path,
    end_time_s: float = 0.004,
    step_time_s: float = 2.5e-8,
    fallback_steps_s: Sequence[float] = (5e-8, 1e-7),
    fault_time_s: float | None = None,
    load_resistance_ohm: float | None = None,
    inductance_h: float | None = None,
    capacitance_f: float | None = None,
    inductor_dcr_ohm: float | None = None,
    capacitor_esr_ohm: float | None = None,
    kp: float | None = None,
    ki: float | None = None,
    timeout_s: float = 900,
) -> dict[str, Any]:
    directory = Path(run_directory)
    directory.mkdir(parents=True, exist_ok=True)
    config = load_system_config()
    baseline = config["discharge_converter"]["baseline"]
    controller = config["discharge_converter"]["controller"]
    ocv_sum = sum(cell["ocv_v"] for cell in cell_ecm_parameters(port))

    control_points = None
    if fault_time_s is not None:
        control_points = protection_control_points(fault_time_s, end_time_s)

    request = {
        "mode": "integrated",
        "name": name,
        "end_time_s": end_time_s,
        "step_time_s": step_time_s,
        "fallback_steps_s": list(fallback_steps_s),
        "steady_window_fraction": 0.25,
        "cells": cell_ecm_parameters(port),
        "path_resistance_ohm": float(config["protection"]["path_resistance_ohm"]),
        "input_capacitance_f": 100e-6,
        "input_capacitor_ic_v": ocv_sum - 0.3,
        "protection_control_points": control_points,
        "waveform_output": str((directory / "waveform.csv").resolve()),
        "inductance_h": inductance_h if inductance_h is not None else float(baseline["inductance_h"]),
        "capacitance_f": capacitance_f if capacitance_f is not None else float(baseline["capacitance_f"]),
        "inductor_dcr_ohm": inductor_dcr_ohm if inductor_dcr_ohm is not None else float(baseline["inductor_dcr_ohm"]),
        "capacitor_esr_ohm": capacitor_esr_ohm if capacitor_esr_ohm is not None else float(baseline["capacitor_esr_ohm"]),
        "kp": float(controller["kp"]) if kp is None else kp,
        "ki": float(controller["ki"]) if ki is None else ki,
        "load_resistance_ohm": load_resistance_ohm,
    }
    request_path = directory / "integrated_request.json"
    request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
    output_path = directory / "integrated_output.json"

    execution = run_python_script(
        "kaifa_power",
        BRIDGE,
        ["--project-root", str(POWERLAB_ROOT), "--request", str(request_path),
         "--output", str(output_path)],
        working_directory=PROJECT_ROOT,
        timeout_s=timeout_s,
    )
    payload = json.loads(output_path.read_text(encoding="utf-8")) if output_path.is_file() else None
    result = {
        "case": name,
        "run_id": directory.name,
        "bridge_execution": {
            "status": execution["status"],
            "returncode": execution["returncode"],
            "duration_s": execution["duration_s"],
            "stderr_tail": (execution.get("stderr") or "")[-2000:],
        },
        "request_path": str(request_path),
        "integrated": (payload or {}).get("integrated"),
        "fault_time_s": fault_time_s,
    }
    (directory / "simulation_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return result


__all__ = ["RESULTS_ROOT", "load_waveform", "new_run_directory", "run_integrated_case"]
