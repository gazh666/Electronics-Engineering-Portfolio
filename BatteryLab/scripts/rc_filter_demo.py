"""Task 10/11/12：RC 输入滤波 AC、瞬态、干扰与参数扫描。"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd

from analysis.filter_response import compare_step_metrics, extract_ac_metrics, first_order_magnitude, first_order_phase_deg
from circuits.rc_filter import (
    RCFilterConfig,
    extract_cutoff,
    run_ac_response,
    run_interference,
    run_step_response,
    scan_parameters,
    theoretical_cutoff_hz,
)
from scripts.stage4_common import afe
from simulations.sensing_runner import finalize_run, new_sensing_run, write_frame, write_plots
from visualization.plots import plot_multi_series, plot_xy

SOURCE = "真实 ngspice 交流小信号/瞬态求解（spice_simulation）"


def main() -> int:
    config = afe()
    run = new_sensing_run("sensing")
    filter_config = RCFilterConfig(
        series_resistance_ohm=float(config["cell_voltage"]["input_filter_resistance_ohm"]),
        differential_capacitance_f=float(config["cell_voltage"]["differential_capacitance_f"]),
    )

    ac = run_ac_response(filter_config)
    cutoff = extract_cutoff(ac["frequency_hz"], ac["transfer"])
    metrics = extract_ac_metrics(ac["frequency_hz"], ac["gain_db"], ac["phase_deg"], cutoff_hz=filter_config.cutoff_hz)
    metrics["spice_cutoff_hz"] = cutoff
    metrics["cutoff_relative_error"] = (cutoff - filter_config.cutoff_hz) / filter_config.cutoff_hz

    step = run_step_response(filter_config, step_v=0.1)
    step_metrics = compare_step_metrics(step, filter_config.tau_s)

    interference = run_interference(filter_config)

    ac_frame = pd.DataFrame(
        {
            "frequency_hz": ac["frequency_hz"],
            "gain_db": ac["gain_db"],
            "phase_deg": ac["phase_deg"],
            "theory_gain_db": 20.0 * np.log10(first_order_magnitude(ac["frequency_hz"], filter_config.cutoff_hz)),
            "theory_phase_deg": first_order_phase_deg(ac["frequency_hz"], filter_config.cutoff_hz),
        }
    )
    write_frame(run, "rc_ac_response.csv", ac_frame)
    write_frame(run, "rc_step_response.csv", pd.DataFrame({"time_s": step["time_s"], "output_v": step["output_v"]}))
    write_frame(
        run,
        "rc_interference.csv",
        pd.DataFrame(
            {
                "time_s": interference["time_s"],
                "before_v": interference["before_v"],
                "after_v": interference["after_v"],
            }
        ),
    )

    scan = scan_parameters(
        resistances_ohm=[20.0, 47.0, 82.0],
        capacitances_f=[0.1e-6, 0.22e-6, 0.47e-6, 1.0e-6],
        run_step=True,
    )
    scan_frame = pd.DataFrame(scan)
    write_frame(run, "rc_parameter_scan.csv", scan_frame)

    plots = write_plots(
        run,
        [
            (
                "07_rc_filter_bode.png",
                plot_multi_series,
                {
                    "series": [
                        ("SPICE 幅频", ac_frame["frequency_hz"].tolist(), ac_frame["gain_db"].tolist()),
                        ("理论幅频", ac_frame["frequency_hz"].tolist(), ac_frame["theory_gain_db"].tolist()),
                        ("SPICE 相频", ac_frame["frequency_hz"].tolist(), ac_frame["phase_deg"].tolist()),
                        ("理论相频", ac_frame["frequency_hz"].tolist(), ac_frame["theory_phase_deg"].tolist()),
                    ],
                    "xlabel": "频率 (Hz)",
                    "ylabel": "增益 (dB) / 相位 (°)",
                    "title": "单体输入 RC 滤波 Bode 图（47 Ω×2 / 0.22 µF）",
                    "annotation": f"{SOURCE}；理论截止 {filter_config.cutoff_hz:.1f} Hz。",
                },
            ),
            (
                "08_rc_step_response.png",
                plot_xy,
                {
                    "x": (step["time_s"] - step["step_start_s"]) * 1e6,
                    "y": step["output_v"],
                    "xlabel": "相对阶跃时刻 (µs)",
                    "ylabel": "差分输出 (V)",
                    "title": "RC 滤波阶跃响应（0.1 V 阶跃）",
                    "annotation": f"{SOURCE}；10–90% 上升时间 {step_metrics['measured_rise_time_s']*1e6:.3f} µs。",
                    "color": "#1f77b4",
                },
            ),
            (
                "08b_rc_interference_100khz.png",
                plot_multi_series,
                {
                    "series": [
                        ("滤波前差分", (interference["time_s"] * 1000).tolist(), interference["before_v"].tolist()),
                        ("滤波后差分", (interference["time_s"] * 1000).tolist(), interference["after_v"].tolist()),
                    ],
                    "xlabel": "时间 (ms)",
                    "ylabel": "差分电压 (V)",
                    "title": "100 kHz 人工差模+共模干扰滤波前后对照",
                    "annotation": f"{SOURCE}；人工设计激励，不是真实 PowerLab EMC 数据。",
                },
            ),
            (
                "08c_rc_parameter_tradeoff.png",
                plot_xy,
                {
                    "x": scan_frame["spice_cutoff_hz"].tolist(),
                    "y": [value * 1e6 for value in scan_frame["settling_time_1pct_s"].tolist()],
                    "xlabel": "实际截止频率 (Hz)",
                    "ylabel": "1% 建立时间 (µs)",
                    "title": "RC 参数取舍：截止频率 vs 建立时间",
                    "annotation": f"{SOURCE}；增大 RC 提高抑制但降低响应速度。",
                    "color": "#ff7f0e",
                },
            ),
        ],
    )

    summary = {
        "filter": {
            "series_resistance_ohm": filter_config.series_resistance_ohm,
            "differential_capacitance_f": filter_config.differential_capacitance_f,
            "differential_resistance_ohm": filter_config.differential_resistance_ohm,
            "tau_s": filter_config.tau_s,
            "theoretical_cutoff_hz": filter_config.cutoff_hz,
        },
        "ac": metrics,
        "step": step_metrics,
        "interference": {
            "frequency_hz": interference["frequency_hz"],
            "rms_before_v": interference["rms_before_v"],
            "rms_after_v": interference["rms_after_v"],
            "attenuation_db": interference["attenuation_db"],
            "amplitude_before_v": interference["amplitude_before_v"],
            "amplitude_after_v": interference["amplitude_after_v"],
        },
        "parameter_scan": scan,
        "plots": plots,
    }
    payload = finalize_run(
        run,
        script="scripts/rc_filter_demo.py",
        summary=summary,
        metadata={"config": "configs/afe_config.yaml", "scan": {"R": [20, 47, 82], "C_uF": [0.1, 0.22, 0.47, 1.0]}},
    )

    print(f"run_id={run.run_id}")
    print(f"理论截止={filter_config.cutoff_hz:.3f} Hz，SPICE 截止={cutoff:.3f} Hz，相对误差={metrics['cutoff_relative_error']*100:.4f}%")
    print(f"1 kHz 衰减={metrics['attenuation_1000hz_db']:.3f} dB，10 kHz={metrics['attenuation_10000hz_db']:.3f} dB，100 kHz={metrics['attenuation_100000hz_db']:.3f} dB，1 MHz={metrics['attenuation_1000000hz_db']:.3f} dB")
    print(f"阶跃上升时间={step_metrics['measured_rise_time_s']*1e6:.3f} µs（理论 {step_metrics['theoretical_rise_time_s']*1e6:.3f} µs）")
    print(f"100 kHz 干扰衰减={interference['attenuation_db']:.3f} dB")
    print(scan_frame[["resistance_ohm", "capacitance_f", "spice_cutoff_hz", "attenuation_100khz_db", "settling_time_1pct_s"]].to_string(index=False))
    print(f"真实 SPICE 求解次数={payload['real_spice_solves']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
