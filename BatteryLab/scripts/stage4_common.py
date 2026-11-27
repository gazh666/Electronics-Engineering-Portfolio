"""第四阶段脚本共用配置与对象构造。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from circuits.current_sensing import CurrentSenseConfig
from circuits.differential_amplifier import DifferentialAmplifierConfig
from circuits.opamp_models import CurrentAmplifierSpec
from circuits.ntc_sensing import NtcConfig
from sensing.adc import ADCConfig, ADCErrorModel
from sensing.config import (
    load_adc_config,
    load_afe_config,
    load_current_sensing_config,
    load_ntc_config,
    load_tolerances,
    load_validation_limits,
)


def afe() -> dict[str, Any]:
    return load_afe_config()


def amplifier_config(config: dict[str, Any] | None = None) -> DifferentialAmplifierConfig:
    return DifferentialAmplifierConfig.from_config(config or afe())


def current_sense_config(config: dict[str, Any] | None = None) -> CurrentSenseConfig:
    settings = config or afe()
    section = settings["current_sensing"]
    return CurrentSenseConfig(
        shunt_ohm=float(section["shunt_resistance_ohm"]),
        amplifier_gain=float(section["amplifier_gain"]),
        reference_v=float(section["zero_current_reference_v"]),
        amplifier_output_low_v=float(section["amplifier_output_low_v"]),
        amplifier_output_high_v=float(section["amplifier_output_high_v"]),
        adc_reference_v=float(settings["adc"]["reference_voltage_v"]),
    )


def ntc_settings(config: dict[str, Any] | None = None) -> NtcConfig:
    return NtcConfig.from_config(config or load_ntc_config())


def adc_settings(config: dict[str, Any] | None = None) -> ADCConfig:
    settings = config or afe()
    adc = settings["adc"]
    return ADCConfig(
        reference_voltage_v=float(adc["reference_voltage_v"]),
        resolution_bits=int(adc["resolution_bits"]),
    )


def adc_error_model(config: dict[str, Any] | None = None) -> ADCErrorModel:
    adc_config = load_adc_config()
    non_ideal = adc_config["non_ideal"]
    return ADCErrorModel(
        reference_deviation_v=float(non_ideal["reference_deviation_v"]),
        input_offset_v=float(non_ideal["input_offset_v"]),
        gain_error_fraction=float(non_ideal["gain_error_fraction"]),
        noise_rms_v=float(non_ideal["noise_rms_v"]),
        inl_lsb=float(non_ideal["inl_lsb"]),
        random_seed=int(non_ideal["random_seed"]),
    )


def current_amplifier_spec(config: dict[str, Any] | None = None) -> CurrentAmplifierSpec:
    settings = config or load_current_sensing_config()
    amp = settings["amplifier"]
    return CurrentAmplifierSpec(
        name="ina240",
        gain=float(amp["gain_v_per_v"]),
        reference_voltage_v=float(amp["reference_voltage_v"]),
        input_offset_v=0.0,
        gain_error_fraction=0.0,
        cmrr_db=float(amp["cmrr_db_typ"]),
        bandwidth_hz=float(amp["bandwidth_hz"]),
        output_low_v=float(amp["output_low_v"]),
        output_high_v=float(amp["output_high_v"]),
    )


def tolerances() -> dict[str, Any]:
    return load_tolerances()


def limits() -> dict[str, Any]:
    return load_validation_limits()
