"""传递函数工具：理想/非理想 Buck 控制到输出传函、零极点与频响。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np

from circuits.validators import finite_number, positive_number

from .averaged_buck import AveragedBuckParameters, linearize


@dataclass(frozen=True)
class TransferFunction:
    """连续时间传递函数 ``num(s)/den(s)``（系数按降幂排列）。"""

    num: np.ndarray
    den: np.ndarray

    def __post_init__(self) -> None:
        num = np.atleast_1d(np.asarray(self.num, dtype=float))
        den = np.atleast_1d(np.asarray(self.den, dtype=float))
        if den.size == 0 or np.allclose(den, 0.0):
            raise ValueError("denominator must be nonzero")
        object.__setattr__(self, "num", num)
        object.__setattr__(self, "den", den)

    def evaluate(self, s: complex | np.ndarray) -> np.ndarray:
        return np.polyval(self.num, s) / np.polyval(self.den, s)

    def frequency_response(self, frequencies_hz: np.ndarray) -> np.ndarray:
        omega = 2.0 * np.pi * np.asarray(frequencies_hz, dtype=float)
        return self.evaluate(1j * omega)

    @property
    def dc_gain(self) -> float:
        return float(self.evaluate(0.0).real)

    @property
    def poles(self) -> np.ndarray:
        return np.roots(self.den)

    @property
    def zeros(self) -> np.ndarray:
        trimmed = np.trim_zeros(self.num, "f")
        if trimmed.size <= 1:
            return np.empty(0, dtype=complex)
        return np.roots(trimmed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "numerator": [float(v) for v in self.num],
            "denominator": [float(v) for v in self.den],
            "dc_gain": self.dc_gain,
            "poles": [[float(p.real), float(p.imag)] for p in self.poles],
            "zeros": [[float(z.real), float(z.imag)] for z in self.zeros],
        }


def _pad(num: np.ndarray, den: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    n = max(num.size, den.size)
    return (
        np.concatenate((np.zeros(n - num.size), num)),
        np.concatenate((np.zeros(n - den.size), den)),
    )


def from_state_space(
    a: np.ndarray, b: np.ndarray, c: np.ndarray, d: np.ndarray
) -> TransferFunction:
    """由单输入单输出状态空间构造传递函数。"""
    a = np.atleast_2d(np.asarray(a, dtype=float))
    b = np.asarray(b, dtype=float).reshape(-1, 1)
    c = np.asarray(c, dtype=float).reshape(1, -1)
    d = np.asarray(d, dtype=float).reshape(1, 1)
    n = a.shape[0]
    # C (sI − A)^-1 B + D，用多项式矩阵求值避免额外依赖。
    identity = np.eye(n)
    coefficients = np.zeros(n + 1, dtype=float)
    # 特征多项式 det(sI − A)，降幂。
    characteristic = np.poly(a)
    # 分子：对若干频点拟合不现实，改用 scipy 的 ss2tf（若可用）。
    try:
        from scipy.signal import ss2tf

        num, den = ss2tf(a, b, c, d)
        return TransferFunction(np.asarray(num[0], dtype=float), np.asarray(den, dtype=float))
    except Exception:  # noqa: BLE001 - 回退到解析二阶形式
        # 仅支持 2 阶系统的解析展开。
        if n != 2:
            raise
        a11, a12 = a[0, 0], a[0, 1]
        a21, a22 = a[1, 0], a[1, 1]
        c1, c2 = c[0, 0], c[0, 1]
        d0 = float(d[0, 0])
        # num = D s² + (C B − D tr(A)) s + (D det(A) + C adj(-A) B)
        n2 = d0
        n1 = float(c @ b) - d0 * (a11 + a22)
        adj = np.array([[a22, -a12], [-a21, a11]], dtype=float)
        n0 = d0 * float(np.linalg.det(a)) + float(c @ adj @ b)
        coefficients[:] = [n2, n1, n0]
        return TransferFunction(coefficients, characteristic)


def ideal_buck_control_to_output(
    vin_v: float, inductance_h: float, capacitance_f: float, load_resistance_ohm: float
) -> TransferFunction:
    """理想 Buck 占空比到输出电压：Vin / (LC s² + (L/R)s + 1)。"""
    vin = positive_number(vin_v, "vin_v")
    inductance = positive_number(inductance_h, "inductance_h")
    capacitance = positive_number(capacitance_f, "capacitance_f")
    resistance = positive_number(load_resistance_ohm, "load_resistance_ohm")
    return TransferFunction(
        np.array([vin]),
        np.array([inductance * capacitance, inductance / resistance, 1.0]),
    )


def nonideal_buck_control_to_output(
    parameters: AveragedBuckParameters, duty: float
) -> tuple[TransferFunction, dict[str, Any]]:
    """非理想平均模型的数值线性化传函（含 DCR/ESR/RDS/VF）。"""
    a, b, c, d = linearize(parameters, duty)
    transfer = from_state_space(a, b, c, d)
    metadata = {
        "a_matrix": a.tolist(),
        "b_matrix": b.tolist(),
        "c_matrix": c.tolist(),
        "d_matrix": d.tolist(),
        "linearization_point": {"duty": float(duty)},
        "method": "numeric_jacobian",
        "model_source": "averaged_model",
    }
    return transfer, metadata


def natural_frequency_rad_s(inductance_h: float, capacitance_f: float) -> float:
    return 1.0 / math.sqrt(
        positive_number(inductance_h, "inductance_h")
        * positive_number(capacitance_f, "capacitance_f")
    )


def natural_frequency_hz(inductance_h: float, capacitance_f: float) -> float:
    return natural_frequency_rad_s(inductance_h, capacitance_f) / (2.0 * math.pi)


def damping_ratio(
    inductance_h: float, capacitance_f: float, load_resistance_ohm: float
) -> float:
    """理想 LC + 电阻负载的阻尼比 ζ = (1/2R)·sqrt(L/C)。"""
    inductance = positive_number(inductance_h, "inductance_h")
    capacitance = positive_number(capacitance_f, "capacitance_f")
    resistance = positive_number(load_resistance_ohm, "load_resistance_ohm")
    return 0.5 / resistance * math.sqrt(inductance / capacitance)


def quality_factor(
    inductance_h: float, capacitance_f: float, load_resistance_ohm: float
) -> float:
    return 1.0 / (2.0 * damping_ratio(inductance_h, capacitance_f, load_resistance_ohm))


def esr_zero_hz(capacitance_f: float, esr_ohm: float) -> float:
    capacitance = positive_number(capacitance_f, "capacitance_f")
    esr = positive_number(esr_ohm, "esr_ohm")
    return 1.0 / (2.0 * math.pi * esr * capacitance)


def frequency_grid(
    start_hz: float = 1.0, stop_hz: float = 1e6, points_per_decade: int = 60
) -> np.ndarray:
    start = positive_number(start_hz, "start_hz")
    stop = positive_number(stop_hz, "stop_hz")
    if stop <= start:
        raise ValueError("stop_hz must exceed start_hz")
    decades = math.log10(stop / start)
    count = max(2, int(round(decades * points_per_decade)) + 1)
    return np.logspace(math.log10(start), math.log10(stop), count)


def cascade(*stages: TransferFunction) -> TransferFunction:
    num = np.array([1.0])
    den = np.array([1.0])
    for stage in stages:
        num = np.polymul(num, stage.num)
        den = np.polymul(den, stage.den)
    return TransferFunction(num, den)


def evaluate_many(
    transfer: TransferFunction, frequencies_hz: Iterable[float]
) -> tuple[np.ndarray, np.ndarray]:
    response = transfer.frequency_response(np.asarray(list(frequencies_hz), dtype=float))
    magnitude_db = 20.0 * np.log10(np.maximum(np.abs(response), 1e-30))
    phase_deg = np.degrees(np.unwrap(np.angle(response)))
    return magnitude_db, phase_deg


def is_stable_transfer(transfer: TransferFunction, tolerance: float = 1e-9) -> bool:
    return bool(np.all(np.real(transfer.poles) < -tolerance))


def finite_number_check(value: float, name: str) -> float:
    return finite_number(value, name)
