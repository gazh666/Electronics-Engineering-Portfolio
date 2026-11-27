"""输入电压扰动：直流与阶跃（PWL）输入源。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySpice.Spice.Netlist import Circuit

from circuits.validators import finite_number, nonnegative_number, positive_number


@dataclass(frozen=True)
class LineStepCase:
    """输入电压阶跃工况。"""

    name: str
    vin_initial_v: float
    vin_final_v: float
    step_time_s: float
    release_time_s: float | None = None
    transition_s: float = 2e-5
    vin_restore_v: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("line case name must be a non-empty string")
        initial = positive_number(self.vin_initial_v, "line.vin_initial_v")
        final = positive_number(self.vin_final_v, "line.vin_final_v")
        nonnegative_number(self.step_time_s, "line.step_time_s")
        positive_number(self.transition_s, "line.transition_s")
        if self.release_time_s is not None:
            nonnegative_number(self.release_time_s, "line.release_time_s")
            if self.release_time_s <= self.step_time_s:
                raise ValueError("release_time_s must exceed step_time_s")
        if self.vin_restore_v is not None:
            positive_number(self.vin_restore_v, "line.vin_restore_v")

    @property
    def is_dc(self) -> bool:
        return (
            self.vin_initial_v == self.vin_final_v
            and self.release_time_s is None
            and self.vin_restore_v is None
        )

    def pwl_points(self, end_time_s: float) -> list[tuple[float, float]]:
        end = positive_number(end_time_s, "end_time_s")
        if self.is_dc:
            return [(0.0, self.vin_initial_v), (end, self.vin_initial_v)]
        points: list[tuple[float, float]] = [(0.0, self.vin_initial_v)]
        points.append((self.step_time_s, self.vin_initial_v))
        points.append((self.step_time_s + self.transition_s, self.vin_final_v))
        if self.release_time_s is not None:
            restore = self.vin_restore_v if self.vin_restore_v is not None else self.vin_initial_v
            points.append((self.release_time_s, self.vin_final_v))
            points.append((self.release_time_s + self.transition_s, restore))
        if end <= points[-1][0]:
            raise ValueError("end_time_s must exceed the last line transition")
        points.append((end, points[-1][1]))
        return points

    def vin_at(self, time_s: float) -> float:
        points = self.pwl_points(max(time_s, 1e-12) + 1.0)
        time = finite_number(time_s, "time_s")
        if time <= points[0][0]:
            return points[0][1]
        for (t0, v0), (t1, v1) in zip(points, points[1:]):
            if t0 <= time <= t1:
                if t1 == t0:
                    return v1
                return v0 + (v1 - v0) * (time - t0) / (t1 - t0)
        return points[-1][1]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "vin_initial_v": self.vin_initial_v,
            "vin_final_v": self.vin_final_v,
            "vin_restore_v": self.vin_restore_v,
            "step_time_s": self.step_time_s,
            "release_time_s": self.release_time_s,
            "transition_s": self.transition_s,
            "is_dc": self.is_dc,
        }


def nominal_line_case(vin_v: float = 12.0) -> LineStepCase:
    """无扰动直流输入（用 0.1 µs 的 PWL 保持与工作点一致）。"""
    return LineStepCase(
        name="nominal",
        vin_initial_v=vin_v,
        vin_final_v=vin_v,
        step_time_s=1e-3,
        transition_s=1e-7,
    )


def add_input_source(
    circuit: Circuit,
    case: LineStepCase,
    end_time_s: float,
    *,
    vin_node: str = "vin",
    ground_node: str | None = None,
    name: str = "VIN",
) -> dict[str, Any]:
    """添加输入源；直流工况使用理想直流源。"""
    ground = circuit.gnd if ground_node is None else ground_node
    if case.is_dc:
        circuit.V(name, vin_node, ground, case.vin_initial_v)
        return {
            "source": name,
            "mode": "dc",
            "vin_v": case.vin_initial_v,
            "case": case.to_dict(),
        }
    points = case.pwl_points(end_time_s)
    circuit.PieceWiseLinearVoltageSource(name, vin_node, ground, values=points)
    return {
        "source": name,
        "mode": "pwl",
        "pwl_points": points,
        "case": case.to_dict(),
    }


def line_cases() -> tuple[LineStepCase, LineStepCase]:
    """默认输入阶跃工况：上跳与下跳（各带释放）。"""
    return (
        LineStepCase(
            name="vin_step_up",
            vin_initial_v=10.0,
            vin_final_v=14.0,
            step_time_s=5e-3,
            release_time_s=None,
        ),
        LineStepCase(
            name="vin_step_down",
            vin_initial_v=12.0,
            vin_final_v=9.0,
            step_time_s=5e-3,
            release_time_s=None,
        ),
    )
