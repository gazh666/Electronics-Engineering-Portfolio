"""器件容差蒙特卡洛与校准前后对照（Task 28/29）。

默认采用独立均匀分布的教学容差假设，不代表真实生产批次统计分布。
1000 组数学行为模型样本不描述为 1000 次真实 SPICE 求解。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from sensing.adc import ADCConfig, ADCErrorModel, adc_convert_real
from sensing.calibration import CalibrationModel, fit_two_point_calibration, identity_calibration
from sensing.temperature_decoder import ntc_resistance, ntc_temperature
from sensing.voltage_decoder import four_resistor_output


class ToleranceError(ValueError):
    """容差分析输入非法。"""


def _uniform(rng: np.random.Generator, nominal: float, tolerance_percent: float) -> float:
    fraction = tolerance_percent / 100.0
    return float(nominal * (1.0 + rng.uniform(-fraction, fraction)))


VOLTAGE_CALIBRATION_POINTS = (3.0, 4.1)
VOLTAGE_VALIDATION_POINTS = (2.5, 3.3, 3.7, 3.9, 4.25)
CURRENT_CALIBRATION_POINTS = (-2.0, 2.0)
CURRENT_VALIDATION_POINTS = (-2.5, -1.5, -0.5, 0.5, 1.5, 2.5)
TEMPERATURE_CALIBRATION_POINTS = (0.0, 60.0)
TEMPERATURE_VALIDATION_POINTS = (10.0, 20.0, 25.0, 30.0, 40.0, 50.0)


@dataclass(frozen=True)
class VoltageDevice:
    r1_ohm: float
    r2_ohm: float
    r3_ohm: float
    r4_ohm: float
    opamp_offset_v: float
    adc_reference_deviation_v: float
    adc_offset_v: float
    adc_gain_error: float
    adc_noise_v: float
    seed: int


def sample_voltage_device(rng: np.random.Generator, config: dict, tolerances: dict) -> VoltageDevice:
    amp = config["differential_amplifier"]
    tol = tolerances["voltage_sensing"]["resistor_tolerance_percent"]
    adc_tol = tolerances["adc"]
    nominal_ref = float(config["adc"]["reference_voltage_v"])
    return VoltageDevice(
        r1_ohm=_uniform(rng, float(amp["r1_ohm"]), tol),
        r2_ohm=_uniform(rng, float(amp["r2_ohm"]), tol),
        r3_ohm=_uniform(rng, float(amp["r3_ohm"]), tol),
        r4_ohm=_uniform(rng, float(amp["r4_ohm"]), tol),
        opamp_offset_v=float(rng.uniform(-tolerances["voltage_sensing"]["opamp_input_offset_max_v"], tolerances["voltage_sensing"]["opamp_input_offset_max_v"])),
        adc_reference_deviation_v=nominal_ref * float(adc_tol["reference_tolerance_percent"]) / 100.0 * float(rng.uniform(-1.0, 1.0)),
        adc_offset_v=float(rng.uniform(-adc_tol["input_offset_max_v"], adc_tol["input_offset_max_v"])),
        adc_gain_error=float(rng.uniform(-0.001, 0.001)),
        adc_noise_v=0.0002,
        seed=int(rng.integers(0, 2**31 - 1)),
    )


def voltage_reading(device: VoltageDevice, cell_voltage_v: float, config: dict, common_mode_v: float | None = None) -> float:
    amp = config["differential_amplifier"]
    reference = float(amp["reference_voltage_v"])
    nominal_gain = float(amp["nominal_gain"])
    if common_mode_v is None:
        vhigh, vlow = cell_voltage_v, 0.0
    else:
        vhigh = float(common_mode_v) + 0.5 * cell_voltage_v
        vlow = float(common_mode_v) - 0.5 * cell_voltage_v
    output = four_resistor_output(
        vhigh,
        vlow,
        r1_ohm=device.r1_ohm,
        r2_ohm=device.r2_ohm,
        r3_ohm=device.r3_ohm,
        r4_ohm=device.r4_ohm,
        reference_v=reference,
    )
    actual_gain = device.r2_ohm / device.r1_ohm
    output += (1.0 + actual_gain) * device.opamp_offset_v
    errors = ADCErrorModel(
        reference_deviation_v=device.adc_reference_deviation_v,
        input_offset_v=device.adc_offset_v,
        gain_error_fraction=device.adc_gain_error,
        noise_rms_v=device.adc_noise_v,
        random_seed=device.seed,
    )
    adc_config = ADCConfig(
        reference_voltage_v=float(config["adc"]["reference_voltage_v"]),
        resolution_bits=int(config["adc"]["resolution_bits"]),
    )
    sample = adc_convert_real(output, adc_config, errors, np.random.default_rng(device.seed + int(cell_voltage_v * 1000)))
    return (sample.decoded_voltage_v - reference) / nominal_gain


@dataclass(frozen=True)
class CurrentDevice:
    shunt_ohm: float
    gain: float
    input_offset_v: float
    adc_reference_deviation_v: float
    adc_offset_v: float
    adc_gain_error: float
    adc_noise_v: float
    seed: int


def sample_current_device(rng: np.random.Generator, config: dict, tolerances: dict, current_config: dict) -> CurrentDevice:
    shunt = config["current_sensing"]
    amp = current_config["amplifier"]
    tol = tolerances["current_sensing"]
    adc_tol = tolerances["adc"]
    nominal_ref = float(config["adc"]["reference_voltage_v"])
    return CurrentDevice(
        shunt_ohm=_uniform(rng, float(shunt["shunt_resistance_ohm"]), float(tol["shunt_tolerance_percent"])),
        gain=_uniform(rng, float(shunt["amplifier_gain"]), float(tol["amplifier_gain_tolerance_percent"])),
        input_offset_v=float(rng.uniform(-tol["input_offset_max_v"], tol["input_offset_max_v"])),
        adc_reference_deviation_v=nominal_ref * float(adc_tol["reference_tolerance_percent"]) / 100.0 * float(rng.uniform(-1.0, 1.0)),
        adc_offset_v=float(rng.uniform(-adc_tol["input_offset_max_v"], adc_tol["input_offset_max_v"])),
        adc_gain_error=float(rng.uniform(-0.001, 0.001)),
        adc_noise_v=0.0002,
        seed=int(rng.integers(0, 2**31 - 1)),
    )


def current_reading(device: CurrentDevice, current_a: float, config: dict) -> float:
    shunt = config["current_sensing"]
    reference = float(shunt["zero_current_reference_v"])
    nominal_gain = float(shunt["amplifier_gain"])
    nominal_shunt = float(shunt["shunt_resistance_ohm"])
    output = reference + device.gain * device.shunt_ohm * current_a + device.gain * device.input_offset_v
    errors = ADCErrorModel(
        reference_deviation_v=device.adc_reference_deviation_v,
        input_offset_v=device.adc_offset_v,
        gain_error_fraction=device.adc_gain_error,
        noise_rms_v=device.adc_noise_v,
        random_seed=device.seed,
    )
    adc_config = ADCConfig(
        reference_voltage_v=float(config["adc"]["reference_voltage_v"]),
        resolution_bits=int(config["adc"]["resolution_bits"]),
    )
    sample = adc_convert_real(output, adc_config, errors, np.random.default_rng(device.seed + int(current_a * 1000)))
    return (sample.decoded_voltage_v - reference) / (nominal_gain * nominal_shunt)


@dataclass(frozen=True)
class TemperatureDevice:
    r25_ohm: float
    beta_k: float
    pullup_ohm: float
    adc_offset_v: float
    adc_noise_v: float
    seed: int


def sample_temperature_device(rng: np.random.Generator, config: dict, tolerances: dict, ntc_config: dict) -> TemperatureDevice:
    ntc = ntc_config["ntc"]
    divider = ntc_config["divider"]
    tol = tolerances["ntc"]
    adc_tol = tolerances["adc"]
    return TemperatureDevice(
        r25_ohm=_uniform(rng, float(ntc["nominal_resistance_ohm"]), float(tol["r25_tolerance_percent"])),
        beta_k=_uniform(rng, float(ntc["beta_k"]), float(tol["beta_tolerance_percent"])),
        pullup_ohm=_uniform(rng, float(divider["pullup_resistance_ohm"]), float(tol["pullup_tolerance_percent"])),
        adc_offset_v=float(rng.uniform(-adc_tol["input_offset_max_v"], adc_tol["input_offset_max_v"])),
        adc_noise_v=0.0002,
        seed=int(rng.integers(0, 2**31 - 1)),
    )


def temperature_reading(device: TemperatureDevice, temperature_c: float, config: dict) -> float:
    nominal = config["temperature_sensing"]
    adc_config = ADCConfig(
        reference_voltage_v=float(config["adc"]["reference_voltage_v"]),
        resolution_bits=int(config["adc"]["resolution_bits"]),
    )
    resistance = ntc_resistance(temperature_c, r25_ohm=device.r25_ohm, beta_k=device.beta_k)
    ratio = resistance / (device.pullup_ohm + resistance)
    # 比率式：激励与 ADC 参考同源，参考误差在理想条件下抵消。
    ratio += device.adc_offset_v / adc_config.reference_voltage_v
    rng = np.random.default_rng(device.seed + int(temperature_c * 100))
    if device.adc_noise_v:
        ratio += float(rng.normal(0.0, device.adc_noise_v / adc_config.reference_voltage_v))
    code = min(max(int(math.floor(ratio * adc_config.levels)), 0), adc_config.levels - 1)
    decoded_voltage = (code + 0.5) * adc_config.lsb_v
    nominal_ratio = decoded_voltage / float(config["temperature_sensing"]["excitation_voltage_v"])
    recovered_resistance = float(nominal["pullup_resistance_ohm"]) * nominal_ratio / (1.0 - nominal_ratio)
    return ntc_temperature(
        recovered_resistance,
        r25_ohm=float(nominal["reference_resistance_ohm"]),
        beta_k=float(nominal["beta_k"]),
    )


def _metrics(errors: np.ndarray) -> dict[str, float]:
    absolute = np.abs(errors)
    return {
        "mean_error": float(np.mean(errors)),
        "mae": float(np.mean(absolute)),
        "rmse": float(np.sqrt(np.mean(errors**2))),
        "max_abs_error": float(np.max(absolute)),
        "p95_abs_error": float(np.percentile(absolute, 95)),
    }


def _calibration_comparison(pre_errors: Sequence[np.ndarray], post_errors: Sequence[np.ndarray]) -> dict[str, object]:
    pre = np.concatenate(pre_errors)
    post = np.concatenate(post_errors)
    pre_metrics = _metrics(pre)
    post_metrics = _metrics(post)
    improvement = {}
    for key in ("mae", "rmse", "max_abs_error", "p95_abs_error"):
        before = pre_metrics[key]
        after = post_metrics[key]
        improvement[key] = float((before - after) / before * 100.0) if before else 0.0
    return {
        "pre_calibration": pre_metrics,
        "post_calibration": post_metrics,
        "improvement_percent": improvement,
    }


def run_voltage_tolerance(
    *,
    config: dict,
    tolerances: dict,
    sample_count: int,
    seed: int,
    calibration_points: Sequence[float] = VOLTAGE_CALIBRATION_POINTS,
    validation_points: Sequence[float] = VOLTAGE_VALIDATION_POINTS,
    common_mode_v: float | None = 9.7,
) -> dict[str, object]:
    rng = np.random.default_rng(seed)
    parameter_rows = []
    sample_metrics = []
    pre_errors = []
    post_errors = []
    for index in range(sample_count):
        device = sample_voltage_device(rng, config, tolerances)
        measured_cal = [voltage_reading(device, point, config, common_mode_v) for point in calibration_points]
        model = fit_two_point_calibration(calibration_points[0], measured_cal[0], calibration_points[1], measured_cal[1], calibration_id=f"voltage_{index}")
        measured_validation = [voltage_reading(device, point, config, common_mode_v) for point in validation_points]
        pre = np.array(measured_validation) - np.array(validation_points)
        post = np.array([model.apply(value) for value in measured_validation]) - np.array(validation_points)
        pre_errors.append(pre)
        post_errors.append(post)
        parameter_rows.append(
            {
                "sample": index,
                "r1_ohm": device.r1_ohm,
                "r2_ohm": device.r2_ohm,
                "r3_ohm": device.r3_ohm,
                "r4_ohm": device.r4_ohm,
                "opamp_offset_v": device.opamp_offset_v,
                "adc_reference_deviation_v": device.adc_reference_deviation_v,
                "adc_offset_v": device.adc_offset_v,
                "adc_gain_error": device.adc_gain_error,
                "calibration_gain": model.gain,
                "calibration_offset": model.offset,
                "pre_mae": float(np.mean(np.abs(pre))),
                "post_mae": float(np.mean(np.abs(post))),
                "pre_max_abs": float(np.max(np.abs(pre))),
                "post_max_abs": float(np.max(np.abs(post))),
            }
        )
        sample_metrics.append(parameter_rows[-1])
    comparison = _calibration_comparison(pre_errors, post_errors)
    return {
        "channel": "cell_voltage",
        "unit": "V",
        "sample_count": sample_count,
        "common_mode_v": common_mode_v,
        "calibration_points": list(calibration_points),
        "validation_points": list(validation_points),
        "parameter_samples": parameter_rows,
        "calibration_comparison": comparison,
        "sample_metrics": sample_metrics,
    }


def run_current_tolerance(
    *,
    config: dict,
    tolerances: dict,
    current_config: dict,
    sample_count: int,
    seed: int,
    calibration_points: Sequence[float] = CURRENT_CALIBRATION_POINTS,
    validation_points: Sequence[float] = CURRENT_VALIDATION_POINTS,
) -> dict[str, object]:
    rng = np.random.default_rng(seed + 1)
    parameter_rows = []
    pre_errors = []
    post_errors = []
    zero_errors = []
    for index in range(sample_count):
        device = sample_current_device(rng, config, tolerances, current_config)
        measured_zero = current_reading(device, 0.0, config)
        zero_offset = measured_zero
        measured_cal = [current_reading(device, point, config) for point in calibration_points]
        model = fit_two_point_calibration(calibration_points[0], measured_cal[0], calibration_points[1], measured_cal[1], calibration_id=f"current_{index}")
        measured_validation = [current_reading(device, point, config) for point in validation_points]
        pre = np.array(measured_validation) - np.array(validation_points)
        post = np.array([model.apply(value) for value in measured_validation]) - np.array(validation_points)
        post_zero = np.array([value - zero_offset for value in measured_validation]) - np.array(validation_points)
        pre_errors.append(pre)
        post_errors.append(post)
        zero_errors.append(post_zero)
        parameter_rows.append(
            {
                "sample": index,
                "shunt_ohm": device.shunt_ohm,
                "gain": device.gain,
                "input_offset_v": device.input_offset_v,
                "adc_reference_deviation_v": device.adc_reference_deviation_v,
                "adc_offset_v": device.adc_offset_v,
                "adc_gain_error": device.adc_gain_error,
                "zero_calibration_offset_a": zero_offset,
                "calibration_gain": model.gain,
                "calibration_offset": model.offset,
                "pre_mae": float(np.mean(np.abs(pre))),
                "post_mae": float(np.mean(np.abs(post))),
                "pre_max_abs": float(np.max(np.abs(pre))),
                "post_max_abs": float(np.max(np.abs(post))),
            }
        )
    comparison = _calibration_comparison(pre_errors, post_errors)
    comparison["zero_calibration_only"] = _metrics(np.concatenate(zero_errors))
    return {
        "channel": "current",
        "unit": "A",
        "sample_count": sample_count,
        "calibration_points": list(calibration_points),
        "validation_points": list(validation_points),
        "parameter_samples": parameter_rows,
        "calibration_comparison": comparison,
        "sample_metrics": parameter_rows,
    }


def run_temperature_tolerance(
    *,
    config: dict,
    tolerances: dict,
    ntc_config: dict,
    sample_count: int,
    seed: int,
    calibration_points: Sequence[float] = TEMPERATURE_CALIBRATION_POINTS,
    validation_points: Sequence[float] = TEMPERATURE_VALIDATION_POINTS,
) -> dict[str, object]:
    rng = np.random.default_rng(seed + 2)
    parameter_rows = []
    pre_errors = []
    post_errors = []
    for index in range(sample_count):
        device = sample_temperature_device(rng, config, tolerances, ntc_config)
        measured_cal = [temperature_reading(device, point, config) for point in calibration_points]
        model = fit_two_point_calibration(calibration_points[0], measured_cal[0], calibration_points[1], measured_cal[1], calibration_id=f"temperature_{index}")
        measured_validation = [temperature_reading(device, point, config) for point in validation_points]
        pre = np.array(measured_validation) - np.array(validation_points)
        post = np.array([model.apply(value) for value in measured_validation]) - np.array(validation_points)
        pre_errors.append(pre)
        post_errors.append(post)
        parameter_rows.append(
            {
                "sample": index,
                "r25_ohm": device.r25_ohm,
                "beta_k": device.beta_k,
                "pullup_ohm": device.pullup_ohm,
                "adc_offset_v": device.adc_offset_v,
                "calibration_gain": model.gain,
                "calibration_offset": model.offset,
                "pre_mae": float(np.mean(np.abs(pre))),
                "post_mae": float(np.mean(np.abs(post))),
                "pre_max_abs": float(np.max(np.abs(pre))),
                "post_max_abs": float(np.max(np.abs(post))),
            }
        )
    comparison = _calibration_comparison(pre_errors, post_errors)
    return {
        "channel": "temperature",
        "unit": "degC",
        "sample_count": sample_count,
        "calibration_points": list(calibration_points),
        "validation_points": list(validation_points),
        "parameter_samples": parameter_rows,
        "calibration_comparison": comparison,
        "sample_metrics": parameter_rows,
    }


def select_corner_samples(rows: Sequence[dict], error_key: str) -> list[dict]:
    """选择标称、代表性、高误差与极限角点样本。"""
    if not rows:
        raise ToleranceError("没有可选择的样本")
    nominal = min(rows, key=lambda row: abs(row.get("pre_mae", 0.0)) + abs(row.get("post_mae", 0.0)))
    representative = sorted(rows, key=lambda row: row.get(error_key, 0.0))[len(rows) // 2]
    high_error = max(rows, key=lambda row: abs(row.get(error_key, 0.0)))
    corner = max(rows, key=lambda row: abs(row.get("calibration_offset", 0.0)) + abs(row.get("calibration_gain", 1.0) - 1.0))
    return [
        {"role": "nominal", **nominal},
        {"role": "representative", **representative},
        {"role": "high_error", **high_error},
        {"role": "extreme_corner", **corner},
    ]
