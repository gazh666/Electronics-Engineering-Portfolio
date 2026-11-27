"""Task 17/18/19/20：通用 ADC 行为模型、量化、非理想项与混叠。"""

from __future__ import annotations

import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd

from sensing.adc import (
    ADCConfig,
    ADCErrorModel,
    adc_convert,
    adc_convert_real,
    check_monotonic,
    compare_resolutions,
    quantization_staircase,
)
from scripts.stage4_common import adc_settings, afe
from simulations.sensing_runner import finalize_run, new_sensing_run, write_frame, write_plots
from visualization.plots import plot_multi_series, plot_xy

SOURCE = "ADC 行为模型（adc_behavioral_model），不是真实芯片转换精度测量"


def alias_frequency(signal_hz: float, sample_hz: float) -> float:
    nearest = round(signal_hz / sample_hz)
    return abs(signal_hz - nearest * sample_hz)


def main() -> int:
    config = afe()
    adc_config = adc_settings(config)
    run = new_sensing_run("sensing")

    staircase = quantization_staircase(0.0, adc_config.reference_voltage_v, 4001, adc_config)
    valid_mask = ~staircase["saturated"] & np.isfinite(staircase["error_v"])
    max_quantization_lsb = float(np.max(np.abs(staircase["error_v"][valid_mask])) / adc_config.lsb_v)
    monotonic = check_monotonic(staircase["input_v"].tolist(), adc_config)

    boundary_voltages = (-0.1, 0.0, 0.5 * adc_config.lsb_v, 1.65, adc_config.reference_voltage_v, adc_config.reference_voltage_v + 0.1)
    boundary_rows = []
    for voltage in boundary_voltages:
        sample = adc_convert(voltage, adc_config)
        boundary_rows.append(
            {
                "input_v": voltage,
                "code": sample.code,
                "decoded_v": sample.decoded_voltage_v,
                "quantization_error_v": sample.quantization_error_v,
                "saturated_low": sample.saturated_low,
                "saturated_high": sample.saturated_high,
            }
        )

    resolution_rows = []
    for row in compare_resolutions(adc_config.reference_voltage_v, (10, 12, 16)):
        bits = int(row["bits"])
        bits_config = ADCConfig(adc_config.reference_voltage_v, bits)
        curve = quantization_staircase(0.0, adc_config.reference_voltage_v, 4001, bits_config)
        mask = ~curve["saturated"] & np.isfinite(curve["error_v"])
        resolution_rows.append(
            {
                **row,
                "max_quantization_error_lsb": float(np.max(np.abs(curve["error_v"][mask])) / bits_config.lsb_v),
                "max_quantization_error_v": float(np.max(np.abs(curve["error_v"][mask]))),
            }
        )

    input_voltage = 1.65
    error_models = {
        "reference_deviation": ADCErrorModel(reference_deviation_v=0.0005, random_seed=1),
        "input_offset": ADCErrorModel(input_offset_v=0.0005, random_seed=2),
        "gain_error": ADCErrorModel(gain_error_fraction=0.001, random_seed=3),
        "noise_only": ADCErrorModel(noise_rms_v=0.0002, random_seed=4),
        "inl_only": ADCErrorModel(inl_lsb=0.5, random_seed=5),
        "combined": ADCErrorModel(
            reference_deviation_v=0.0005,
            input_offset_v=0.0005,
            gain_error_fraction=0.001,
            noise_rms_v=0.0002,
            inl_lsb=0.5,
            random_seed=42,
        ),
    }
    non_ideal_rows = []
    for name, model in error_models.items():
        rng = np.random.default_rng(model.random_seed)
        samples = [adc_convert_real(input_voltage, adc_config, model, rng) for _ in range(1000)]
        errors = np.array([sample.decoded_voltage_v - input_voltage for sample in samples])
        non_ideal_rows.append(
            {
                "case": name,
                "input_v": input_voltage,
                "mean_error_v": float(np.mean(errors)),
                "mae_v": float(np.mean(np.abs(errors))),
                "max_abs_error_v": float(np.max(np.abs(errors))),
                "std_v": float(np.std(errors)),
            }
        )

    interference_hz = 100_000.0
    slow_hz = 2.0
    interference_amplitude = 0.1
    sampling_rows = []
    sample_series = {}
    for sample_hz in (1000.0, 1100.0, 10_000.0, 10_100.0):
        for phase in (0.0, math.pi / 2.0):
            duration = 0.02
            count = int(sample_hz * duration)
            times = np.arange(count) / sample_hz
            signal = 3.7 + 0.02 * np.sin(2 * math.pi * slow_hz * times) + interference_amplitude * np.sin(2 * math.pi * interference_hz * times + phase)
            average_4 = np.convolve(signal, np.ones(4) / 4.0, mode="valid")
            average_16 = np.convolve(signal, np.ones(16) / 16.0, mode="valid")
            sampling_rows.append(
                {
                    "sample_hz": sample_hz,
                    "phase_deg": math.degrees(phase),
                    "nyquist_hz": sample_hz / 2.0,
                    "aliased_frequency_hz": alias_frequency(interference_hz, sample_hz),
                    "mean_sample_v": float(np.mean(signal)),
                    "mean_average4_v": float(np.mean(average_4)),
                    "mean_average16_v": float(np.mean(average_16)),
                    "peak_to_peak_v": float(np.max(signal) - np.min(signal)),
                }
            )
            sample_series[(sample_hz, phase)] = (times, signal)

    write_frame(run, "adc_staircase.csv", pd.DataFrame(staircase))
    write_frame(run, "adc_boundary_cases.csv", pd.DataFrame(boundary_rows))
    write_frame(run, "adc_resolution_comparison.csv", pd.DataFrame(resolution_rows))
    write_frame(run, "adc_non_ideal_cases.csv", pd.DataFrame(non_ideal_rows))
    write_frame(run, "adc_sampling_alias.csv", pd.DataFrame(sampling_rows))

    times_1k, signal_1k = sample_series[(1000.0, 0.0)]
    continuous_time = np.linspace(0.0, 0.002, 4000)
    continuous_signal = 3.7 + 0.02 * np.sin(2 * math.pi * slow_hz * continuous_time) + interference_amplitude * np.sin(2 * math.pi * interference_hz * continuous_time)

    plots = write_plots(
        run,
        [
            (
                "12_adc_quantization_staircase.png",
                plot_multi_series,
                {
                    "series": [
                        ("理想输入", staircase["input_v"][::10].tolist(), staircase["input_v"][::10].tolist()),
                        ("12 位量化输出", staircase["input_v"][::10].tolist(), staircase["decoded_v"][::10].tolist()),
                    ],
                    "xlabel": "输入电压 (V)",
                    "ylabel": "解码电压 (V)",
                    "title": "12 位 ADC 量化阶梯（3.3 V 参考，中点重构）",
                    "annotation": f"{SOURCE}；LSB={adc_config.lsb_v*1000:.6f} mV。",
                },
            ),
            (
                "13_adc_quantization_error.png",
                plot_xy,
                {
                    "x": staircase["input_v"][::5].tolist(),
                    "y": (staircase["error_v"][::5] * 1000.0).tolist(),
                    "xlabel": "输入电压 (V)",
                    "ylabel": "量化误差 (mV)",
                    "title": "12 位 ADC 理想量化误差（限制在 ±0.5 LSB）",
                    "annotation": f"{SOURCE}；最大 {max_quantization_lsb:.4f} LSB。",
                    "color": "#2ca02c",
                },
            ),
            (
                "14_adc_resolution_comparison.png",
                plot_xy,
                {
                    "x": [row["bits"] for row in resolution_rows],
                    "y": [row["max_quantization_error_v"] * 1e6 for row in resolution_rows],
                    "xlabel": "ADC 位数",
                    "ylabel": "最大量化误差 (µV)",
                    "title": "不同 ADC 位数量化误差对照（3.3 V 参考）",
                    "annotation": f"{SOURCE}；分辨率不等于有效精度（未做 SINAD/ENOB 实验）。",
                    "color": "#9467bd",
                },
            ),
            (
                "15_adc_aliasing_samples.png",
                plot_multi_series,
                {
                    "series": [
                        ("连续 100 kHz 干扰", (continuous_time * 1000).tolist(), continuous_signal.tolist()),
                        ("1 kHz 采样点", (times_1k[:5] * 1000).tolist(), signal_1k[:5].tolist()),
                    ],
                    "xlabel": "时间 (ms)",
                    "ylabel": "电压 (V)",
                    "title": "100 kHz 干扰在 1 kHz 采样下的混叠",
                    "annotation": f"{SOURCE}；100 kHz 恰为 1 kHz 的 100 倍，混叠到近似直流。",
                },
            ),
            (
                "16_adc_aliasing_dc_offset.png",
                plot_multi_series,
                {
                    "series": [
                        (
                            f"{row['sample_hz']:.0f} Hz, {row['phase_deg']:.0f}°",
                            [row["sample_hz"]],
                            [row["mean_sample_v"] - 3.7],
                        )
                        for row in sampling_rows
                    ],
                    "xlabel": "采样频率 (Hz)",
                    "ylabel": "采样均值相对 3.7 V 的偏差 (V)",
                    "title": "混叠造成的等效直流偏差与采样相位关系",
                    "annotation": f"{SOURCE}；数字平均不能消除已发生的混叠。",
                },
            ),
        ],
    )

    summary = {
        "adc_config": {
            "reference_voltage_v": adc_config.reference_voltage_v,
            "resolution_bits": adc_config.resolution_bits,
            "lsb_v": adc_config.lsb_v,
            "levels": adc_config.levels,
        },
        "max_quantization_error_lsb": max_quantization_lsb,
        "monotonic": monotonic,
        "boundary_cases": boundary_rows,
        "resolution_comparison": resolution_rows,
        "non_ideal_cases": non_ideal_rows,
        "sampling_alias": sampling_rows,
        "interference_hz": interference_hz,
        "plots": plots,
    }
    payload = finalize_run(
        run,
        script="scripts/adc_demo.py",
        summary=summary,
        metadata={"config": "configs/afe_config.yaml; configs/adc_config.yaml", "real_spice_solves": 0},
    )

    print(f"run_id={run.run_id}")
    print(f"12 位 LSB={adc_config.lsb_v*1000:.6f} mV，最大量化误差={max_quantization_lsb:.4f} LSB，单调={monotonic}")
    print(pd.DataFrame(resolution_rows)[["bits", "lsb_v", "max_quantization_error_v"]].to_string(index=False))
    print(pd.DataFrame(non_ideal_rows).to_string(index=False))
    print(pd.DataFrame(sampling_rows).to_string(index=False))
    print("真实 SPICE 求解次数=0（本节为 ADC 行为模型与解析信号）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
