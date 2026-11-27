"""无源寄生参数模型：电感 DCR 与电容 ESR。

拓扑约定::

    L1  节点 in  → l_dcr           (理想电感)
    RDCR l_dcr  → out              (绕组直流电阻，DCR = 0 时省略)

    RESR out → cap_internal        (等效串联电阻，ESR = 0 时省略)
    C1   cap_internal → 参考节点    (理想电容)

``dcr_ohm`` / ``esr_ohm`` 为 0 时不写入 0 欧姆电阻，而是用理想导线连接，
避免向 ngspice 注入不受控的零欧姆电阻。
"""

from __future__ import annotations

from PySpice.Spice.Netlist import Circuit

from .nonideal_config import CapacitorModelConfig, InductorModelConfig


def _node(value: object, name: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(f"{name} must be a non-empty node name")
    text = str(value).strip()
    if not text:
        raise ValueError(f"{name} must be a non-empty node name")
    return text


def add_inductor_with_dcr(
    circuit: Circuit,
    config: InductorModelConfig,
    input_node: str,
    output_node: str,
    *,
    name: str = "1",
    internal_node: str = "l_dcr",
) -> dict[str, str]:
    """写入「理想电感 + 串联 DCR」，返回实际节点映射。

    ``dcr_ohm == 0`` 时电感直接连接 ``input_node`` 与 ``output_node``，
    返回的 ``inductor_output_node`` 等于 ``output_node``。
    """
    if not isinstance(circuit, Circuit):
        raise ValueError("circuit must be a PySpice Circuit")
    if not isinstance(config, InductorModelConfig):
        raise ValueError("config must be InductorModelConfig")
    node_in = _node(input_node, "input_node")
    node_out = _node(output_node, "output_node")
    instance = str(name).strip()
    if not instance:
        raise ValueError("inductor instance name must be a non-empty string")

    if config.dcr_ohm > 0:
        middle = _node(internal_node, "internal_node")
        if middle in (node_in, node_out):
            raise ValueError("inductor internal node must differ from its terminals")
        circuit.L(instance, node_in, middle, config.inductance_h)
        circuit.R("DCR", middle, node_out, config.dcr_ohm)
        return {
            "inductor_input_node": node_in,
            "inductor_output_node": middle,
            "dcr_input_node": middle,
            "dcr_output_node": node_out,
            "dcr_ohm": config.dcr_ohm,
        }

    circuit.L(instance, node_in, node_out, config.inductance_h)
    return {
        "inductor_input_node": node_in,
        "inductor_output_node": node_out,
        "dcr_input_node": node_out,
        "dcr_output_node": node_out,
        "dcr_ohm": 0.0,
    }


def add_capacitor_with_esr(
    circuit: Circuit,
    config: CapacitorModelConfig,
    output_node: str,
    reference_node: str,
    *,
    name: str = "1",
    internal_node: str = "cap_internal",
) -> dict[str, str]:
    """写入「串联 ESR + 理想电容」，返回实际节点映射。

    ``esr_ohm == 0`` 时电容直接连接 ``output_node`` 与 ``reference_node``，
    返回的 ``capacitor_internal_node`` 等于 ``output_node``。
    """
    if not isinstance(circuit, Circuit):
        raise ValueError("circuit must be a PySpice Circuit")
    if not isinstance(config, CapacitorModelConfig):
        raise ValueError("config must be CapacitorModelConfig")
    node_out = _node(output_node, "output_node")
    reference = _node(reference_node, "reference_node")
    instance = str(name).strip()
    if not instance:
        raise ValueError("capacitor instance name must be a non-empty string")

    if config.esr_ohm > 0:
        middle = _node(internal_node, "internal_node")
        if middle in (node_out, reference):
            raise ValueError("capacitor internal node must differ from its terminals")
        circuit.R("ESR", node_out, middle, config.esr_ohm)
        circuit.C(instance, middle, reference, config.capacitance_f)
        return {
            "esr_input_node": node_out,
            "esr_output_node": middle,
            "capacitor_internal_node": middle,
            "capacitor_reference_node": reference,
            "esr_ohm": config.esr_ohm,
        }

    circuit.C(instance, node_out, reference, config.capacitance_f)
    return {
        "esr_input_node": node_out,
        "esr_output_node": node_out,
        "capacitor_internal_node": node_out,
        "capacitor_reference_node": reference,
        "esr_ohm": 0.0,
    }
