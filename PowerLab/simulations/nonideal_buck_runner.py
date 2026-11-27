"""非理想 Buck 瞬态仿真入口（支持 A–E 五种对照模型）。"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from circuits.nonideal_buck import (
    build_nonideal_buck,
    get_variant_features,
    legacy_baseline_parameters,
)
from circuits.nonideal_config import NonidealBuckConfig
from circuits.validators import positive_number, temperature_celsius
from simulations.buck_runner import time_step_statistics
from simulations.models import SimulationResult
from simulations.runner import SimulationRunner


def run_nonideal_buck_transient(
    config: NonidealBuckConfig,
    variant: str | None = None,
    *,
    end_time_s: float | None = None,
    step_time_s: float | None = None,
    max_step_time_s: float | None = None,
    temperature_c: float | None = None,
) -> SimulationResult:
    """执行一次真实非理想 Buck 瞬态仿真。"""
    if not isinstance(config, NonidealBuckConfig):
        raise ValueError("config must be NonidealBuckConfig")
    features = get_variant_features(variant or config.model_variant)

    override: dict[str, float] = {}
    if end_time_s is not None:
        override["end_time_s"] = positive_number(end_time_s, "end_time_s")
    if step_time_s is not None:
        override["step_time_s"] = positive_number(step_time_s, "step_time_s")
    if max_step_time_s is not None:
        override["max_step_time_s"] = positive_number(max_step_time_s, "max_step_time_s")

    transient = replace(config.transient, **override) if override else config.transient
    transient.validate_for_switching(config.switching_frequency_hz)
    simulation_temperature = (
        config.transient.temperature_c
        if temperature_c is None
        else temperature_celsius(temperature_c)
    )

    circuit = build_nonideal_buck(config, features.variant)
    runner = SimulationRunner(temperature_c=simulation_temperature)
    result = runner.run_transient(
        circuit,
        transient.step_time_s,
        transient.end_time_s,
        0.0,
        max_time=transient.max_step_time_s,
        parameters={
            "model_variant": features.variant,
            "switching_frequency_hz": config.switching_frequency_hz,
            "duty_cycle": config.duty_cycle,
            "inductance_h": config.inductor.inductance_h,
            "inductor_dcr_ohm": config.inductor.dcr_ohm,
            "capacitance_f": config.capacitor.capacitance_f,
            "capacitor_esr_ohm": config.capacitor.esr_ohm,
            "load_resistance_ohm": config.load_resistance_ohm,
            "temperature_c": simulation_temperature,
        },
    )

    result.metadata["time_step_statistics"] = time_step_statistics(
        result.data["time_s"].to_numpy(),
        configured_max_step_s=transient.max_step_time_s,
    )
    result.metadata["model_variant"] = features.to_dict()
    result.metadata["nonideal_buck_parameters"] = config.to_dict()
    result.metadata["analysis_settings"] = {
        "requested_end_time_s": transient.end_time_s,
        "requested_step_time_s": transient.step_time_s,
        "requested_max_step_time_s": transient.max_step_time_s,
        "minimum_steps_per_period": config.period_s / transient.max_step_time_s,
        "simulation_temperature_c": simulation_temperature,
        "specification_type": config.specification_type,
        "data_source": "spice_simulation",
    }
    if features.variant == "A":
        result.metadata["legacy_baseline"] = {
            "builder": "circuits.buck.build_buck_from_parameters",
            "parameters": legacy_baseline_parameters(config).to_dict(),
        }
    return result


def simulate_variants(
    config: NonidealBuckConfig,
    variants: tuple[str, ...] = ("A", "B", "C", "D", "E"),
    *,
    temperature_c: float | None = None,
) -> dict[str, SimulationResult]:
    """依次真实运行多个对照模型，返回 ``variant -> result``。"""
    if not variants:
        raise ValueError("variants must not be empty")
    results: dict[str, SimulationResult] = {}
    for variant in variants:
        results[variant] = run_nonideal_buck_transient(
            config, variant, temperature_c=temperature_c
        )
    return results


def with_gate_resistance(
    config: NonidealBuckConfig, resistance_ohm: float
) -> NonidealBuckConfig:
    """返回更换栅极电阻后的配置（用于驱动波形对比）。"""
    if not isinstance(config, NonidealBuckConfig):
        raise ValueError("config must be NonidealBuckConfig")
    return replace(
        config,
        gate_driver=replace(config.gate_driver, gate_resistance_ohm=resistance_ohm),
    )


def with_load_resistance(
    config: NonidealBuckConfig, resistance_ohm: float
) -> NonidealBuckConfig:
    return replace(
        config,
        load_resistance_ohm=positive_number(resistance_ohm, "load_resistance_ohm"),
    )


def with_duty_cycle(
    config: NonidealBuckConfig, duty_cycle: float
) -> NonidealBuckConfig:
    return replace(config, duty_cycle=duty_cycle)


def summarize_result(result: SimulationResult) -> dict[str, Any]:
    """提取结果的基本元信息（不重算波形）。"""
    if not isinstance(result, SimulationResult):
        raise ValueError("result must be SimulationResult")
    return {
        "model_variant": result.metadata.get("model_variant", {}).get("variant"),
        "sample_count": int(len(result.data)),
        "duration_ms": result.metadata.get("duration_ms"),
        "time_step_statistics": result.metadata.get("time_step_statistics"),
        "analysis_settings": result.metadata.get("analysis_settings"),
    }
