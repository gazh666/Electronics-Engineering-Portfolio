"""Task 30/31/32/33：3S 完整 AFE、单向波形驱动瞬态、干扰与全链路采集。"""

from __future__ import annotations

import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd

from analysis.sensing_metrics import compute_metrics
from circuits.afe_frontend import run_afe_transient, solve_afe_static
from scripts.stage4_common import (
    adc_error_model,
    adc_settings,
    afe,
    amplifier_config,
    current_sense_config,
    ntc_settings,
)
from sensing.measurement_chain import measure_current, measure_temperature, measure_voltage
from sensing.temperature_decoder import ntc_resistance
from simulations.sensing_runner import finalize_run, new_sensing_run, write_frame, write_plots
from storage.result_store import write_json
from visualization.plots import plot_multi_series, plot_xy

SOURCE = "真实 ngspice 瞬态/工作点求解（spice_simulation）"
IDENTIFIED_PATH = PROJECT_ROOT / "data" / "identified" / "identified_parameters_all_models.csv"

SCENARIOS = [
    ("nominal_rest", [3.6, 3.8, 4.0], 0.0, 25.0),
    ("discharge_2a", [3.6, 3.8, 4.0], 2.0, 25.0),
    ("charge_1a", [3.6, 3.8, 4.0], -1.0, 25.0),
    ("inconsistent_cells", [3.5, 3.7, 4.05], 0.0, 25.0),
    ("over_declared_range", [4.1, 4.2, 4.3], 0.0, 25.0),
]


def load_identified_first_order() -> dict[str, float]:
    frame = pd.read_csv(IDENTIFIED_PATH)
    row = frame[frame["model_order"] == 1].iloc[0]
    return {
        "r0_ohm": float(row["r0_ohm"]),
        "r1_ohm": float(row["r1_ohm"]),
        "tau1_s": float(row["tau1_s"]),
        "capacity_ah": float(row["capacity_ah"]),
        "parameter_source": "identified_parameters_stage3",
    }


def build_current_profile(duration_s: float = 3.5, step_s: float = 0.01) -> tuple[np.ndarray, np.ndarray]:
    keys = np.array(
        [
            [0.0, 0.0],
            [0.5, 0.0],
            [0.52, 2.0],
            [1.5, 2.0],
            [1.52, 0.0],
            [2.0, 0.0],
            [2.02, -1.0],
            [3.0, -1.0],
            [3.02, 0.0],
            [duration_s, 0.0],
        ]
    )
    time_s = np.arange(0.0, duration_s + 0.5 * step_s, step_s)
    current = np.interp(time_s, keys[:, 0], keys[:, 1])
    return time_s, current


def build_cell_waveforms(
    time_s: np.ndarray,
    current_a: np.ndarray,
    ocv_v: tuple[float, float, float],
    parameters: dict[str, float],
) -> list[np.ndarray]:
    r0 = parameters["r0_ohm"]
    r1 = parameters["r1_ohm"]
    tau = parameters["tau1_s"]
    v1 = [0.0, 0.0, 0.0]
    cells = [[], [], []]
    for index, time in enumerate(time_s):
        if index > 0:
            dt = float(time_s[index] - time_s[index - 1])
            previous_current = float(current_a[index - 1])
            for channel in range(3):
                v1[channel] = previous_current * r1 + (v1[channel] - previous_current * r1) * math.exp(-dt / tau)
        for channel in range(3):
            cells[channel].append(ocv_v[channel] - float(current_a[index]) * r0 - v1[channel])
    return [np.asarray(values, dtype=float) for values in cells]


def main() -> int:
    config = afe()
    amp = amplifier_config(config)
    current_config = current_sense_config(config)
    ntc_config = ntc_settings()
    adc_config = adc_settings(config)
    adc_errors = adc_error_model(config)
    parameters = load_identified_first_order()
    run = new_sensing_run("sensing")

    static_rows = []
    for name, cells, current, temperature in SCENARIOS:
        solution = solve_afe_static(cells, current, temperature, amp, current_config, ntc_config)
        outputs = solution["cell_outputs_v"]
        decoded = [
            (outputs[index] - amp.reference_v) / amp.nominal_gain
            for index in range(3)
        ]
        static_rows.append(
            {
                "scenario": name,
                "cell1_v": cells[0],
                "cell2_v": cells[1],
                "cell3_v": cells[2],
                "current_a": current,
                "temperature_c": temperature,
                "out1_v": outputs[0],
                "out2_v": outputs[1],
                "out3_v": outputs[2],
                "decoded_cell1_v": decoded[0],
                "decoded_cell2_v": decoded[1],
                "decoded_cell3_v": decoded[2],
                "max_cell_error_v": max(abs(decoded[index] - cells[index]) for index in range(3)),
                "current_output_v": solution["current_output_v"],
                "decoded_current_a": (solution["current_output_v"] - current_config.reference_v) / (current_config.amplifier_gain * current_config.shunt_ohm),
                "ntc_voltage_v": solution["ntc_voltage_v"],
                "top_cell_pin_common_mode_v": solution["cell_pin_common_mode_v"][2],
            }
        )

    temperature_rows = []
    for temperature in (0.0, 25.0, 60.0):
        solution = solve_afe_static([3.6, 3.8, 4.0], 0.0, temperature, amp, current_config, ntc_config)
        measurement = measure_temperature(
            channel_name="ntc",
            reference_temperature_c=temperature,
            analog_output_v=solution["ntc_voltage_v"],
            adc_config=adc_config,
            r25_ohm=ntc_config.r25_ohm,
            beta_k=ntc_config.beta_k,
            pullup_ohm=ntc_config.pullup_ohm,
            excitation_v=ntc_config.excitation_v,
            adc_errors=adc_errors,
            rng=np.random.default_rng(100 + int(temperature)),
        )
        temperature_rows.append(
            {
                "reference_temperature_c": temperature,
                "ntc_voltage_v": solution["ntc_voltage_v"],
                "estimated_temperature_c": measurement.estimated_value,
                "error_c": measurement.measurement_error,
                "status": measurement.status,
                "adc_code": measurement.adc_code,
            }
        )

    time_s, current_profile = build_current_profile()
    cells = build_cell_waveforms(time_s, current_profile, (3.6, 3.8, 4.0), parameters)
    transient = run_afe_transient(
        cells,
        time_s,
        current_profile,
        25.0,
        amp,
        current_config,
        ntc_config,
        step_s=0.01,
        max_step_s=0.005,
    )

    sample_times = np.arange(0.1, time_s[-1], 0.1)
    cell_references = [np.interp(sample_times, time_s, values) for values in cells]
    current_reference = np.interp(sample_times, time_s, current_profile)
    cell_outputs = [np.interp(sample_times, transient["time_s"], transient[f"out{index}"]) for index in (1, 2, 3)]
    current_output = np.interp(sample_times, transient["time_s"], transient["out_i"])

    voltage_measurements = [[] for _ in range(3)]
    current_measurements = []
    for index, time in enumerate(sample_times):
        for channel in range(3):
            voltage_measurements[channel].append(
                measure_voltage(
                    channel_name=f"cell{channel + 1}",
                    reference_cell_v=float(cell_references[channel][index]),
                    analog_output_v=float(cell_outputs[channel][index]),
                    gain=amp.nominal_gain,
                    reference_v=amp.reference_v,
                    adc_config=adc_config,
                    adc_errors=adc_errors,
                    output_low_v=0.0,
                    output_high_v=amp.supply_v,
                    pin_common_mode_v=None,
                    rng=np.random.default_rng(1000 + index * 10 + channel),
                )
            )
        current_measurements.append(
            measure_current(
                channel_name="pack_current",
                reference_current_a=float(current_reference[index]),
                analog_output_v=float(current_output[index]),
                amplifier_gain=current_config.amplifier_gain,
                shunt_ohm=current_config.shunt_ohm,
                zero_reference_v=current_config.reference_v,
                adc_config=adc_config,
                adc_errors=adc_errors,
                output_low_v=current_config.amplifier_output_low_v,
                output_high_v=current_config.amplifier_output_high_v,
                rng=np.random.default_rng(2000 + index),
            )
        )

    voltage_metric_rows = []
    for channel in range(3):
        estimated = [float(item.estimated_value) for item in voltage_measurements[channel]]
        metrics = compute_metrics(estimated, cell_references[channel].tolist(), unit="V", full_scale=4.25, full_scale_definition="declared_measurement_max")
        metrics.update({"channel": f"cell{channel + 1}", "invalid_count": sum(1 for item in voltage_measurements[channel] if not item.is_valid)})
        voltage_metric_rows.append(metrics)
    current_metrics = compute_metrics(
        [float(item.estimated_value) for item in current_measurements],
        current_reference.tolist(),
        unit="A",
        full_scale=5.0,
        full_scale_definition="bidirectional_-2.5A_to_+2.5A_span",
    )
    current_metrics["channel"] = "pack_current"

    # 干扰场景
    interference_time = np.arange(0.0, 0.001, 0.0001)
    interference_cells = [np.full_like(interference_time, value) for value in (3.6, 3.8, 4.0)]
    interference_current = np.zeros_like(interference_time)
    interference_data = run_afe_transient(
        interference_cells,
        interference_time,
        interference_current,
        25.0,
        amp,
        current_config,
        ntc_config,
        step_s=1e-6,
        max_step_s=1e-6,
        common_mode_interference_v=0.05,
        differential_interference_v=0.05,
        interference_hz=100_000.0,
    )
    interference_after = (interference_data["out2"] - amp.reference_v) / amp.nominal_gain
    interference_before = 0.5 * (3.8) + 0.05 * np.sin(2 * math.pi * 100_000.0 * interference_data["time_s"])
    interference_after_ac = interference_after - np.mean(interference_after)
    interference_before_ac = interference_before - np.mean(interference_before)
    rms_before = float(np.sqrt(np.mean(interference_before_ac[-len(interference_before_ac) // 2 :] ** 2)))
    rms_after = float(np.sqrt(np.mean(interference_after_ac[-len(interference_after_ac) // 2 :] ** 2)))
    attenuation_db = 20.0 * math.log10(rms_after / rms_before) if rms_before > 0 else float("nan")

    # 状态处理：NTC 开路/短路
    status_rows = []
    for label, voltage in (("open", 0.99 * ntc_config.excitation_v), ("short", 0.01 * ntc_config.excitation_v)):
        measurement = measure_temperature(
            channel_name="ntc",
            reference_temperature_c=None,
            analog_output_v=voltage,
            adc_config=adc_config,
            r25_ohm=ntc_config.r25_ohm,
            beta_k=ntc_config.beta_k,
            pullup_ohm=ntc_config.pullup_ohm,
            excitation_v=ntc_config.excitation_v,
        )
        status_rows.append({"case": label, "analog_output_v": voltage, "status": measurement.status, "estimated_value": measurement.estimated_value, "note": measurement.note})

    write_frame(run, "afe_static_scenarios.csv", pd.DataFrame(static_rows))
    write_frame(run, "afe_temperature_scenarios.csv", pd.DataFrame(temperature_rows))
    write_frame(run, "afe_voltage_metrics.csv", pd.DataFrame(voltage_metric_rows))
    write_frame(run, "afe_current_metrics.csv", pd.DataFrame([current_metrics]))
    write_frame(run, "afe_status_cases.csv", pd.DataFrame(status_rows))
    write_frame(
        run,
        "afe_transient_waveform.csv",
        pd.DataFrame(
            {
                "time_s": transient["time_s"],
                "cell1_v": transient["n1"],
                "cell2_v": transient["n2"] - transient["n1"],
                "cell3_v": transient["n3"] - transient["n2"],
                "out1_v": transient["out1"],
                "out2_v": transient["out2"],
                "out3_v": transient["out3"],
                "current_a": np.interp(transient["time_s"], time_s, current_profile),
                "current_output_v": transient["out_i"],
                "ntc_voltage_v": transient["temp"],
            }
        ),
    )
    write_json(
        run.path / "afe_summary.json",
        {
            "identified_parameters": parameters,
            "voltage_metrics": voltage_metric_rows,
            "current_metrics": current_metrics,
            "temperature_rows": temperature_rows,
            "status_rows": status_rows,
            "interference": {
                "rms_before_v": rms_before,
                "rms_after_v": rms_after,
                "attenuation_db": attenuation_db,
            },
        },
    )

    waveform_frame = pd.DataFrame(
        {
            "time_s": transient["time_s"],
            "cell1_v": transient["n1"],
            "cell2_v": transient["n2"] - transient["n1"],
            "cell3_v": transient["n3"] - transient["n2"],
            "out1_v": transient["out1"],
            "out2_v": transient["out2"],
            "out3_v": transient["out3"],
            "current_a": np.interp(transient["time_s"], time_s, current_profile),
            "current_output_v": transient["out_i"],
        }
    )

    plots = write_plots(
        run,
        [
            (
                "29_afe_3s_waveform.png",
                plot_multi_series,
                {
                    "series": [
                        ("cell1 电压", waveform_frame["time_s"].tolist(), waveform_frame["cell1_v"].tolist()),
                        ("cell2 电压", waveform_frame["time_s"].tolist(), waveform_frame["cell2_v"].tolist()),
                        ("cell3 电压", waveform_frame["time_s"].tolist(), waveform_frame["cell3_v"].tolist()),
                        ("cell1 放大输出", waveform_frame["time_s"].tolist(), waveform_frame["out1_v"].tolist()),
                    ],
                    "xlabel": "时间 (s)",
                    "ylabel": "电压 (V)",
                    "title": "3S 完整 AFE 瞬态：单体电压与差分放大器输出",
                    "annotation": f"{SOURCE}；电池波形由第三阶段辨识参数单向驱动。",
                },
            ),
            (
                "30_afe_current_step.png",
                plot_multi_series,
                {
                    "series": [
                        ("真实电流", waveform_frame["time_s"].tolist(), waveform_frame["current_a"].tolist()),
                        ("解码电流", waveform_frame["time_s"].tolist(), ((waveform_frame["current_output_v"] - current_config.reference_v) / (current_config.amplifier_gain * current_config.shunt_ohm)).tolist()),
                    ],
                    "xlabel": "时间 (s)",
                    "ylabel": "电流 (A)",
                    "title": "AFE 电流通道：放电→静置→充电阶跃",
                    "annotation": f"{SOURCE}；Rshunt=10 mΩ，G=50。",
                },
            ),
            (
                "31_afe_interference_100khz.png",
                plot_multi_series,
                {
                    "series": [
                        ("滤波前等效输入", (interference_data["time_s"] * 1e6).tolist(), interference_before.tolist()),
                        ("滤波后通道输出", (interference_data["time_s"] * 1e6).tolist(), interference_after.tolist()),
                    ],
                    "xlabel": "时间 (µs)",
                    "ylabel": "电压 (V)",
                    "title": "3S AFE 上的人工 100 kHz 差模+共模干扰",
                    "annotation": f"{SOURCE}；人工设计激励，不是 PowerLab 实测 EMC。衰减 {attenuation_db:.2f} dB。",
                },
            ),
            (
                "32_afe_temperature.png",
                plot_xy,
                {
                    "x": [row["reference_temperature_c"] for row in temperature_rows],
                    "y": [row["estimated_temperature_c"] for row in temperature_rows],
                    "xlabel": "参考温度 (℃)",
                    "ylabel": "AFE 解码温度 (℃)",
                    "title": "3S AFE 温度通道",
                    "annotation": f"{SOURCE}；NTC 自热未建模。",
                    "color": "#8c564b",
                },
            ),
        ],
    )

    summary = {
        "identified_parameters": parameters,
        "static_scenarios": static_rows,
        "temperature_scenarios": temperature_rows,
        "voltage_metrics": voltage_metric_rows,
        "current_metrics": current_metrics,
        "interference": {
            "rms_before_v": rms_before,
            "rms_after_v": rms_after,
            "attenuation_db": attenuation_db,
        },
        "status_cases": status_rows,
        "plots": plots,
    }
    payload = finalize_run(
        run,
        script="scripts/afe_system_demo.py",
        summary=summary,
        metadata={
            "config": "configs/afe_config.yaml",
            "battery_model": "identified_parameters_stage3_first_order",
            "note": "电池侧波形由辨识模型单向驱动，不是双向闭环联合仿真。",
        },
    )

    print(f"run_id={run.run_id}")
    print(f"辨识参数：R0={parameters['r0_ohm']*1000:.3f} mΩ，R1={parameters['r1_ohm']*1000:.3f} mΩ，tau1={parameters['tau1_s']:.3f} s")
    print(pd.DataFrame(static_rows)[["scenario", "max_cell_error_v", "decoded_current_a", "ntc_voltage_v", "top_cell_pin_common_mode_v"]].to_string(index=False))
    print(pd.DataFrame(voltage_metric_rows)[["channel", "mae", "max_abs_error", "invalid_count"]].to_string(index=False))
    print(f"电流：MAE={current_metrics['mae']*1000:.3f} mA，最大={current_metrics['max_abs_error']*1000:.3f} mA")
    print(pd.DataFrame(temperature_rows).to_string(index=False))
    print(f"100 kHz 人工干扰衰减={attenuation_db:.3f} dB")
    print(pd.DataFrame(status_rows).to_string(index=False))
    print(f"真实 SPICE 求解次数={payload['real_spice_solves']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
