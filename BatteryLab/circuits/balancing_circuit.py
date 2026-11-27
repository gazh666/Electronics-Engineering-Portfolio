"""被动均衡支路真实 ngspice 电路：电阻 + 均衡 MOSFET。

每节电芯跨接 ``Rbal + Rds_on``，由 3.3 V 逻辑驱动。用 0 V 串联源读取真实支路
电流，避免用节点电压反推。三节初始电压不同，验证高电压单体先被选中时的电流与
电阻功耗。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from PySpice.Spice.Netlist import Circuit

from circuits.spice_utils import run_operating_point, save_netlist
from protection.limits import ProtectionLimits


class BalancingSpiceError(RuntimeError):
    """均衡电路求解失败。"""


@dataclass(frozen=True)
class BalancingSpiceChannel:
    cell_id: str
    enabled: bool
    cell_voltage_v: float
    branch_current_a: float
    resistor_power_w: float
    mosfet_power_w: float
    resistor_temperature_c: float

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True)
class BalancingSpiceResult:
    channels: tuple[BalancingSpiceChannel, ...]
    total_current_a: float
    total_power_w: float
    delta_cell_voltage_v: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "channels": [channel.to_dict() for channel in self.channels],
            "total_current_a": self.total_current_a,
            "total_power_w": self.total_power_w,
            "delta_cell_voltage_v": self.delta_cell_voltage_v,
        }


def build_balancing_circuit(
    limits: ProtectionLimits,
    cell_voltages_v: Sequence[float],
    enabled: Sequence[bool],
) -> Circuit:
    if len(cell_voltages_v) != 3 or len(enabled) != 3:
        raise BalancingSpiceError("本电路固定为 3 节")
    circuit = Circuit("BatteryLab passive balancing")
    # 电芯：n3 -> n2 -> n1 -> gnd。
    circuit.V("V3", "n3", "n2", float(cell_voltages_v[2]))
    circuit.V("V2", "n2", "n1", float(cell_voltages_v[1]))
    circuit.V("V1", "n1", circuit.gnd, float(cell_voltages_v[0]))
    circuit.V("CTRL", "ctrl", circuit.gnd, 3.3)
    for index, on in enumerate(enabled, start=1):
        top = {1: "n1", 2: "n2", 3: "n3"}[index]
        bottom = {1: circuit.gnd, 2: "n1", 3: "n2"}[index]
        circuit.V(f"EN{index}", f"ctrl{index}", circuit.gnd, 3.3 if on else 0.0)
        circuit.V(f"BC{index}", top, f"b{index}a", 0.0)
        circuit.R(f"B{index}", f"b{index}a", f"b{index}b", limits.balance_resistor_ohm)
        circuit.S(
            f"BS{index}", f"b{index}b", bottom, f"ctrl{index}", circuit.gnd, model="BAL_SW"
        )
    circuit.model("BAL_SW", "SW", VT=1.65, VH=0.0, RON=limits.balance_mosfet_rds_on_ohm, ROFF=1e9)
    return circuit


def run_balancing_spice(
    limits: ProtectionLimits,
    cell_voltages_v: Sequence[float],
    enabled: Sequence[bool] | None = None,
) -> BalancingSpiceResult:
    if enabled is None:
        enabled = [
            float(value) >= limits.balance_start_cell_voltage_v for value in cell_voltages_v
        ]
    circuit = build_balancing_circuit(limits, cell_voltages_v, enabled)
    nodes = run_operating_point(
        circuit,
        ("n1", "n2", "n3"),
        branches=("VBC1", "VBC2", "VBC3"),
    )
    cell_voltages = [
        nodes["n1"] - 0.0,
        nodes["n2"] - nodes["n1"],
        nodes["n3"] - nodes["n2"],
    ]
    channels: list[BalancingSpiceChannel] = []
    ambient = limits.balance_ambient_temperature_c
    for index, cell_voltage in enumerate(cell_voltages, start=1):
        current = float(nodes.get(f"I:vbc{index}", 0.0))
        resistor_power = current * current * limits.balance_resistor_ohm
        mosfet_power = current * current * limits.balance_mosfet_rds_on_ohm
        channels.append(
            BalancingSpiceChannel(
                cell_id=f"cell{index}",
                enabled=bool(enabled[index - 1]),
                cell_voltage_v=float(cell_voltage),
                branch_current_a=current,
                resistor_power_w=resistor_power,
                mosfet_power_w=mosfet_power,
                resistor_temperature_c=ambient
                + resistor_power * limits.balance_resistor_thermal_resistance_c_per_w,
            )
        )
    return BalancingSpiceResult(
        channels=tuple(channels),
        total_current_a=float(sum(channel.branch_current_a for channel in channels)),
        total_power_w=float(
            sum(channel.resistor_power_w + channel.mosfet_power_w for channel in channels)
        ),
        delta_cell_voltage_v=float(max(cell_voltages) - min(cell_voltages)),
    )


def save_balancing_netlist(limits: ProtectionLimits, path) -> Any:
    return save_netlist(
        build_balancing_circuit(limits, (4.05, 4.12, 4.18), (False, False, True)), path
    )
