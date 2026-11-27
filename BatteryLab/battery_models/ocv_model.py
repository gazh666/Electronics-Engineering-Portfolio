"""OCV 模型：固定 OCV 基准与教学 OCV-SOC 分段线性查表。"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from battery_models.parameters import CONFIG_DIR, ParameterError, load_yaml


class OcvError(ValueError):
    """OCV 模型参数或查询非法。"""


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise OcvError(f"{name} 不允许使用布尔值")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise OcvError(f"{name} 必须是数值") from exc
    if not math.isfinite(number):
        raise OcvError(f"{name} 必须是有限数值")
    return number


@dataclass(frozen=True)
class ConstantOcvModel:
    """固定 OCV 基准实验模型，用于独立验证 RC 动态公式。"""

    voltage_v: float = 3.8
    source_type: str = "constant_ocv_benchmark"

    def __post_init__(self) -> None:
        object.__setattr__(self, "voltage_v", _finite(self.voltage_v, "固定 OCV"))

    def voltage(self, soc: float) -> float:
        _finite(soc, "SOC")
        return self.voltage_v

    def metadata(self) -> dict[str, Any]:
        return {
            "ocv_model": "constant_ocv_benchmark",
            "voltage_v": self.voltage_v,
            "source_type": self.source_type,
        }


@dataclass(frozen=True)
class TableOcvModel:
    """SOC-OCV 分段线性插值表。

    查表必须覆盖 [0, 1]，禁止无提示外推。
    """

    soc_table: tuple[float, ...]
    ocv_table: tuple[float, ...]
    source_type: str = "educational_assumption"

    def __post_init__(self) -> None:
        soc_values = tuple(_finite(value, "SOC 表项") for value in self.soc_table)
        ocv_values = tuple(_finite(value, "OCV 表项") for value in self.ocv_table)
        if len(soc_values) < 2:
            raise OcvError("OCV 查表至少需要两个点")
        if len(soc_values) != len(ocv_values):
            raise OcvError("SOC 表与 OCV 表长度不一致")
        if not all(b > a for a, b in zip(soc_values, soc_values[1:])):
            raise OcvError("SOC 表必须严格递增")
        if soc_values[0] > 0.0 or soc_values[-1] < 1.0:
            raise OcvError("OCV 查表必须覆盖 SOC 0 至 1，禁止外推")
        object.__setattr__(self, "soc_table", soc_values)
        object.__setattr__(self, "ocv_table", ocv_values)

    def voltage(self, soc: float) -> float:
        soc_value = _finite(soc, "SOC")
        if not 0.0 <= soc_value <= 1.0:
            raise OcvError("SOC 超出 0 至 1 范围")
        return float(np.interp(soc_value, np.asarray(self.soc_table), np.asarray(self.ocv_table)))

    def metadata(self) -> dict[str, Any]:
        return {
            "ocv_model": "table_interpolation",
            "source_type": self.source_type,
            "soc_table": list(self.soc_table),
            "ocv_table_v": list(self.ocv_table),
        }


@dataclass(frozen=True)
class IdentifiedOcvModel:
    """由公开实验辨识得到的 OCV-SOC 查表模型。

    与 ``TableOcvModel`` 的区别是携带数据来源元数据（电芯型号、样品、温度、方向、
    原始文件哈希、SOC 有效范围），并可选 PCHIP 保形插值用于对照。
    """

    soc_table: tuple[float, ...]
    ocv_table: tuple[float, ...]
    metadata_info: dict[str, Any] = field(default_factory=dict)
    interpolation: str = "piecewise_linear"
    source_type: str = "identified_ocv_curve"

    def __post_init__(self) -> None:
        soc_values = tuple(_finite(value, "SOC 表项") for value in self.soc_table)
        ocv_values = tuple(_finite(value, "OCV 表项") for value in self.ocv_table)
        if len(soc_values) < 2 or len(soc_values) != len(ocv_values):
            raise OcvError("OCV 查表长度非法")
        if not all(b > a for a, b in zip(soc_values, soc_values[1:])):
            raise OcvError("SOC 表必须严格递增")
        if soc_values[0] != 0.0 or soc_values[-1] != 1.0:
            raise OcvError("辨识 OCV 表必须显式覆盖 SOC 0 与 1")
        if self.interpolation not in ("piecewise_linear", "pchip"):
            raise OcvError("插值方式只能是 piecewise_linear 或 pchip")
        object.__setattr__(self, "soc_table", soc_values)
        object.__setattr__(self, "ocv_table", ocv_values)
        if self.interpolation == "pchip":
            from scipy.interpolate import PchipInterpolator

            object.__setattr__(
                self, "_pchip", PchipInterpolator(np.asarray(soc_values), np.asarray(ocv_values))
            )

    def voltage(self, soc: float) -> float:
        soc_value = _finite(soc, "SOC")
        if not 0.0 <= soc_value <= 1.0:
            raise OcvError("SOC 超出 0 至 1 范围，禁止外推")
        if self.interpolation == "pchip":
            return float(self._pchip(soc_value))
        return float(np.interp(soc_value, np.asarray(self.soc_table), np.asarray(self.ocv_table)))

    def metadata(self) -> dict[str, Any]:
        payload = {
            "ocv_model": "identified_ocv_curve",
            "source_type": self.source_type,
            "interpolation": self.interpolation,
            "soc_table_points": len(self.soc_table),
            "soc_min": self.soc_table[0],
            "soc_max": self.soc_table[-1],
        }
        payload.update(self.metadata_info)
        return payload


def load_identified_ocv(csv_path: str | Path, interpolation: str = "piecewise_linear") -> IdentifiedOcvModel:
    """从 ``soc,ocv_v`` CSV 读取已辨识 OCV 曲线。"""
    import csv

    target = Path(csv_path)
    if not target.exists():
        raise OcvError(f"OCV 曲线文件不存在: {target}")
    soc_values: list[float] = []
    ocv_values: list[float] = []
    with target.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            soc_values.append(float(row["soc"]))
            ocv_values.append(float(row["ocv_v"]))
    return IdentifiedOcvModel(
        tuple(soc_values),
        tuple(ocv_values),
        metadata_info={"source_file": str(target)},
        interpolation=interpolation,
    )


def interpolate_ocv(soc: float, soc_table: Sequence[float], ocv_table: Sequence[float]) -> float:
    """独立插值函数（供测试与文档引用）。"""
    return TableOcvModel(tuple(float(v) for v in soc_table), tuple(float(v) for v in ocv_table)).voltage(soc)


def load_ocv_reference(path: str | Path | None = None) -> TableOcvModel:
    target = Path(path) if path is not None else CONFIG_DIR / "ocv_reference.yaml"
    raw = load_yaml(target)
    try:
        soc_values = raw["soc"]
        ocv_values = raw["ocv_v"]
    except KeyError as exc:
        raise ParameterError(f"OCV 配置缺少字段: {exc}") from exc
    if not isinstance(soc_values, Sequence) or not isinstance(ocv_values, Sequence):
        raise ParameterError("OCV 配置的 soc / ocv_v 必须是序列")
    return TableOcvModel(tuple(soc_values), tuple(ocv_values), str(raw.get("source_type", "educational_assumption")))
