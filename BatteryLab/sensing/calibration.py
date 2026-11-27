"""零点校准与两点校准（Task 25）。

校准模型：``y = gain * x + offset``，其中 x 为真实输入，y 为测量读数。
校准后恢复：``x_estimated = (y - offset) / gain``。

严格区分校准集与独立验证集：校准系数只能由预先指定的校准点计算，
验证点不得参与重新拟合。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence


class CalibrationError(ValueError):
    """校准输入非法。"""


def _real(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise CalibrationError(f"{name} 必须是有限数值")
    return float(value)


@dataclass(frozen=True)
class CalibrationModel:
    gain: float
    offset: float
    kind: str = "identity"
    reference_points: tuple[tuple[float, float], ...] = field(default_factory=tuple)
    calibration_id: str = ""

    def __post_init__(self) -> None:
        if not math.isfinite(self.gain) or self.gain == 0.0:
            raise CalibrationError("校准增益必须为非零有限值")
        if not math.isfinite(self.offset):
            raise CalibrationError("校准失调必须为有限值")

    def apply(self, measured_value: float) -> float:
        return (_real(measured_value, "测量值") - self.offset) / self.gain

    def forward(self, reference_value: float) -> float:
        return self.gain * _real(reference_value, "参考值") + self.offset

    @property
    def is_identity(self) -> bool:
        return abs(self.gain - 1.0) <= 1e-15 and abs(self.offset) <= 1e-15

    def as_dict(self) -> dict[str, float | str | list]:
        return {
            "gain": self.gain,
            "offset": self.offset,
            "kind": self.kind,
            "reference_points": [list(point) for point in self.reference_points],
            "calibration_id": self.calibration_id,
        }


def identity_calibration(calibration_id: str = "") -> CalibrationModel:
    return CalibrationModel(gain=1.0, offset=0.0, kind="identity", calibration_id=calibration_id)


def fit_zero_calibration(measured_zero: float, calibration_id: str = "zero") -> CalibrationModel:
    """零点校准：offset = 真实 0 输入时的读数，增益固定为 1。"""
    offset = _real(measured_zero, "零输入读数")
    return CalibrationModel(
        gain=1.0,
        offset=offset,
        kind="zero",
        reference_points=((0.0, offset),),
        calibration_id=calibration_id,
    )


def fit_two_point_calibration(
    reference_1: float,
    measured_1: float,
    reference_2: float,
    measured_2: float,
    calibration_id: str = "two_point",
) -> CalibrationModel:
    """两点校准：a = (y2-y1)/(x2-x1)，b = y1 - a*x1。

    注意这里 gain 是"输出/输入"的斜率；应用时取逆。
    """
    x1 = _real(reference_1, "参考点1")
    x2 = _real(reference_2, "参考点2")
    y1 = _real(measured_1, "测量点1")
    y2 = _real(measured_2, "测量点2")
    if abs(x2 - x1) <= 1e-15:
        raise CalibrationError("两个校准参考点不能相同")
    gain = (y2 - y1) / (x2 - x1)
    if abs(gain) <= 1e-15:
        raise CalibrationError("两点校准增益接近 0")
    offset = y1 - gain * x1
    return CalibrationModel(
        gain=gain,
        offset=offset,
        kind="two_point",
        reference_points=((x1, y1), (x2, y2)),
        calibration_id=calibration_id,
    )


def apply_calibration(measured_value: float, gain: float, offset: float) -> float:
    model = CalibrationModel(gain=gain, offset=offset)
    return model.apply(measured_value)


def calibration_error_report(
    references: Sequence[float],
    measured: Sequence[float],
    model: CalibrationModel,
) -> dict[str, float]:
    if len(references) != len(measured) or not references:
        raise CalibrationError("参考值与测量值必须等长且非空")
    errors = [model.apply(value) - ref for ref, value in zip(references, measured)]
    absolute = [abs(value) for value in errors]
    count = len(errors)
    return {
        "count": float(count),
        "mean_error": sum(errors) / count,
        "mae": sum(absolute) / count,
        "rmse": math.sqrt(sum(value * value for value in errors) / count),
        "max_abs_error": max(absolute),
    }
