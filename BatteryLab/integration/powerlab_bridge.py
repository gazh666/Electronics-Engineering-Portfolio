"""PowerLab 只读桥接脚本（在 kaifa_power 环境执行）。

两种模式：

- ``power_map``：调用 PowerLab 真实闭环构建器与求解器，扫描 (Vin, Iload) 矩阵；
- ``integrated``：调用 PowerLab 真实闭环构建器，把其理想输入源设为 0 V，
  串入真实 3S 电池 ECM 与保护通路，形成**同一网表**内的联合仿真。

不调用 PowerLab 保存函数；波形与指标只写到 BatteryLab 运行目录。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np


def _node(analysis, name: str) -> np.ndarray:
    return np.array(analysis.nodes[name], dtype=float)


def _branch(analysis, name: str) -> np.ndarray:
    keys = list(analysis.branches.keys())
    candidates = [name, f"v{name}", f"i{name}"]
    for candidate in candidates:
        for key in keys:
            if key.lower() == candidate.lower():
                return np.array(analysis.branches[key], dtype=float)
    for key in keys:
        if name.lower() in key.lower():
            return np.array(analysis.branches[key], dtype=float)
    raise KeyError(f"branch {name!r} not found; available={keys}")


def _steady_voltage(time_s, vout, start: float, end: float) -> dict:
    mask = (time_s >= start) & (time_s <= end)
    if mask.sum() < 50:
        return {"status": "INSUFFICIENT_SAMPLES", "mean_drift_fraction": None, "ripple_change_fraction": None}
    window = vout[mask]
    half = len(window) // 2
    first_mean = float(np.mean(window[:half]))
    second_mean = float(np.mean(window[half:]))
    first_ripple = float(np.max(window[:half]) - np.min(window[:half]))
    second_ripple = float(np.max(window[half:]) - np.min(window[half:]))
    drift = abs(second_mean - first_mean) / max(abs(first_mean), 1e-9)
    ripple = abs(second_ripple - first_ripple)
    return {
        "status": "STEADY_STATE_REACHED" if drift < 5e-3 and ripple < 1e-2 else "NOT_STEADY",
        "mean_drift_fraction": drift,
        "ripple_change_fraction": ripple / max(first_ripple, 1e-9),
        "ripple_change_v": ripple,
    }


def _window_metrics(time_s, vout, vin, iin, il, iload) -> dict:
    pin = float(np.mean(vin * iin))
    pout = float(np.mean(vout * iload))
    return {
        "output_voltage_mean_v": float(np.mean(vout)),
        "output_voltage_ripple_vpp": float(np.max(vout) - np.min(vout)),
        "input_voltage_mean_v": float(np.mean(vin)),
        "input_current_mean_a": float(np.mean(iin)),
        "output_current_mean_a": float(np.mean(iload)),
        "inductor_peak_current_a": float(np.max(il)),
        "inductor_valley_current_a": float(np.min(il)),
        "input_power_w": pin,
        "output_power_w": pout,
        "efficiency_percent": (pout / pin * 100.0) if pin > 1e-12 else None,
        "samples": int(len(vout)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--request", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    started = time.perf_counter()
    project_root = Path(args.project_root).resolve()
    sys.path.insert(0, str(project_root))

    request = json.loads(Path(args.request).read_text(encoding="utf-8"))
    mode = request.get("mode", "power_map")

    from circuits.closed_loop_buck import build_closed_loop_buck
    from circuits.closed_loop_config import load_closed_loop_config
    from circuits.dynamic_load import CurrentStep, CurrentStepLoad
    from circuits.input_disturbance import nominal_line_case

    config = load_closed_loop_config()
    if request.get("variant"):
        config = config.with_variant(str(request["variant"]))
    if request.get("kp") is not None and request.get("ki") is not None:
        config = config.with_gains(float(request["kp"]), float(request["ki"]))
    if request.get("inductance_h") and request.get("capacitance_f"):
        stage = replace(
            config.power_stage,
            inductor=replace(
                config.power_stage.inductor,
                inductance_h=float(request["inductance_h"]),
                dcr_ohm=float(request.get("inductor_dcr_ohm", 0.05)),
            ),
            capacitor=replace(
                config.power_stage.capacitor,
                capacitance_f=float(request["capacitance_f"]),
                esr_ohm=float(request.get("capacitor_esr_ohm", 0.03)),
            ),
        )
        config = replace(config, power_stage=stage)
    if request.get("load_resistance_ohm"):
        config = replace(
            config,
            power_stage=replace(config.power_stage, load_resistance_ohm=float(request["load_resistance_ohm"])),
        )

    end_time = float(request.get("end_time_s", 0.004))
    step_time = float(request.get("step_time_s", 5e-8))
    payload = {
        "bridge": "powerlab_readonly_bridge",
        "mode": mode,
        "project_root": str(project_root),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    try:
        if mode == "power_map":
            payload["points"] = _run_power_map(
                request, config, end_time, step_time,
                nominal_line_case, CurrentStepLoad, CurrentStep, build_closed_loop_buck,
            )
        elif mode == "integrated":
            payload["integrated"] = _run_integrated(
                request, config, end_time, step_time, nominal_line_case, build_closed_loop_buck,
            )
        else:
            raise ValueError(f"unknown mode {mode!r}")
    finally:
        payload["duration_s"] = time.perf_counter() - started

    Path(args.output).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps({"status": "OK", "mode": mode, "duration_s": payload["duration_s"]}))
    return 0


def _run_power_map(request, config, end_time, step_time, nominal_line_case,
                   CurrentStepLoad, CurrentStep, builder):
    points = []
    window = float(request.get("steady_window_fraction", 0.35))
    loads = request.get("loads")
    if not loads:
        target = float(request.get("target_output_voltage_v", 5.0))
        loads = [
            {"resistance_ohm": target / float(current), "nominal_current_a": float(current)}
            for current in request["load_currents_a"]
        ]
    for vin in request["input_voltages_v"]:
        for load_spec in loads:
            resistance = float(load_spec["resistance_ohm"])
            nominal_current = float(load_spec["nominal_current_a"])
            point_config = replace(
                config,
                power_stage=replace(config.power_stage, load_resistance_ohm=resistance),
            ).with_load(None).with_line(nominal_line_case(float(vin))).with_timing(
                end_time, step_time_s=step_time, max_step_time_s=step_time
            )
            try:
                circuit, layout = builder(point_config, mode="closed_loop")
                analysis = circuit.simulator(temperature=25, nominal_temperature=25).transient(
                    step_time=step_time, end_time=end_time, max_time=step_time,
                    use_initial_condition=True,
                )
                time_s = np.array(analysis.time, dtype=float)
                vout = _node(analysis, layout.nodes["output"])
                vin_node = _node(analysis, layout.nodes["input"])
                iin = _branch(analysis, layout.branches["input_current"])
                il = _branch(analysis, layout.branches["inductor_current"])
                iload = _branch(analysis, layout.branches["load_current"])
            except Exception as exc:  # noqa: BLE001 - 保留真实失败
                points.append({
                    "input_voltage_v": vin, "load_current_a": nominal_current,
                    "load_resistance_ohm": resistance,
                    "status": "SOLVER_FAILED", "error": f"{type(exc).__name__}: {exc}",
                })
                continue
            end = float(time_s[-1])
            start = end * (1.0 - window)
            mask = time_s >= start
            overall = _window_metrics(time_s[mask], vout[mask], vin_node[mask], iin[mask], il[mask], iload[mask])
            steady = _steady_voltage(time_s, vout, max(end - 2e-3, start), end)
            status = "CONVERGED" if steady["status"] == "STEADY_STATE_REACHED" else "NOT_STEADY"
            if abs(overall["output_voltage_mean_v"] - 5.0) > 0.25:
                status = "OUTPUT_NOT_REGULATED"
            ccm = overall["inductor_valley_current_a"] > 0.0
            points.append({
                "input_voltage_v": vin, "load_current_a": nominal_current,
                "load_resistance_ohm": resistance, "status": status,
                "steady_state": steady, "metrics": overall, "ccm": ccm,
                "solver": {"step_time_s": step_time, "end_time_s": end_time},
                "netlist_sha256": hashlib.sha256(str(circuit).encode()).hexdigest(),
            })
    return points


def _run_integrated(request, config, end_time, step_time, nominal_line_case, builder):
    # PowerLab 要求输入源电压为正；置 1 mV 使其等价于"理想源不供电"，
    # 电池 ECM 成为唯一能量来源（1 mV 偏置在结果中可忽略并已记录）。
    integrated_config = config.with_line(nominal_line_case(1e-3)).with_timing(
        end_time, step_time_s=step_time, max_step_time_s=step_time
    )
    circuit, layout = builder(integrated_config, mode="closed_loop")
    # PowerLab 构建器把输入源硬编码为理想电压源 VIN。为使电池成为唯一电源，
    # 必须真正移除该理想源；仅把它设为 0 V 会形成低阻短路通路（已实测复现）。
    removed = circuit._elements.pop("VIN", None)  # noqa: SLF001 - PySpice 无公开删除接口
    if removed is None:
        for key, element in list(circuit._elements.items()):
            name = str(getattr(element, "name", key))
            if name.upper() == "VIN" or key.upper().endswith("VIN"):
                removed = circuit._elements.pop(key)
                break
    element_keys = list(circuit._elements.keys())
    input_source_removed = removed is not None
    input_node = layout.nodes["input"]
    output_node = layout.nodes["output"]

    cells = request["cells"]
    taps = ["0"]
    for index, cell in enumerate(cells, start=1):
        negative = taps[-1]
        positive = f"bpos{index}"
        o = f"cell{index}_o"
        x = f"cell{index}_x"
        circuit.V(f"OCV{index}", o, negative, float(cell["ocv_v"]))
        circuit.R(f"RP{index}", o, x, float(cell["rp_ohm"]))
        circuit.C(f"CP{index}", o, x, float(cell["cp_f"]), ic=float(cell.get("initial_polarization_v", 0.0)))
        circuit.R(f"R0_{index}", x, positive, float(cell["r0_ohm"]))
        taps.append(positive)
    bpos = taps[-1]
    circuit.V("BSENSE", bpos, "prot_in", 0.0)

    points = request.get("protection_control_points")
    if points:
        insert = [(float(t), float(v)) for t, v in points]
        if insert[0][0] > 0:
            insert.insert(0, (0.0, insert[0][1]))
        if insert[-1][0] < end_time:
            insert.append((end_time, insert[-1][1]))
        circuit.PieceWiseLinearVoltageSource("PCTRL", "prot_ctrl", circuit.gnd, values=insert)
    else:
        circuit.V("PCTRL", "prot_ctrl", circuit.gnd, 1.0)

    path_r = float(request.get("path_resistance_ohm", 0.052))
    off_r = 1e6
    circuit.B(
        "BPROT", "prot_in", input_node,
        current_expression=(
            f"V(prot_in,{input_node})/({path_r:.12g}+({off_r:.12g}-{path_r:.12g})"
            f"*(1-min(max(V(prot_ctrl),0),1)))"
        ),
    )
    circuit.C(
        "CIN", input_node, circuit.gnd,
        float(request.get("input_capacitance_f", 100e-6)),
        ic=float(request.get("input_capacitor_ic_v", 10.5)),
    )

    attempts = [step_time]
    for candidate in request.get("fallback_steps_s", [50e-9, 100e-9]):
        if float(candidate) not in attempts:
            attempts.append(float(candidate))

    last_error = None
    analysis = None
    used_step = None
    for attempt in attempts:
        try:
            analysis = circuit.simulator(temperature=25, nominal_temperature=25).transient(
                step_time=attempt, end_time=end_time, max_time=attempt,
                use_initial_condition=True,
            )
            used_step = attempt
            break
        except Exception as exc:  # noqa: BLE001 - 记录真实失败
            last_error = f"{type(exc).__name__}: {exc}"
    if analysis is None:
        return {"status": "SOLVER_FAILED", "error": last_error, "attempted_steps_s": attempts}

    time_s = np.array(analysis.time, dtype=float)
    vbat = _node(analysis, bpos)
    vin = _node(analysis, input_node)
    vout = _node(analysis, output_node)
    ibat = _branch(analysis, "bsense")
    iin = _branch(analysis, layout.branches["input_current"])
    il = _branch(analysis, layout.branches["inductor_current"])
    iload = _branch(analysis, layout.branches["load_current"])
    duty = _node(analysis, "duty")
    pwm = _node(analysis, "pwm")

    waveform_path = request.get("waveform_output")
    if waveform_path:
        target = Path(waveform_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        matrix = np.column_stack([time_s, vbat, vin, vout, ibat, iin, il, iload, duty, pwm])
        np.savetxt(
            target, matrix, delimiter=",",
            header="time_s,battery_voltage_v,converter_input_voltage_v,output_voltage_v,"
                   "battery_current_a,converter_input_current_a,inductor_current_a,load_current_a,duty_v,pwm_v",
            comments="", fmt="%.10g",
        )

    window = float(request.get("steady_window_fraction", 0.25))
    end = float(time_s[-1])
    start = end * (1.0 - window)
    mask = time_s >= start
    metrics = _window_metrics(time_s[mask], vout[mask], vin[mask], iin[mask], il[mask], iload[mask])
    metrics.update({
        "output_voltage_min_v": float(np.min(vout[mask])),
        "output_voltage_max_v": float(np.max(vout[mask])),
        "converter_input_voltage_min_v": float(np.min(vin)),
        "battery_voltage_mean_v": float(np.mean(vbat[mask])),
        "battery_voltage_min_v": float(np.min(vbat)),
        "battery_current_mean_a": float(np.mean(ibat[mask])),
        "battery_current_peak_a": float(np.max(ibat)),
        "battery_current_min_a": float(np.min(ibat)),
        "duty_mean": float(np.mean(duty[mask])),
        "pre_steady_battery_voltage_v": float(np.mean(vbat[time_s <= start])) if start > 0 else None,
    })
    steady = _steady_voltage(time_s, vout, start, end)
    return {
        "status": "CONVERGED",
        "used_step_s": used_step,
        "attempted_steps_s": attempts,
        "metrics": metrics,
        "steady_state": steady,
        "waveform_output": waveform_path,
        "netlist_sha256": hashlib.sha256(str(circuit).encode()).hexdigest(),
        "power_stage_source": "powerlab_build_closed_loop_buck",
        "battery_source": "stage3_identified_first_order_rc_ecm",
        "input_source_removed": input_source_removed,
        "element_keys": element_keys,
        "cell_voltage_nodes": taps,
    }


if __name__ == "__main__":
    sys.exit(main())
