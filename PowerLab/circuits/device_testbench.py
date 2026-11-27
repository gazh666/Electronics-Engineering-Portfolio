"""独立器件测试台电路（MOSFET 转移 / 输出 / 截止，二极管正向 / 反向）。

测试台只包含被测器件与理想扫描源，不包含 Buck 拓扑，
用于把器件特性与变换器行为分开验证。

节点约定：

- MOSFET：drain / gate / source(=gnd) / bulk(=source)
- 二极管：anode / cathode(=gnd)

扫描源名称：MOSFET 栅极 ``GG``、MOSFET 漏极 ``DD``、二极管 ``DD``。
"""

from __future__ import annotations

from PySpice.Spice.Netlist import Circuit

from .diode_models import add_nonideal_diode
from .mosfet_models import add_educational_nmos
from .nonideal_config import DiodeModelConfig, MosfetModelConfig
from .validators import finite_number, positive_number

#: 测试台扫描源名称。
SOURCE_MOSFET_GATE = "GG"
SOURCE_MOSFET_DRAIN = "DD"
SOURCE_DIODE = "DD"

#: 测试台节点名称。
NODE_DRAIN = "drain"
NODE_GATE = "gate"
NODE_ANODE = "anode"


def _fixed_source(value: float, name: str) -> float:
    return finite_number(value, name)


def build_mosfet_transfer_testbench(
    config: MosfetModelConfig,
    vds_v: float,
    *,
    title: str = "NMOS Transfer Characteristic",
) -> Circuit:
    """固定 ``VDS``，扫描 ``VGS``，测量漏极电流。"""
    if not isinstance(config, MosfetModelConfig):
        raise ValueError("config must be MosfetModelConfig")
    drain_voltage = _fixed_source(vds_v, "vds_v")
    if drain_voltage <= 0:
        raise ValueError("vds_v must be positive for the transfer testbench")

    circuit = Circuit(title)
    circuit.V("DD", NODE_DRAIN, circuit.gnd, drain_voltage)
    circuit.V("GG", NODE_GATE, circuit.gnd, 0.0)
    add_educational_nmos(circuit, config, NODE_DRAIN, NODE_GATE, circuit.gnd)
    return circuit


def build_mosfet_output_testbench(
    config: MosfetModelConfig,
    vgs_v: float,
    *,
    title: str = "NMOS Output Characteristic",
) -> Circuit:
    """固定 ``VGS``，扫描 ``VDS``，测量漏极电流。

    ``vgs_v = 0`` 时同时充当截止状态漏电流测试台。
    """
    if not isinstance(config, MosfetModelConfig):
        raise ValueError("config must be MosfetModelConfig")
    gate_voltage = _fixed_source(vgs_v, "vgs_v")

    circuit = Circuit(title)
    circuit.V("GG", NODE_GATE, circuit.gnd, gate_voltage)
    circuit.V("DD", NODE_DRAIN, circuit.gnd, 0.0)
    add_educational_nmos(circuit, config, NODE_DRAIN, NODE_GATE, circuit.gnd)
    return circuit


def build_diode_forward_testbench(
    config: DiodeModelConfig,
    *,
    title: str = "Freewheeling Diode Forward Characteristic",
) -> Circuit:
    """二极管阳极接扫描源、阴极接地，扫描正向电压。"""
    if not isinstance(config, DiodeModelConfig):
        raise ValueError("config must be DiodeModelConfig")

    circuit = Circuit(title)
    circuit.V("DD", NODE_ANODE, circuit.gnd, 0.0)
    add_nonideal_diode(circuit, config, NODE_ANODE, circuit.gnd)
    return circuit


def build_diode_reverse_testbench(
    config: DiodeModelConfig,
    *,
    title: str = "Freewheeling Diode Reverse Characteristic",
) -> Circuit:
    """与正向测试台相同的拓扑，扫描负向电压以观察反向漏电流。"""
    if not isinstance(config, DiodeModelConfig):
        raise ValueError("config must be DiodeModelConfig")
    circuit = Circuit(title)
    circuit.V("DD", NODE_ANODE, circuit.gnd, 0.0)
    add_nonideal_diode(circuit, config, NODE_ANODE, circuit.gnd)
    return circuit


def validate_sweep(start_v: float, stop_v: float, step_v: float, *, name: str) -> tuple[float, float, float]:
    """校验扫描区间与步长。"""
    start = finite_number(start_v, f"{name}.start_v")
    stop = finite_number(stop_v, f"{name}.stop_v")
    step = positive_number(step_v, f"{name}.step_v")
    if stop <= start:
        raise ValueError(f"{name}.stop_v must exceed start_v")
    if step > (stop - start):
        raise ValueError(f"{name}.step_v must not exceed the sweep span")
    return start, stop, step
