"""独立器件真实仿真入口（MOSFET / 二极管）。

本模块只负责构建测试台、调用 ngspice 直流扫描并标注元数据；
特性提取与合格判定在 :mod:`analysis.device_characteristics` 中完成。
"""

from __future__ import annotations

from typing import Any

import numpy as np

from circuits.device_testbench import (
    SOURCE_DIODE,
    SOURCE_MOSFET_DRAIN,
    SOURCE_MOSFET_GATE,
    build_diode_forward_testbench,
    build_diode_reverse_testbench,
    build_mosfet_output_testbench,
    build_mosfet_transfer_testbench,
    validate_sweep,
)
from circuits.nonideal_config import DiodeModelConfig, MosfetModelConfig
from circuits.validators import temperature_celsius
from simulations.models import SimulationResult
from simulations.runner import SimulationRunner

#: 默认器件温度（固定值，不做自热耦合）。
DEFAULT_DEVICE_TEMPERATURE_C = 25.0


def _resolve_temperature(temperature_c: float | None) -> float:
    if temperature_c is None:
        return DEFAULT_DEVICE_TEMPERATURE_C
    return temperature_celsius(temperature_c)


def _annotate(
    result: SimulationResult,
    *,
    device: str,
    model: dict[str, Any],
    conditions: dict[str, Any],
    temperature_c: float,
    sweep_source: str,
) -> None:
    result.metadata["device"] = device
    result.metadata["device_model"] = model
    result.metadata["test_conditions"] = {
        **conditions,
        "temperature_c": temperature_c,
        "sweep_source": sweep_source,
        "data_source": "spice_simulation",
    }
    result.metadata["sign_conventions"] = {
        "drain_current_a": "-i(DD) for the drain sweep source",
        "gate_current_a": "-i(GG) for the gate sweep source",
        "diode_current_a": "-i(DD) for the diode sweep source",
        "diode_voltage_v": "V(anode) - V(cathode)",
    }


def run_mosfet_transfer(
    config: MosfetModelConfig,
    *,
    vds_v: float,
    vgs_start_v: float,
    vgs_stop_v: float,
    vgs_step_v: float,
    temperature_c: float | None = None,
) -> SimulationResult:
    """真实扫描 ``ID-VGS`` 转移特性。"""
    if not isinstance(config, MosfetModelConfig):
        raise ValueError("config must be MosfetModelConfig")
    start, stop, step = validate_sweep(
        vgs_start_v, vgs_stop_v, vgs_step_v, name="transfer_sweep"
    )
    circuit = build_mosfet_transfer_testbench(config, vds_v)
    temperature = _resolve_temperature(temperature_c)
    result = SimulationRunner(temperature_c=temperature).run_dc(
        circuit,
        SOURCE_MOSFET_GATE,
        start,
        stop,
        step,
        parameters={
            "device": "mosfet",
            "test": "transfer",
            "vds_v": float(vds_v),
            "temperature_c": temperature,
            "model_name": config.model_name,
        },
    )
    _annotate(
        result,
        device="mosfet_transfer",
        model=config.to_dict(),
        conditions={
            "vds_v": float(vds_v),
            "vgs_start_v": start,
            "vgs_stop_v": stop,
            "vgs_step_v": step,
        },
        temperature_c=temperature,
        sweep_source=SOURCE_MOSFET_GATE,
    )
    return result


def run_mosfet_output(
    config: MosfetModelConfig,
    *,
    vgs_v: float,
    vds_start_v: float,
    vds_stop_v: float,
    vds_step_v: float,
    temperature_c: float | None = None,
) -> SimulationResult:
    """真实扫描指定 ``VGS`` 下的 ``ID-VDS`` 输出特性。"""
    if not isinstance(config, MosfetModelConfig):
        raise ValueError("config must be MosfetModelConfig")
    start, stop, step = validate_sweep(
        vds_start_v, vds_stop_v, vds_step_v, name="output_sweep"
    )
    circuit = build_mosfet_output_testbench(config, vgs_v)
    temperature = _resolve_temperature(temperature_c)
    result = SimulationRunner(temperature_c=temperature).run_dc(
        circuit,
        SOURCE_MOSFET_DRAIN,
        start,
        stop,
        step,
        parameters={
            "device": "mosfet",
            "test": "output",
            "vgs_v": float(vgs_v),
            "temperature_c": temperature,
            "model_name": config.model_name,
        },
    )
    _annotate(
        result,
        device="mosfet_output",
        model=config.to_dict(),
        conditions={
            "vgs_v": float(vgs_v),
            "vds_start_v": start,
            "vds_stop_v": stop,
            "vds_step_v": step,
        },
        temperature_c=temperature,
        sweep_source=SOURCE_MOSFET_DRAIN,
    )
    return result


def run_mosfet_off_state(
    config: MosfetModelConfig,
    *,
    vgs_v: float = 0.0,
    vds_start_v: float = 0.0,
    vds_stop_v: float = 5.0,
    vds_step_v: float = 0.1,
    temperature_c: float | None = None,
) -> SimulationResult:
    """测量 ``VGS`` 低于阈值时的漏极漏电流。"""
    result = run_mosfet_output(
        config,
        vgs_v=vgs_v,
        vds_start_v=vds_start_v,
        vds_stop_v=vds_stop_v,
        vds_step_v=vds_step_v,
        temperature_c=temperature_c,
    )
    result.metadata["device"] = "mosfet_off_state"
    result.metadata["test_conditions"]["test"] = "off_state"
    return result


def run_diode_forward(
    config: DiodeModelConfig,
    *,
    vd_start_v: float,
    vd_stop_v: float,
    vd_step_v: float,
    temperature_c: float | None = None,
) -> SimulationResult:
    """真实扫描二极管正向 ``I-V``。"""
    if not isinstance(config, DiodeModelConfig):
        raise ValueError("config must be DiodeModelConfig")
    start, stop, step = validate_sweep(
        vd_start_v, vd_stop_v, vd_step_v, name="diode_forward_sweep"
    )
    if start < 0:
        raise ValueError("diode forward sweep must start at a nonnegative voltage")
    circuit = build_diode_forward_testbench(config)
    temperature = _resolve_temperature(temperature_c)
    result = SimulationRunner(temperature_c=temperature).run_dc(
        circuit,
        SOURCE_DIODE,
        start,
        stop,
        step,
        parameters={
            "device": "diode",
            "test": "forward",
            "temperature_c": temperature,
            "model_name": config.model_name,
        },
    )
    _annotate(
        result,
        device="diode_forward",
        model=config.to_dict(),
        conditions={
            "vd_start_v": start,
            "vd_stop_v": stop,
            "vd_step_v": step,
        },
        temperature_c=temperature,
        sweep_source=SOURCE_DIODE,
    )
    return result


def run_diode_reverse(
    config: DiodeModelConfig,
    *,
    vd_start_v: float,
    vd_stop_v: float,
    vd_step_v: float,
    temperature_c: float | None = None,
) -> SimulationResult:
    """真实扫描二极管反向漏电流（阳极电压为负）。"""
    if not isinstance(config, DiodeModelConfig):
        raise ValueError("config must be DiodeModelConfig")
    start, stop, step = validate_sweep(
        vd_start_v, vd_stop_v, vd_step_v, name="diode_reverse_sweep"
    )
    if stop > 0:
        raise ValueError("diode reverse sweep must end at or below zero volts")
    circuit = build_diode_reverse_testbench(config)
    temperature = _resolve_temperature(temperature_c)
    result = SimulationRunner(temperature_c=temperature).run_dc(
        circuit,
        SOURCE_DIODE,
        start,
        stop,
        step,
        parameters={
            "device": "diode",
            "test": "reverse",
            "temperature_c": temperature,
            "model_name": config.model_name,
        },
    )
    _annotate(
        result,
        device="diode_reverse",
        model=config.to_dict(),
        conditions={
            "vd_start_v": start,
            "vd_stop_v": stop,
            "vd_step_v": step,
        },
        temperature_c=temperature,
        sweep_source=SOURCE_DIODE,
    )
    return result


def mosfet_transfer_data(result: SimulationResult) -> dict[str, np.ndarray]:
    """把真实扫描结果整理成 ``vgs / vds / id / ig`` 数组。"""
    data = result.data
    required = ("sweep_v", "drain_v", "gate_v", "vdd_branch_current_a", "vgg_branch_current_a")
    missing = [name for name in required if name not in data.columns]
    if missing:
        raise ValueError(f"MOSFET transfer result missing columns: {missing}")
    return {
        "sweep_v": data["sweep_v"].to_numpy(dtype=float),
        "vgs_v": data["gate_v"].to_numpy(dtype=float),
        "vds_v": data["drain_v"].to_numpy(dtype=float),
        "id_a": -data["vdd_branch_current_a"].to_numpy(dtype=float),
        "ig_a": -data["vgg_branch_current_a"].to_numpy(dtype=float),
    }


def mosfet_output_data(result: SimulationResult) -> dict[str, np.ndarray]:
    """把真实输出特性整理成 ``vds / id`` 数组。"""
    data = result.data
    required = ("sweep_v", "drain_v", "gate_v", "vdd_branch_current_a")
    missing = [name for name in required if name not in data.columns]
    if missing:
        raise ValueError(f"MOSFET output result missing columns: {missing}")
    return {
        "sweep_v": data["sweep_v"].to_numpy(dtype=float),
        "vds_v": data["drain_v"].to_numpy(dtype=float),
        "vgs_v": data["gate_v"].to_numpy(dtype=float),
        "id_a": -data["vdd_branch_current_a"].to_numpy(dtype=float),
    }


def diode_data(result: SimulationResult) -> dict[str, np.ndarray]:
    """把真实二极管扫描整理成 ``vd / id`` 数组。"""
    data = result.data
    required = ("sweep_v", "anode_v", "vdd_branch_current_a")
    missing = [name for name in required if name not in data.columns]
    if missing:
        raise ValueError(f"diode result missing columns: {missing}")
    return {
        "sweep_v": data["sweep_v"].to_numpy(dtype=float),
        "vd_v": data["anode_v"].to_numpy(dtype=float),
        "id_a": -data["vdd_branch_current_a"].to_numpy(dtype=float),
    }
