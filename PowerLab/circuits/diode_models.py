"""非理想续流二极管模型构建。

``D`` 模型参数：IS / N / RS / CJO / VJ / M / TT。
低储存电荷教学模型，不等同于任何真实肖特基二极管数据手册模型。
"""

from __future__ import annotations

from typing import Any

from PySpice.Spice.Netlist import Circuit

from .nonideal_config import DiodeModelConfig

#: 默认续流二极管实例名（网表中显示为 DFREE）。
DEFAULT_DIODE_INSTANCE = "FREE"


def add_nonideal_diode(
    circuit: Circuit,
    config: DiodeModelConfig,
    anode_node: str,
    cathode_node: str,
    *,
    name: str = DEFAULT_DIODE_INSTANCE,
    model_name: str | None = None,
) -> str:
    """写入二极管模型与实例，返回模型名。

    正方向：阳极 → 阴极。
    """
    if not isinstance(circuit, Circuit):
        raise ValueError("circuit must be a PySpice Circuit")
    if not isinstance(config, DiodeModelConfig):
        raise ValueError("config must be DiodeModelConfig")
    if isinstance(anode_node, bool) or not isinstance(anode_node, (str, int)):
        raise ValueError("anode_node must be a non-empty node name")
    if isinstance(cathode_node, bool) or not isinstance(cathode_node, (str, int)):
        raise ValueError("cathode_node must be a non-empty node name")
    anode = str(anode_node).strip()
    cathode = str(cathode_node).strip()
    if not anode or not cathode:
        raise ValueError("diode nodes must be non-empty node names")
    instance = str(name).strip()
    if not instance:
        raise ValueError("diode instance name must be a non-empty string")
    model = str(model_name or config.model_name).strip()
    if not model:
        raise ValueError("diode model name must be a non-empty string")

    circuit.model(model, "D", **config.spice_parameters())
    circuit.D(instance, anode, cathode, model=model)
    return model


def diode_metadata(config: DiodeModelConfig) -> dict[str, Any]:
    """导出二极管模型元数据。"""
    if not isinstance(config, DiodeModelConfig):
        raise ValueError("config must be DiodeModelConfig")
    return {
        "device": "freewheeling diode",
        "model_name": config.model_name,
        "model_source": config.model_source,
        "model_version": config.model_version,
        "spice_parameters": config.spice_parameters(),
        "limitations": [
            "low charge-storage teaching model",
            "not a validated Schottky diode model",
            "reverse recovery (Qrr) is not physically calibrated",
        ],
    }
