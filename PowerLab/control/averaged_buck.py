"""平均状态空间 Buck 模型（理想与非理想、连续导通模式）。

平均模型是控制设计工具，不是开关级波形：
它给出逐周期平均的 ``iL``、``vC``、``Vout``，不能替代 SPICE 开关波形。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from circuits.validators import finite_number, nonnegative_number, positive_number

LOAD_TYPES = ("resistive", "constant_current")


@dataclass(frozen=True)
class AveragedBuckParameters:
    """平均模型参数（SI 单位）。"""

    vin_v: float = 12.0
    inductance_h: float = 47e-6
    capacitance_f: float = 100e-6
    load_resistance_ohm: float = 2.5
    dcr_ohm: float = 0.05
    esr_ohm: float = 0.03
    rds_on_ohm: float = 0.0
    diode_forward_v: float = 0.0
    load_type: str = "resistive"
    load_current_a: float = 0.0
    switching_frequency_hz: float = 100_000.0

    def __post_init__(self) -> None:
        positive_number(self.vin_v, "averaged.vin_v")
        positive_number(self.inductance_h, "averaged.inductance_h")
        positive_number(self.capacitance_f, "averaged.capacitance_f")
        positive_number(self.load_resistance_ohm, "averaged.load_resistance_ohm")
        nonnegative_number(self.dcr_ohm, "averaged.dcr_ohm")
        nonnegative_number(self.esr_ohm, "averaged.esr_ohm")
        nonnegative_number(self.rds_on_ohm, "averaged.rds_on_ohm")
        nonnegative_number(self.diode_forward_v, "averaged.diode_forward_v")
        if self.load_type not in LOAD_TYPES:
            raise ValueError(f"load_type must be one of {LOAD_TYPES}")
        if self.load_type == "constant_current":
            finite_number(self.load_current_a, "averaged.load_current_a")
            if self.load_current_a < 0:
                raise ValueError("load_current_a must be nonnegative")
        positive_number(
            self.switching_frequency_hz, "averaged.switching_frequency_hz"
        )
        if self.rds_on_ohm >= self.load_resistance_ohm:
            raise ValueError("rds_on_ohm is unrealistically large for the load")

    @property
    def period_s(self) -> float:
        return 1.0 / self.switching_frequency_hz

    def output_voltage(self, il: float, vc: float, load_current: float | None = None) -> float:
        """由电感电流与电容电压求输出端电压（含 ESR 压降）。"""
        if self.load_type == "resistive":
            return (vc + self.esr_ohm * il) / (1.0 + self.esr_ohm / self.load_resistance_ohm)
        current = self.load_current_a if load_current is None else load_current
        return vc + self.esr_ohm * (il - current)

    def to_dict(self) -> dict[str, Any]:
        return {
            "vin_v": self.vin_v,
            "inductance_h": self.inductance_h,
            "capacitance_f": self.capacitance_f,
            "load_resistance_ohm": self.load_resistance_ohm,
            "dcr_ohm": self.dcr_ohm,
            "esr_ohm": self.esr_ohm,
            "rds_on_ohm": self.rds_on_ohm,
            "diode_forward_v": self.diode_forward_v,
            "load_type": self.load_type,
            "load_current_a": self.load_current_a,
            "switching_frequency_hz": self.switching_frequency_hz,
            "model_source": "averaged_model",
        }


@dataclass(frozen=True)
class AveragedOperatingPoint:
    duty: float
    inductor_current_a: float
    capacitor_voltage_v: float
    output_voltage_v: float
    delta_inductor_current_a: float
    valley_current_a: float
    continuous_conduction: bool


def _validate_state(il: float, vc: float) -> tuple[float, float]:
    return (
        finite_number(il, "inductor_current_a"),
        finite_number(vc, "capacitor_voltage_v"),
    )


def buck_derivatives(
    inductor_current_a: float,
    capacitor_voltage_v: float,
    duty: float,
    parameters: AveragedBuckParameters,
    *,
    load_current_a: float | None = None,
) -> tuple[float, float]:
    """理想平均模型导数 ``(diL/dt, dvC/dt)``。"""
    il, vc = _validate_state(inductor_current_a, capacitor_voltage_v)
    d = finite_number(duty, "duty")
    if not 0.0 <= d <= 1.0:
        raise ValueError("duty must be within [0, 1]")
    vout = parameters.output_voltage(il, vc, load_current_a)
    di = (d * parameters.vin_v - vout) / parameters.inductance_h
    if parameters.load_type == "resistive":
        ic = il - vout / parameters.load_resistance_ohm
    else:
        current = parameters.load_current_a if load_current_a is None else load_current_a
        ic = il - finite_number(current, "load_current_a")
    return di, ic / parameters.capacitance_f


def nonideal_derivatives(
    inductor_current_a: float,
    capacitor_voltage_v: float,
    duty: float,
    parameters: AveragedBuckParameters,
    *,
    load_current_a: float | None = None,
) -> tuple[float, float]:
    """非理想平均模型：开关导通电阻、二极管正向压降、电感 DCR、电容 ESR。"""
    il, vc = _validate_state(inductor_current_a, capacitor_voltage_v)
    d = finite_number(duty, "duty")
    if not 0.0 <= d <= 1.0:
        raise ValueError("duty must be within [0, 1]")
    vout = parameters.output_voltage(il, vc, load_current_a)
    series_drop = il * (d * parameters.rds_on_ohm + parameters.dcr_ohm)
    voltage = (
        d * parameters.vin_v
        - (1.0 - d) * parameters.diode_forward_v
        - series_drop
        - vout
    )
    di = voltage / parameters.inductance_h
    if parameters.load_type == "resistive":
        ic = il - vout / parameters.load_resistance_ohm
    else:
        current = parameters.load_current_a if load_current_a is None else load_current_a
        ic = il - finite_number(current, "load_current_a")
    return di, ic / parameters.capacitance_f


def operating_point(
    duty: float,
    parameters: AveragedBuckParameters,
    *,
    load_current_a: float | None = None,
    nonideal: bool = True,
) -> AveragedOperatingPoint:
    """解析稳态工作点（CCM 假设）。"""
    d = finite_number(duty, "duty")
    if not 0.0 <= d <= 1.0:
        raise ValueError("duty must be within [0, 1]")

    if parameters.load_type == "resistive":
        load = parameters.load_resistance_ohm
        if not nonideal:
            vout = d * parameters.vin_v
            il = vout / load
        else:
            numerator = d * parameters.vin_v - (1.0 - d) * parameters.diode_forward_v
            denominator = 1.0 + (d * parameters.rds_on_ohm + parameters.dcr_ohm) / load
            vout = numerator / denominator
            il = vout / load
    else:
        il = (
            parameters.load_current_a
            if load_current_a is None
            else finite_number(load_current_a, "load_current_a")
        )
        if not nonideal:
            vout = d * parameters.vin_v
        else:
            vout = (
                d * parameters.vin_v
                - (1.0 - d) * parameters.diode_forward_v
                - il * (d * parameters.rds_on_ohm + parameters.dcr_ohm)
            )
    delta = (parameters.vin_v - vout) * d * parameters.period_s / parameters.inductance_h
    valley = il - 0.5 * delta
    return AveragedOperatingPoint(
        duty=d,
        inductor_current_a=il,
        capacitor_voltage_v=vout,
        output_voltage_v=vout,
        delta_inductor_current_a=delta,
        valley_current_a=valley,
        continuous_conduction=valley > 0.0,
    )


def linearize(
    parameters: AveragedBuckParameters,
    duty: float,
    *,
    nonideal: bool = True,
    load_current_a: float | None = None,
    perturbation: float = 1e-6,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """数值雅可比线性化，返回 ``(A, B, C, D)``（状态 ``[iL, vC]``，输入 duty）。"""
    op = operating_point(duty, parameters, load_current_a=load_current_a, nonideal=nonideal)
    x0 = np.array([op.inductor_current_a, op.capacitor_voltage_v], dtype=float)
    d0 = op.duty
    derivative = nonideal_derivatives if nonideal else buck_derivatives

    def f(state: np.ndarray, d: float) -> np.ndarray:
        di, dv = derivative(
            state[0], state[1], d, parameters, load_current_a=load_current_a
        )
        return np.array([di, dv], dtype=float)

    a = np.zeros((2, 2), dtype=float)
    for j in range(2):
        step = perturbation * max(1.0, abs(x0[j]))
        xp = x0.copy()
        xm = x0.copy()
        xp[j] += step
        xm[j] -= step
        a[:, j] = (f(xp, d0) - f(xm, d0)) / (2.0 * step)
    step_d = perturbation
    b = ((f(x0, d0 + step_d) - f(x0, d0 - step_d)) / (2.0 * step_d)).reshape(2, 1)

    if parameters.load_type == "resistive":
        scale = 1.0 + parameters.esr_ohm / parameters.load_resistance_ohm
        c = np.array([[parameters.esr_ohm / scale, 1.0 / scale]], dtype=float)
    else:
        c = np.array([[parameters.esr_ohm, 1.0]], dtype=float)
    d_matrix = np.zeros((1, 1), dtype=float)
    return a, b, c, d_matrix


def ccm_check(
    inductor_current_a: float,
    output_voltage_v: float,
    duty: float,
    parameters: AveragedBuckParameters,
) -> tuple[float, float, bool]:
    """返回 ``(纹波峰峰值, 谷值电流, 是否 CCM)``。"""
    il = finite_number(inductor_current_a, "inductor_current_a")
    vout = finite_number(output_voltage_v, "output_voltage_v")
    d = finite_number(duty, "duty")
    delta = (parameters.vin_v - vout) * d * parameters.period_s / parameters.inductance_h
    valley = il - 0.5 * delta
    return abs(delta), valley, valley > 0.0
