"""动态负载：恒流阶跃负载与电阻阶跃负载（真实 SPICE 元件）。

恒流负载用行为电流源实现，并在输出电压低于顺应电压时按比例降流，
避免输出被理想电流源强行拉到负压；实际负载电流由真实 KCL 波形验证。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from PySpice.Spice.Netlist import Circuit

from circuits.validators import finite_number, nonnegative_number, positive_number

from .switch_models import SwitchConfig, add_switch_model

DEFAULT_LOAD_SWITCH = SwitchConfig(
    on_resistance_ohm=0.01,
    off_resistance_ohm=1e6,
    threshold_voltage_v=2.5,
    hysteresis_voltage_v=0.1,
)


@dataclass(frozen=True)
class CurrentStep:
    """恒流负载的一个台阶。"""

    time_s: float
    current_a: float

    def __post_init__(self) -> None:
        nonnegative_number(self.time_s, "load_step.time_s")
        nonnegative_number(self.current_a, "load_step.current_a")


@dataclass(frozen=True)
class CurrentStepLoad:
    """恒流阶跃负载（PWL 命令 + 顺应电压限流）。"""

    steps: tuple[CurrentStep, ...]
    transition_s: float = 1e-5
    compliance_voltage_v: float = 1.0
    initial_current_a: float = 0.0

    def __post_init__(self) -> None:
        if not self.steps:
            raise ValueError("load steps must not be empty")
        positive_number(self.transition_s, "load.transition_s")
        positive_number(self.compliance_voltage_v, "load.compliance_voltage_v")
        nonnegative_number(self.initial_current_a, "load.initial_current_a")
        times = [step.time_s for step in self.steps]
        if any(b <= a for a, b in zip(times, times[1:])):
            raise ValueError("load step times must be strictly increasing")

    @property
    def load_type(self) -> str:
        return "constant_current"

    @property
    def peak_current_a(self) -> float:
        return max([self.initial_current_a] + [s.current_a for s in self.steps])

    def pwl_points(self, end_time_s: float | None = None) -> list[tuple[float, float]]:
        """构造 (时间, 电流) 折线；每个台阶含有限过渡时间。"""
        points: list[tuple[float, float]] = [(0.0, self.initial_current_a)]
        current = self.initial_current_a
        for step in self.steps:
            if step.time_s > points[-1][0]:
                points.append((step.time_s, current))
            target_time = step.time_s + self.transition_s
            points.append((target_time, step.current_a))
            current = step.current_a
        if end_time_s is not None:
            end = finite_number(end_time_s, "end_time_s")
            if end <= points[-1][0]:
                raise ValueError("end_time_s must exceed the last load transition")
            points.append((end, current))
        return points

    def current_at(self, time_s: float) -> float:
        """折线命令电流（不含顺应限流）。"""
        points = self.pwl_points(None)
        time = finite_number(time_s, "time_s")
        if time <= points[0][0]:
            return points[0][1]
        for (t0, i0), (t1, i1) in zip(points, points[1:]):
            if t0 <= time <= t1:
                if t1 == t0:
                    return i1
                return i0 + (i1 - i0) * (time - t0) / (t1 - t0)
        return points[-1][1]

    def add_to(
        self,
        circuit: Circuit,
        output_node: str,
        ground_node: str,
        *,
        command_source_name: str = "ICMD",
        command_node: str = "icmd",
        load_name: str = "BLOAD",
        end_time_s: float | None = None,
    ) -> dict[str, Any]:
        """把恒流负载加入电路，返回布局说明。"""
        points = self.pwl_points(end_time_s)
        circuit.PieceWiseLinearVoltageSource(
            command_source_name, command_node, ground_node, values=points
        )
        compliance = self.compliance_voltage_v
        expression = (
            f"V({command_node})*min(max(V({output_node})/{compliance:.12g},0),1)"
        )
        circuit.B(load_name, output_node, ground_node, current_expression=expression)
        return {
            "load_type": "constant_current",
            "command_source": command_source_name,
            "command_node": command_node,
            "load_element": load_name,
            "expression": expression,
            "pwl_points": points,
            "compliance_voltage_v": compliance,
            "peak_current_a": self.peak_current_a,
            "transition_s": self.transition_s,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "load_type": self.load_type,
            "initial_current_a": self.initial_current_a,
            "steps": [{"time_s": s.time_s, "current_a": s.current_a} for s in self.steps],
            "transition_s": self.transition_s,
            "compliance_voltage_v": self.compliance_voltage_v,
            "peak_current_a": self.peak_current_a,
        }


@dataclass(frozen=True)
class ResistiveStepLoad:
    """电阻阶跃负载：基准电阻 + 受控开关投入的并联支路。"""

    base_resistance_ohm: float
    target_resistance_ohm: float
    step_time_s: float
    release_time_s: float
    transition_s: float = 1e-5
    switch_on_resistance_ohm: float = 0.01
    initial_connected: bool = False

    def __post_init__(self) -> None:
        base = positive_number(self.base_resistance_ohm, "load.base_resistance_ohm")
        target = positive_number(self.target_resistance_ohm, "load.target_resistance_ohm")
        if target >= base:
            raise ValueError("target_resistance_ohm must be smaller than base resistance")
        nonnegative_number(self.step_time_s, "load.step_time_s")
        nonnegative_number(self.release_time_s, "load.release_time_s")
        if self.release_time_s <= self.step_time_s:
            raise ValueError("release_time_s must exceed step_time_s")
        positive_number(self.transition_s, "load.transition_s")
        nonnegative_number(self.switch_on_resistance_ohm, "load.switch_on_resistance_ohm")
        if self.switch_on_resistance_ohm >= target:
            raise ValueError("switch on resistance must be smaller than target resistance")

    @property
    def load_type(self) -> str:
        return "resistive_step"

    @property
    def series_resistance_ohm(self) -> float:
        """并联支路串联电阻，使投入后等效电阻等于目标值。"""
        base = self.base_resistance_ohm
        target = self.target_resistance_ohm
        branch = 1.0 / (1.0 / target - 1.0 / base)
        series = branch - self.switch_on_resistance_ohm
        if series <= 0:
            raise ValueError("target resistance is too close to switch on resistance")
        return series

    def equivalent_resistance(self, connected: bool) -> float:
        if not connected:
            return self.base_resistance_ohm
        branch = self.series_resistance_ohm + self.switch_on_resistance_ohm
        return 1.0 / (1.0 / self.base_resistance_ohm + 1.0 / branch)

    def add_to(
        self,
        circuit: Circuit,
        output_node: str,
        ground_node: str,
        *,
        model_name: str = "SWLOAD",
        switch_element_name: str = "SLOAD",
        control_source_name: str = "VSTEP",
        control_node: str = "step_gate",
        base_resistor_name: str = "RLOAD",
        series_resistor_name: str = "RSTEP",
        series_node: str = "step_series",
    ) -> dict[str, Any]:
        circuit.R(base_resistor_name, output_node, ground_node, self.base_resistance_ohm)
        model = add_switch_model(circuit, DEFAULT_LOAD_SWITCH, name=model_name)
        circuit.S(
            switch_element_name,
            output_node,
            series_node,
            control_node,
            ground_node,
            model=model,
        )
        circuit.R(series_resistor_name, series_node, ground_node, self.series_resistance_ohm)

        low = 0.0
        high = 5.0
        initial = high if self.initial_connected else low
        pulse_width = max(self.release_time_s - self.step_time_s, self.transition_s)
        if self.initial_connected:
            # 初始导通：从高电平开始，在 release 时刻关断。
            circuit.PulseVoltageSource(
                control_source_name,
                control_node,
                ground_node,
                initial_value=high,
                pulsed_value=low,
                delay_time=self.release_time_s,
                rise_time=self.transition_s,
                fall_time=self.transition_s,
                pulse_width=pulse_width,
                period=1.0,
            )
        else:
            circuit.PulseVoltageSource(
                control_source_name,
                control_node,
                ground_node,
                initial_value=low,
                pulsed_value=high,
                delay_time=self.step_time_s,
                rise_time=self.transition_s,
                fall_time=self.transition_s,
                pulse_width=pulse_width,
                period=1.0,
            )
        return {
            "load_type": "resistive_step",
            "base_resistance_ohm": self.base_resistance_ohm,
            "target_resistance_ohm": self.target_resistance_ohm,
            "series_resistance_ohm": self.series_resistance_ohm,
            "switch_on_resistance_ohm": self.switch_on_resistance_ohm,
            "step_time_s": self.step_time_s,
            "release_time_s": self.release_time_s,
            "transition_s": self.transition_s,
            "initial_connected": self.initial_connected,
            "elements": [
                base_resistor_name,
                switch_element_name,
                series_resistor_name,
                control_source_name,
            ],
        }

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "load_type": self.load_type,
            "base_resistance_ohm": self.base_resistance_ohm,
            "target_resistance_ohm": self.target_resistance_ohm,
            "series_resistance_ohm": self.series_resistance_ohm,
            "step_time_s": self.step_time_s,
            "release_time_s": self.release_time_s,
            "transition_s": self.transition_s,
            "initial_connected": self.initial_connected,
        }
        return payload

    def current_at(self, time_s: float, output_voltage_v: float) -> float:
        """给定输出电压下的理想负载电流（用于文档与校验）。"""
        time = finite_number(time_s, "time_s")
        voltage = finite_number(output_voltage_v, "output_voltage_v")
        if time < self.step_time_s or time >= self.release_time_s:
            connected = self.initial_connected and time < self.release_time_s
            if time >= self.release_time_s:
                connected = False
        else:
            connected = True
        return voltage / self.equivalent_resistance(connected)


def load_from_dict(payload: dict[str, Any]) -> CurrentStepLoad | ResistiveStepLoad:
    """由 YAML 片段构造负载对象。"""
    if not isinstance(payload, dict):
        raise ValueError("load configuration must be a mapping")
    kind = payload.get("load_type", "constant_current")
    if kind == "constant_current":
        steps = tuple(
            CurrentStep(time_s=float(item["time_s"]), current_a=float(item["current_a"]))
            for item in payload.get("steps", [])
        )
        return CurrentStepLoad(
            steps=steps,
            transition_s=float(payload.get("transition_s", 1e-5)),
            compliance_voltage_v=float(payload.get("compliance_voltage_v", 1.0)),
            initial_current_a=float(payload.get("initial_current_a", 0.0)),
        )
    if kind == "resistive_step":
        return ResistiveStepLoad(
            base_resistance_ohm=float(payload["base_resistance_ohm"]),
            target_resistance_ohm=float(payload["target_resistance_ohm"]),
            step_time_s=float(payload["step_time_s"]),
            release_time_s=float(payload["release_time_s"]),
            transition_s=float(payload.get("transition_s", 1e-5)),
            switch_on_resistance_ohm=float(payload.get("switch_on_resistance_ohm", 0.01)),
            initial_connected=bool(payload.get("initial_connected", False)),
        )
    raise ValueError(f"unsupported load_type {kind!r}")
