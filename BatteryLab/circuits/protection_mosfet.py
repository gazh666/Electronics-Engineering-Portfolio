"""真实 ngspice 背靠背 N 沟道 MOSFET 充放电保护开关。

拓扑（低边、共源）：

```text
BATT_N ──D  CHG-FET  S──┬──S  DSG-FET  D── PACK_N
                        │
                       CS（共源节点）
```

CHG 管体二极管只允许充电方向，DSG 管体二极管只允许放电方向；两只同时关断
才能双向阻断。网表使用 ngspice 的 level-1 MOS 模型（含真实体二极管方向），
开关管参数来自 ``configs/protection_config.yaml``。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
from PySpice.Spice.Netlist import Circuit

from circuits.spice_utils import run_operating_point, run_transient, save_netlist
from protection.limits import ProtectionLimits

MOSFET_MODEL_NAME = "NMOS_PROTECTION"

# 每节电芯的串联内阻与开路电压（第三阶段冻结参数，教学夹具）。
CELL_R0_OHM = 0.077068
DEFAULT_CELL_OCV_V = 4.05


class ProtectionSpiceError(RuntimeError):
    """保护开关真实求解失败。"""


@dataclass(frozen=True)
class SwitchOperatingPoint:
    """一种开关组合下的稳态结果。"""

    case: str
    description: str
    charge_fet_on: bool
    discharge_fet_on: bool
    load_ohm: float | None
    charger_voltage_v: float | None
    pack_voltage_v: float
    pack_current_a: float
    switch_current_a: float
    switch_drop_v: float
    switch_resistance_ohm: float
    switch_loss_w: float
    load_current_a: float
    charge_current_a: float
    node_voltages_v: dict[str, float]

    @property
    def blocked(self) -> bool:
        return abs(self.switch_current_a) <= 1e-3

    def to_dict(self) -> dict[str, Any]:
        return {
            "case": self.case,
            "description": self.description,
            "charge_fet_on": self.charge_fet_on,
            "discharge_fet_on": self.discharge_fet_on,
            "load_ohm": self.load_ohm,
            "charger_voltage_v": self.charger_voltage_v,
            "pack_voltage_v": self.pack_voltage_v,
            "pack_current_a": self.pack_current_a,
            "switch_current_a": self.switch_current_a,
            "switch_drop_v": self.switch_drop_v,
            "switch_resistance_ohm": self.switch_resistance_ohm,
            "switch_loss_w": self.switch_loss_w,
            "load_current_a": self.load_current_a,
            "charge_current_a": self.charge_current_a,
            "node_voltages_v": self.node_voltages_v,
        }


def _add_cell_stack(circuit: Circuit, limits: ProtectionLimits, cell_ocv_v: float) -> None:
    """三节串联：每节一个 OCV 源与一个欧姆内阻。"""
    r0 = CELL_R0_OHM
    circuit.R("R3", "PACK_P", "t3", r0)
    circuit.V("V3", "t3", "n2", cell_ocv_v)
    circuit.R("R2", "n2", "t2", r0)
    circuit.V("V2", "t2", "n1", cell_ocv_v)
    circuit.R("R1", "n1", "t1", r0)
    circuit.V("V1", "t1", "BATT_N", cell_ocv_v)


def build_back_to_back_circuit(
    limits: ProtectionLimits,
    *,
    charge_fet_on: bool,
    discharge_fet_on: bool,
    load_ohm: float | None = None,
    charger_voltage_v: float | None = None,
    charger_resistance_ohm: float = 0.5,
    cell_ocv_v: float = DEFAULT_CELL_OCV_V,
    gate_step_s: float | None = None,
    gate_initial_on: bool = False,
) -> Circuit:
    """构造背靠背保护开关网表。

    ``gate_step_s`` 非空时，对应的栅极在此时刻由 ``gate_initial_on`` 切换到目标状态，
    用于真实瞬态切断实验。
    """
    circuit = Circuit("BatteryLab back-to-back protection switch")
    _add_cell_stack(circuit, limits, cell_ocv_v)

    circuit.MOSFET("CHG", "BATT_N", "g_chg", "CS", "CS", model=MOSFET_MODEL_NAME)
    circuit.MOSFET("DSG", circuit.gnd, "g_dsg", "CS", "CS", model=MOSFET_MODEL_NAME)
    circuit.model(
        MOSFET_MODEL_NAME,
        "NMOS",
        LEVEL=1,
        VTO=2.5,
        KP=20.0,
        LAMBDA=0.01,
        RD=limits.drain_access_resistance_ohm,
        RS=limits.source_access_resistance_ohm,
        IS=limits.body_diode_saturation_current_a,
        CGSO=1e-9,
        CGDO=1e-9,
    )

    # 栅极驱动：10 V 相对共源节点，10 Ω 栅极电阻 + 100 kΩ 下拉。
    for name, on, node in (("CHG", charge_fet_on, "g_chg"), ("DSG", discharge_fet_on, "g_dsg")):
        control_node = f"ctrl_{name.lower()}"
        if gate_step_s is None:
            circuit.V(f"CTRL{name}", control_node, circuit.gnd, 1.0 if on else 0.0)
        else:
            initial = 1.0 if gate_initial_on else 0.0
            final = 1.0 if on else 0.0
            circuit.PulseVoltageSource(
                f"CTRL{name}",
                control_node,
                circuit.gnd,
                initial_value=initial,
                pulsed_value=final,
                delay_time=gate_step_s,
                rise_time=100e-9,
                fall_time=100e-9,
                pulse_width=1.0,
                period=2.0,
            )
        circuit.VCVS(f"DRV{name}", node, "CS", control_node, circuit.gnd, limits.gate_drive_voltage_v)
        circuit.R(f"G{name}", node, "CS", limits.gate_resistance_ohm)
        circuit.R(f"GS{name}", node, "CS", limits.gate_pulldown_ohm)

    if load_ohm is not None:
        circuit.V("IL", "PACK_P", "load_top", 0.0)
        circuit.R("LOAD", "load_top", circuit.gnd, load_ohm)
    if charger_voltage_v is not None:
        circuit.V("CHG_SRC", "chg_top", circuit.gnd, charger_voltage_v)
        circuit.R("CHG_R", "chg_top", "chg_r2", charger_resistance_ohm)
        circuit.V("IC", "chg_r2", "PACK_P", 0.0)
    # CS 在双管关断时浮空，1 GΩ 仅定义直流参考，电流 < 12 nA。
    circuit.R("CSREF", "CS", circuit.gnd, 1e9)
    return circuit


# PACK_N 作为 SPICE 参考地（节点 0），避免整个电池组浮空导致伪收敛失败。
NODES = ("PACK_P", "BATT_N", "CS", "g_chg", "g_dsg")


def _operating_case(
    limits: ProtectionLimits,
    *,
    case: str,
    description: str,
    charge_fet_on: bool,
    discharge_fet_on: bool,
    load_ohm: float | None,
    charger_voltage_v: float | None,
    cell_ocv_v: float = DEFAULT_CELL_OCV_V,
) -> SwitchOperatingPoint:
    circuit = build_back_to_back_circuit(
        limits,
        charge_fet_on=charge_fet_on,
        discharge_fet_on=discharge_fet_on,
        load_ohm=load_ohm,
        charger_voltage_v=charger_voltage_v,
        cell_ocv_v=cell_ocv_v,
    )
    branches: tuple[str, ...] = ()
    if load_ohm is not None:
        branches += ("VIL",)
    if charger_voltage_v is not None:
        branches += ("VIC",)
    nodes = run_operating_point(circuit, NODES, branches=branches)
    pack_p = nodes["PACK_P"]
    batt_n = nodes["BATT_N"]
    load_current = float(nodes.get("I:vil", 0.0))
    charge_current = float(nodes.get("I:vic", 0.0))
    # 放电为正：负载电流减去充入电池的电流。
    pack_current = load_current - charge_current
    switch_current = pack_current
    switch_drop = abs(batt_n)
    resistance = switch_drop / abs(switch_current) if abs(switch_current) > 1e-9 else float("inf")
    loss = switch_drop * abs(switch_current)
    return SwitchOperatingPoint(
        case=case,
        description=description,
        charge_fet_on=charge_fet_on,
        discharge_fet_on=discharge_fet_on,
        load_ohm=load_ohm,
        charger_voltage_v=charger_voltage_v,
        pack_voltage_v=float(pack_p),
        pack_current_a=pack_current,
        switch_current_a=switch_current,
        switch_drop_v=switch_drop,
        switch_resistance_ohm=resistance,
        switch_loss_w=loss,
        load_current_a=load_current,
        charge_current_a=charge_current,
        node_voltages_v={key: float(value) for key, value in nodes.items()},
    )


def run_switch_case_matrix(limits: ProtectionLimits) -> list[SwitchOperatingPoint]:
    """七个必需工况：导通、双向阻断与输入掉电回灌。"""
    cases = [
        dict(
            case="CASE_A_BOTH_ON_DISCHARGE",
            description="两管导通，2 Ω 负载放电约 1 A",
            charge_fet_on=True,
            discharge_fet_on=True,
            load_ohm=11.8,
            charger_voltage_v=None,
        ),
        dict(
            case="CASE_B_BOTH_ON_CHARGE",
            description="两管导通，12.6 V 充电",
            charge_fet_on=True,
            discharge_fet_on=True,
            load_ohm=None,
            charger_voltage_v=12.6,
        ),
        dict(
            case="CASE_C_CHG_OFF_BLOCK_CHARGE",
            description="充电管关断，充电方向应被阻断",
            charge_fet_on=False,
            discharge_fet_on=True,
            load_ohm=None,
            charger_voltage_v=12.6,
        ),
        dict(
            case="CASE_D_DSG_OFF_BLOCK_DISCHARGE",
            description="放电管关断，放电方向应被阻断",
            charge_fet_on=True,
            discharge_fet_on=False,
            load_ohm=11.8,
            charger_voltage_v=None,
        ),
        dict(
            case="CASE_E_BOTH_OFF_LEAKAGE",
            description="两管关断，12.6 V 充电源下的反向漏电",
            charge_fet_on=False,
            discharge_fet_on=False,
            load_ohm=None,
            charger_voltage_v=12.6,
        ),
        dict(
            case="CASE_F_INPUT_COLLAPSE_BOTH_ON",
            description="输入掉电至 0 V，两管仍导通，电池向输入回灌",
            charge_fet_on=True,
            discharge_fet_on=True,
            load_ohm=None,
            charger_voltage_v=0.0,
        ),
        dict(
            case="CASE_G_INPUT_COLLAPSE_DSG_OFF",
            description="输入掉电至 0 V，放电管关断，回灌被阻断",
            charge_fet_on=True,
            discharge_fet_on=False,
            load_ohm=None,
            charger_voltage_v=0.0,
        ),
    ]
    return [_operating_case(limits, **case) for case in cases]


@dataclass(frozen=True)
class TurnOffWaveform:
    time_s: np.ndarray
    discharge_current_a: np.ndarray
    gate_voltage_v: np.ndarray
    switch_voltage_v: np.ndarray
    current_cutoff_time_s: float | None

    def summary(self) -> dict[str, Any]:
        return {
            "points": int(self.time_s.size),
            "peak_current_a": float(np.max(np.abs(self.discharge_current_a))),
            "final_current_a": float(self.discharge_current_a[-1]),
            "current_cutoff_time_s": self.current_cutoff_time_s,
        }


def run_turn_off_transient(
    limits: ProtectionLimits,
    *,
    step_s: float = 2e-7,
    end_s: float = 2e-6,
    gate_step_s: float = 5e-7,
    load_ohm: float = 11.8,
) -> TurnOffWaveform:
    """两管同时关断的真实瞬态：观察电流切断过程与栅极电压。"""
    circuit = build_back_to_back_circuit(
        limits,
        charge_fet_on=False,
        discharge_fet_on=False,
        load_ohm=load_ohm,
        gate_step_s=gate_step_s,
        gate_initial_on=True,
    )
    data = run_transient(
        circuit,
        duration_s=end_s,
        step_s=step_s,
        max_step_s=step_s,
        nodes=("BATT_N", "g_dsg", "g_chg", "load_top", "CS"),
        branches=("VIL",),
        reltol=1e-4,
        abstol=1e-9,
        vntol=1e-6,
    )
    time_array = data["time_s"]
    current = data["I:vil"]
    switch_voltage = -data["BATT_N"]
    gate = data["g_dsg"] - data["CS"]
    # 切断时刻：电流降到峰值 5% 以下的第一点。
    peak = float(np.max(np.abs(current))) if current.size else 0.0
    cutoff: float | None = None
    if peak > 1e-6:
        below = np.where(np.abs(current) < 0.05 * peak)[0]
        if below.size:
            cutoff = float(time_array[below[0]])
    return TurnOffWaveform(
        time_s=time_array,
        discharge_current_a=current,
        gate_voltage_v=gate,
        switch_voltage_v=switch_voltage,
        current_cutoff_time_s=cutoff,
    )


def persist_switch_results(
    limits: ProtectionLimits,
    cases: list[SwitchOperatingPoint],
    transient: TurnOffWaveform,
    directory: Path,
) -> dict[str, Path]:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    circuit = build_back_to_back_circuit(
        limits,
        charge_fet_on=True,
        discharge_fet_on=True,
        load_ohm=11.8,
        charger_voltage_v=12.6,
    )
    netlist_path = save_netlist(circuit, directory / "protection_switch.cir")
    return {"netlist": netlist_path}


SwitchSide = Literal["charge", "discharge"]


