"""Level 1 增强型 N 沟道 MOSFET 教学模型构建。

模型来源为 ``educational_assumption``：平方律 Level 1 模型 + 固定外部寄生电容，
不是经过验证的商业功率 MOSFET 模型。

四个端口：Drain / Gate / Source / Bulk。本阶段体端与源极相连，
因此体二极管方向为「源极（阳极）→ 漏极（阴极）」，高侧位置时处于反偏。
"""

from __future__ import annotations

from typing import Any

from PySpice.Spice.Netlist import Circuit

from .nonideal_config import MosfetModelConfig

#: 默认 MOSFET 器件实例名（网表中显示为 M1）。
DEFAULT_MOSFET_INSTANCE = "1"


def _node_name(value: object, name: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(f"{name} must be a non-empty node name")
    text = str(value).strip()
    if not text:
        raise ValueError(f"{name} must be a non-empty node name")
    return text


def add_educational_nmos(
    circuit: Circuit,
    config: MosfetModelConfig,
    drain_node: str,
    gate_node: str,
    source_node: str,
    *,
    name: str = DEFAULT_MOSFET_INSTANCE,
    bulk_node: str | None = None,
    model_name: str | None = None,
) -> str:
    """写入 Level 1 NMOS 模型与器件实例，返回模型名。

    ``bulk_node`` 为空时体端接源极（本阶段默认）。
    """
    if not isinstance(circuit, Circuit):
        raise ValueError("circuit must be a PySpice Circuit")
    if not isinstance(config, MosfetModelConfig):
        raise ValueError("config must be MosfetModelConfig")
    drain = _node_name(drain_node, "drain_node")
    gate = _node_name(gate_node, "gate_node")
    source = _node_name(source_node, "source_node")
    bulk = source if bulk_node is None else _node_name(bulk_node, "bulk_node")
    instance = str(name).strip()
    if not instance:
        raise ValueError("MOSFET instance name must be a non-empty string")
    model = str(model_name or config.model_name).strip()
    if not model:
        raise ValueError("MOSFET model name must be a non-empty string")

    circuit.model(
        model,
        "NMOS",
        LEVEL=config.level,
        VTO=config.threshold_voltage_v,
        KP=config.kp_a_per_v2,
        LAMBDA=config.channel_length_modulation_per_v,
        RD=config.drain_resistance_ohm,
        RS=config.source_resistance_ohm,
        GAMMA=0,
    )
    circuit.M(
        instance,
        drain,
        gate,
        source,
        bulk,
        model=model,
        w=config.channel_width_m,
        l=config.channel_length_m,
    )
    return model


def add_mosfet_parasitic_capacitors(
    circuit: Circuit,
    config: MosfetModelConfig,
    drain_node: str,
    gate_node: str,
    source_node: str,
) -> dict[str, float]:
    """在 MOSFET 外部添加简化常值 Cgs / Cgd / Cds，返回实际写入的电容值。

    这些电容是常值教学近似，不等于真实器件的非线性 Ciss / Coss / Crss；
    为了避免重复建模，本阶段不在模型内部再声明结电容参数。
    """
    if not isinstance(circuit, Circuit):
        raise ValueError("circuit must be a PySpice Circuit")
    if not isinstance(config, MosfetModelConfig):
        raise ValueError("config must be MosfetModelConfig")
    drain = _node_name(drain_node, "drain_node")
    gate = _node_name(gate_node, "gate_node")
    source = _node_name(source_node, "source_node")

    written: dict[str, float] = {}
    if config.external_cgs_f > 0:
        circuit.C("GS", gate, source, config.external_cgs_f)
        written["cgs_f"] = config.external_cgs_f
    if config.external_cgd_f > 0:
        circuit.C("GD", gate, drain, config.external_cgd_f)
        written["cgd_f"] = config.external_cgd_f
    if config.external_cds_f > 0:
        circuit.C("DS", drain, source, config.external_cds_f)
        written["cds_f"] = config.external_cds_f
    return written


def mosfet_metadata(config: MosfetModelConfig) -> dict[str, Any]:
    """导出模型元数据，用于结果目录中的模型说明。"""
    if not isinstance(config, MosfetModelConfig):
        raise ValueError("config must be MosfetModelConfig")
    return {
        "device": "N-channel enhancement MOSFET (Level 1)",
        "model_name": config.model_name,
        "model_source": config.model_source,
        "model_version": config.model_version,
        "bulk_connection": "source (body diode anode at source, cathode at drain)",
        "spice_parameters": config.spice_parameters(),
        "instance_geometry": {
            "width_m": config.channel_width_m,
            "length_m": config.channel_length_m,
            "width_over_length": config.width_over_length,
        },
        "external_capacitances_f": {
            "cgs": config.external_cgs_f,
            "cgd": config.external_cgd_f,
            "cds": config.external_cds_f,
        },
        "limitations": [
            "square-law Level 1 model, not a validated commercial power MOSFET",
            "constant external capacitances, not bias-dependent Ciss/Coss/Crss",
            "no thermal network, no avalanche or SOA model",
        ],
    }
