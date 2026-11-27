"""KiCad XML 网表解析。

只解析真实导出的 kicadxml 网表结构；对结构不符的输入显式报错，
不允许把未知格式当作"零器件/零网络"。
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path


def parse_kicad_xml_netlist(file_path: str | Path) -> dict:
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(path)

    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise ValueError(f"Unexpected netlist XML: {exc}") from exc

    components_node = root.find("components")
    nets_node = root.find("nets")
    if components_node is None or nets_node is None:
        raise ValueError("Unexpected netlist format")

    components: dict[str, dict] = {}
    for comp in components_node.findall("comp"):
        ref = comp.attrib.get("ref")
        if not ref:
            raise ValueError("Component without reference")
        if ref in components:
            raise ValueError(f"Duplicate reference: {ref}")
        components[ref] = {
            "value": comp.findtext("value"),
            "footprint": comp.findtext("footprint"),
        }

    pin_to_net: dict[tuple[str, str], str] = {}
    nets: dict[str, list[dict]] = {}

    for net in nets_node.findall("net"):
        net_name = net.attrib.get("name")
        if not net_name:
            raise ValueError("Net without name")
        if net_name in nets:
            raise ValueError(f"Duplicate net: {net_name}")

        nodes = []
        for node in net.findall("node"):
            ref = node.attrib.get("ref")
            pin = node.attrib.get("pin")
            if ref is None or pin is None:
                raise ValueError(f"Incomplete node in net {net_name}")

            key = (ref, pin)
            if key in pin_to_net and pin_to_net[key] != net_name:
                raise ValueError(f"Pin in multiple nets: {key}")

            pin_to_net[key] = net_name
            nodes.append(
                {
                    "reference": ref,
                    "pin_number": pin,
                    "pin_function": node.attrib.get("pinfunction"),
                }
            )

        nets[net_name] = nodes

    if not components:
        raise ValueError("Empty component list")

    return {
        "components": components,
        "nets": nets,
        "pin_to_net": pin_to_net,
    }


def summarize_netlist(netlist: dict) -> dict:
    """给出器件/网络计数与单引脚网络列表。"""
    single_pin_nets = {
        name: nodes[0]["reference"] + "." + nodes[0]["pin_number"]
        for name, nodes in netlist["nets"].items()
        if len(nodes) == 1
    }

    return {
        "component_count": len(netlist["components"]),
        "net_count": len(netlist["nets"]),
        "single_pin_net_count": len(single_pin_nets),
        "single_pin_nets": single_pin_nets,
    }
