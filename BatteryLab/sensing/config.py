"""第四阶段配置加载与参数有限性/范围/单位检查。"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Mapping

from battery_models.parameters import ParameterError, load_yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "configs"


class ConfigError(ValueError):
    """配置缺失或非法。"""


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{name} 必须是数值，实际为 {value!r}")
    number = float(value)
    if not math.isfinite(number):
        raise ConfigError(f"{name} 必须是有限数值，实际为 {number!r}")
    return number


def _positive(value: Any, name: str) -> float:
    number = _finite(value, name)
    if number <= 0.0:
        raise ConfigError(f"{name} 必须为正数，实际为 {number!r}")
    return number


def _in_range(value: Any, name: str, low: float, high: float) -> float:
    number = _finite(value, name)
    if not low <= number <= high:
        raise ConfigError(f"{name} 必须位于 [{low}, {high}]，实际为 {number!r}")
    return number


def _int_bits(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{name} 必须是整数，实际为 {value!r}")
    if not 4 <= value <= 24:
        raise ConfigError(f"{name} 必须位于 [4, 24]，实际为 {value}")
    return value


def _section(config: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    section = config.get(key)
    if not isinstance(section, Mapping):
        raise ConfigError(f"缺少配置段: {key}")
    return section


def load_config(name: str) -> dict[str, Any]:
    path = CONFIG_DIR / name
    if not path.exists():
        raise ConfigError(f"配置文件不存在: {path}")
    try:
        payload = load_yaml(path)
    except ParameterError as exc:
        raise ConfigError(f"{name} 解析失败: {exc}") from exc
    if not isinstance(payload, dict):
        raise ConfigError(f"{name} 顶层必须是映射")
    return payload


def load_afe_config() -> dict[str, Any]:
    config = load_config("afe_config.yaml")
    pack = _section(config, "battery_pack")
    if int(pack["series_cells"]) != 3:
        raise ConfigError("本阶段教学 AFE 固定为 3 串")
    _positive(pack["nominal_pack_voltage_v"], "battery_pack.nominal_pack_voltage_v")

    cell = _section(config, "cell_voltage")
    low = _positive(cell["measurement_min_v"], "cell_voltage.measurement_min_v")
    high = _positive(cell["measurement_max_v"], "cell_voltage.measurement_max_v")
    if low >= high:
        raise ConfigError("cell_voltage 测量下限必须小于上限")
    _positive(cell["input_filter_resistance_ohm"], "cell_voltage.input_filter_resistance_ohm")
    _positive(cell["differential_capacitance_f"], "cell_voltage.differential_capacitance_f")

    amp = _section(config, "differential_amplifier")
    supply = _positive(amp["supply_voltage_v"], "differential_amplifier.supply_voltage_v")
    for name in ("r1_ohm", "r2_ohm", "r3_ohm", "r4_ohm"):
        _positive(amp[name], f"differential_amplifier.{name}")
    gain = _positive(amp["nominal_gain"], "differential_amplifier.nominal_gain")
    ratio = float(amp["r2_ohm"]) / float(amp["r1_ohm"])
    if abs(ratio - gain) > 1e-9:
        raise ConfigError("nominal_gain 必须等于 r2/r1")
    if abs(float(amp["r4_ohm"]) / float(amp["r3_ohm"]) - gain) > 1e-9:
        raise ConfigError("四电阻差分放大器要求 r4/r3 = r2/r1")
    ref = _finite(amp["reference_voltage_v"], "differential_amplifier.reference_voltage_v")
    if not 0.0 <= ref < supply:
        raise ConfigError("差分放大器参考电压必须位于 [0, 供电) 内")
    _in_range(amp["teaching_output_low_v"], "differential_amplifier.teaching_output_low_v", 0.0, supply)
    _in_range(amp["teaching_output_high_v"], "differential_amplifier.teaching_output_high_v", 0.0, supply)
    if float(amp["teaching_output_low_v"]) >= float(amp["teaching_output_high_v"]):
        raise ConfigError("教学运放输出下限必须小于上限")

    current = _section(config, "current_sensing")
    imin = _finite(current["minimum_current_a"], "current_sensing.minimum_current_a")
    imax = _finite(current["maximum_current_a"], "current_sensing.maximum_current_a")
    if imin >= imax or imin > 0 or imax < 0:
        raise ConfigError("双向电流范围必须跨越 0 且 min < max")
    _positive(current["shunt_resistance_ohm"], "current_sensing.shunt_resistance_ohm")
    _positive(current["amplifier_gain"], "current_sensing.amplifier_gain")
    _positive(current["zero_current_reference_v"], "current_sensing.zero_current_reference_v")
    _positive(current["output_filter_resistance_ohm"], "current_sensing.output_filter_resistance_ohm")
    _positive(current["output_filter_capacitance_f"], "current_sensing.output_filter_capacitance_f")

    adc = _section(config, "adc")
    _positive(adc["reference_voltage_v"], "adc.reference_voltage_v")
    _int_bits(adc["resolution_bits"], "adc.resolution_bits")

    ntc = _section(config, "temperature_sensing")
    _positive(ntc["reference_resistance_ohm"], "temperature_sensing.reference_resistance_ohm")
    _positive(ntc["beta_k"], "temperature_sensing.beta_k")
    _positive(ntc["pullup_resistance_ohm"], "temperature_sensing.pullup_resistance_ohm")
    _positive(ntc["excitation_voltage_v"], "temperature_sensing.excitation_voltage_v")
    tmin = _finite(ntc["minimum_temperature_c"], "temperature_sensing.minimum_temperature_c")
    tmax = _finite(ntc["maximum_temperature_c"], "temperature_sensing.maximum_temperature_c")
    if tmin >= tmax:
        raise ConfigError("温度范围下限必须小于上限")
    return config


def load_adc_config() -> dict[str, Any]:
    config = load_config("adc_config.yaml")
    nominal = _section(config, "nominal")
    _positive(nominal["reference_voltage_v"], "adc.nominal.reference_voltage_v")
    _int_bits(nominal["resolution_bits"], "adc.nominal.resolution_bits")
    non_ideal = _section(config, "non_ideal")
    for name in ("reference_deviation_v", "input_offset_v", "gain_error_fraction", "noise_rms_v", "inl_lsb"):
        _finite(non_ideal[name], f"adc.non_ideal.{name}")
    if float(non_ideal["noise_rms_v"]) < 0.0:
        raise ConfigError("adc 噪声 RMS 不能为负")
    sampling = _section(config, "sampling")
    _positive(sampling["analog_step_s"], "adc.sampling.analog_step_s")
    return config


def load_current_sensing_config() -> dict[str, Any]:
    config = load_config("current_sensing.yaml")
    shunt = _section(config, "shunt")
    _positive(shunt["nominal_resistance_ohm"], "shunt.nominal_resistance_ohm")
    _positive(shunt["rated_power_w"], "shunt.rated_power_w")
    amp = _section(config, "amplifier")
    _positive(amp["gain_v_per_v"], "amplifier.gain_v_per_v")
    _positive(amp["bandwidth_hz"], "amplifier.bandwidth_hz")
    if float(amp["common_mode_min_v"]) >= float(amp["common_mode_max_v"]):
        raise ConfigError("INA240 共模范围必须 min < max")
    if float(amp["supply_min_v"]) >= float(amp["supply_max_v"]):
        raise ConfigError("INA240 供电范围必须 min < max")
    meas = _section(config, "measurement")
    imin = _finite(meas["minimum_current_a"], "measurement.minimum_current_a")
    imax = _finite(meas["maximum_current_a"], "measurement.maximum_current_a")
    if imin >= imax or imin > 0 or imax < 0:
        raise ConfigError("双向电流测量范围必须跨越 0")
    return config


def load_ntc_config() -> dict[str, Any]:
    config = load_config("ntc_config.yaml")
    ntc = _section(config, "ntc")
    _positive(ntc["nominal_resistance_ohm"], "ntc.nominal_resistance_ohm")
    _positive(ntc["beta_k"], "ntc.beta_k")
    divider = _section(config, "divider")
    _positive(divider["pullup_resistance_ohm"], "divider.pullup_resistance_ohm")
    _positive(divider["excitation_voltage_v"], "divider.excitation_voltage_v")
    if abs(float(divider["excitation_voltage_v"]) - float(divider["adc_reference_voltage_v"])) > 1e-12:
        raise ConfigError("比率式测量要求分压激励与 ADC 参考一致")
    rng = _section(config, "temperature_range")
    if float(rng["minimum_c"]) >= float(rng["maximum_c"]):
        raise ConfigError("NTC 温度范围必须 min < max")
    return config


def load_tolerances() -> dict[str, Any]:
    config = load_config("sensing_tolerances.yaml")
    if isinstance(config.get("sample_count"), bool) or int(config["sample_count"]) <= 0:
        raise ConfigError("容差采样数量必须为正整数")
    for section_name, keys in (
        ("voltage_sensing", ("resistor_tolerance_percent", "opamp_input_offset_max_v")),
        ("current_sensing", ("shunt_tolerance_percent", "amplifier_gain_tolerance_percent", "input_offset_max_v")),
        ("adc", ("reference_tolerance_percent", "input_offset_max_v")),
        ("ntc", ("r25_tolerance_percent", "beta_tolerance_percent", "pullup_tolerance_percent")),
    ):
        section = _section(config, section_name)
        for key in keys:
            _finite(section[key], f"{section_name}.{key}")
            if float(section[key]) < 0.0:
                raise ConfigError(f"{section_name}.{key} 不能为负")
    return config


def load_validation_limits() -> dict[str, Any]:
    config = load_config("stage4_validation.yaml")
    ideal = _section(config, "ideal_consistency")
    _positive(ideal["divider_and_diff_amp_theory_vs_spice_v"], "ideal_consistency.divider_and_diff_amp_theory_vs_spice_v")
    _positive(ideal["bidirectional_current_theory_vs_spice_v"], "ideal_consistency.bidirectional_current_theory_vs_spice_v")
    _positive(ideal["rc_cutoff_frequency_relative_error"], "ideal_consistency.rc_cutoff_frequency_relative_error")
    non_ideal = _section(config, "non_ideal_measurement")
    _positive(non_ideal["cell_voltage_max_error_v"], "non_ideal_measurement.cell_voltage_max_error_v")
    _positive(non_ideal["current_max_error_a"], "non_ideal_measurement.current_max_error_a")
    _positive(non_ideal["ntc_max_temperature_error_c"], "non_ideal_measurement.ntc_max_temperature_error_c")
    return config
