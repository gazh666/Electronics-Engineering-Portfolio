"""电池端口适配：把第三阶段真实辨识ECM包装成系统级电气端口。

数据来源：

- 参数：``results/identification/run_identification_20261126_125603_622eba/identified_parameters.csv``
  （CALCE INR18650-20R SP2，25 ℃，DST 工况辨识）
- OCV：``results/ocv/run_ocv_20261126_124813_24e8d1/ocv_soc.csv``

辨识 SOC 有效区间为 0.0106–0.5068。超过该区间时参数属于外推，必须由调用方
标记 ``SOC_OUTSIDE_IDENTIFIED_WINDOW``，本适配层不会自动"修正"该事实。
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Sequence

from battery_models.battery_pack import SeriesBatteryPack, build_inconsistent_pack
from battery_models.ocv_model import IdentifiedOcvModel
from battery_models.parameters import CellParameters, PROJECT_ROOT, RCBranch, load_yaml

DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "system_config.yaml"


class BatteryPortError(ValueError):
    """电池端口输入非法。"""


def load_system_config(path: str | Path | None = None) -> dict[str, Any]:
    return load_yaml(path or DEFAULT_CONFIG)


def load_identified_parameters(csv_path: str | Path) -> dict[str, dict[str, Any]]:
    target = Path(csv_path)
    if not target.is_absolute():
        target = PROJECT_ROOT / target
    if not target.is_file():
        raise BatteryPortError(f"辨识参数文件不存在: {target}")
    records: dict[str, dict[str, Any]] = {}
    with target.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            order = int(float(row["model_order"]))
            key = {0: "rint", 1: "first_order_rc", 2: "second_order_rc"}[order]
            record: dict[str, Any] = {}
            for name, value in row.items():
                try:
                    record[name] = None if value == "" else float(value)
                except (TypeError, ValueError):
                    record[name] = value
            records[key] = record
    if not records:
        raise BatteryPortError("辨识参数文件为空")
    return records


def load_identified_ocv(path: str | Path) -> IdentifiedOcvModel:
    target = Path(path)
    if not target.is_absolute():
        target = PROJECT_ROOT / target
    if not target.is_file():
        raise BatteryPortError(f"OCV 曲线文件不存在: {target}")
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or len(payload) < 2:
        raise BatteryPortError("OCV 曲线格式非法")
    soc = tuple(float(item["soc"]) for item in payload)
    ocv = tuple(float(item["ocv_v"]) for item in payload)
    return IdentifiedOcvModel(soc, ocv, metadata_info={"source_file": str(target)})


@dataclass(frozen=True)
class BatteryPortState:
    effective_voltage_v: float
    total_series_resistance_ohm: float
    socs: tuple[float, ...]
    polarization_voltage_sum_v: float
    identified_soc_min: float
    identified_soc_max: float

    @property
    def inside_identified_window(self) -> bool:
        return all(self.identified_soc_min <= soc <= self.identified_soc_max for soc in self.socs)


@dataclass(frozen=True)
class TerminalState:
    pack_voltage_v: float
    cell_voltages_v: tuple[float, ...]
    pack_ohmic_loss_w: float
    pack_polarization_loss_w: float

    @property
    def minimum_cell_voltage_v(self) -> float:
        return min(self.cell_voltages_v)

    @property
    def internal_loss_w(self) -> float:
        return self.pack_ohmic_loss_w + self.pack_polarization_loss_w


class BatteryPort:
    """3S1P 电池组端口；放电电流为正。"""

    def __init__(
        self,
        pack: SeriesBatteryPack,
        *,
        path_resistance_ohm: float = 0.052,
        identified_soc_min: float = 0.0,
        identified_soc_max: float = 1.0,
        parameter_source: str = "identified_parameters",
    ) -> None:
        if path_resistance_ohm < 0:
            raise BatteryPortError("通路电阻必须非负")
        self.pack = pack
        self.path_resistance_ohm = float(path_resistance_ohm)
        self.identified_soc_min = float(identified_soc_min)
        self.identified_soc_max = float(identified_soc_max)
        self.parameter_source = parameter_source

    # ------------------------------------------------------------ state
    def polarization_sum_v(self) -> float:
        return float(
            sum(sum(cell.state.polarization_voltages_v) for cell in self.pack.cells)
        )

    def ocv_sum_v(self) -> float:
        return float(sum(cell.ocv_v() for cell in self.pack.cells))

    def get_port_state(self) -> BatteryPortState:
        return BatteryPortState(
            effective_voltage_v=self.ocv_sum_v() - self.polarization_sum_v(),
            total_series_resistance_ohm=self.pack.total_r0_ohm() + self.path_resistance_ohm,
            socs=self.pack.socs,
            polarization_voltage_sum_v=self.polarization_sum_v(),
            identified_soc_min=self.identified_soc_min,
            identified_soc_max=self.identified_soc_max,
        )

    def calculate_terminal_state(self, current_a: float) -> TerminalState:
        if not math.isfinite(current_a):
            raise BatteryPortError("电流必须为有限数值")
        return TerminalState(
            pack_voltage_v=self.pack.pack_voltage(current_a),
            cell_voltages_v=self.pack.cell_voltages(current_a),
            pack_ohmic_loss_w=self.pack.pack_ohmic_loss_w(current_a),
            pack_polarization_loss_w=self.pack.pack_polarization_loss_w(),
        )

    def advance(self, current_a: float, dt_s: float) -> None:
        if dt_s <= 0:
            raise BatteryPortError("步长必须为正")
        self.pack.step(current_a, dt_s)

    @property
    def socs(self) -> tuple[float, ...]:
        return self.pack.socs

    @property
    def cell_ids(self) -> tuple[str, ...]:
        return tuple(cell.cell_id for cell in self.pack.cells)

    def cell_parameters(self) -> tuple[CellParameters, ...]:
        return tuple(cell.parameters for cell in self.pack.cells)

    def capacity_ah(self) -> tuple[float, ...]:
        return tuple(cell.parameters.capacity_ah for cell in self.pack.cells)


def build_battery_port(
    *,
    initial_soc: Sequence[float] | None = None,
    capacities_ah: Sequence[float] | None = None,
    r0_scale: float = 1.0,
    r0_ohm: Sequence[float] | None = None,
    model_order: str = "first_order_rc",
    path_resistance_ohm: float = 0.052,
    config_path: str | Path | None = None,
) -> BatteryPort:
    """按真实辨识参数构造 3S 电池端口（默认参数不做任何"美化"）。"""
    config = load_system_config(config_path)
    battery = config["battery"]
    parameters = load_identified_parameters(battery["parameter_source_file"])
    if model_order not in parameters:
        raise BatteryPortError(f"辨识结果没有 {model_order} 模型")
    row = parameters[model_order]
    ocv_model = load_identified_ocv(battery["ocv_source_file"])

    capacity_default = float(row["capacity_ah"])
    soc_values = list(initial_soc if initial_soc is not None else battery["initial_soc"])
    if len(soc_values) != int(battery["series_cells"]):
        raise BatteryPortError("初始 SOC 数量必须等于串联节数")
    if any(not 0.0 <= value <= 1.0 for value in soc_values):
        raise BatteryPortError("初始 SOC 必须位于 0 至 1")

    branches: list[RCBranch] = []
    if model_order in ("first_order_rc", "second_order_rc"):
        branches.append(RCBranch(float(row["r1_ohm"]), float(row["c1_f"])))
    if model_order == "second_order_rc":
        branches.append(RCBranch(float(row["r2_ohm"]), float(row["c2_f"])))

    base_r0 = float(row["r0_ohm"]) * float(r0_scale)
    if r0_ohm is not None:
        base_r0 = float(r0_ohm[0])
    resolved_capacity = capacity_default if capacities_ah is not None else capacity_default

    from battery_models.parameters import ECMModelDefinition

    definition = ECMModelDefinition(
        name=model_order,
        parameters=CellParameters(
            capacity_ah=resolved_capacity,
            r0_ohm=base_r0,
            label="cell1",
            parameter_source="identified_parameters",
            temperature_c=float(row["temperature_c"]),
        ),
        branches=tuple(branches),
        parameter_source="identified_parameters",
    )
    pack = build_inconsistent_pack(
        definition,
        ocv_model,
        socs=soc_values,
        capacities_ah=list(capacities_ah) if capacities_ah is not None else None,
        r0_ohm=list(r0_ohm) if r0_ohm is not None else None,
    )
    return BatteryPort(
        pack,
        path_resistance_ohm=path_resistance_ohm,
        identified_soc_min=float(battery["identified_soc_min"]),
        identified_soc_max=float(battery["identified_soc_max"]),
        parameter_source="identified_parameters",
    )


def cell_ecm_parameters(port: BatteryPort) -> list[dict[str, float]]:
    """导出每节电芯的 SPICE 用参数（OCV 冻结在初始 SOC）。"""
    payload: list[dict[str, float]] = []
    for cell in port.pack.cells:
        payload.append(
            {
                "ocv_v": cell.ocv_v(),
                "r0_ohm": cell.parameters.r0_ohm,
                "rp_ohm": cell.branches[0].resistance_ohm if cell.branches else 1e9,
                "cp_f": cell.branches[0].capacitance_f if cell.branches else 1e-12,
                "initial_polarization_v": float(sum(cell.state.polarization_voltages_v)),
                "soc": cell.state.soc,
                "capacity_ah": cell.parameters.capacity_ah,
            }
        )
    return payload


__all__ = [
    "BatteryPort",
    "BatteryPortState",
    "BatteryPortError",
    "TerminalState",
    "build_battery_port",
    "cell_ecm_parameters",
    "load_identified_ocv",
    "load_identified_parameters",
    "load_system_config",
]
