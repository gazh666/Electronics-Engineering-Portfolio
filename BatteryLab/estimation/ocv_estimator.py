"""OCV-SOC 反向查表。

第三阶段给出 SOC→OCV 曲线；本模块负责 OCV→SOC 反演。

真实 CALCE 平均 OCV 曲线在约 89%–90% 与 99.5%–100% SOC 附近存在
非单调/平台（原始数据保留不删）。因此：

1. 原始数据完整保存；
2. 反演使用**显式单调包络**（累积最大值），并记录被调整的索引；
3. 局部斜率低于阈值时返回 ``LOW_OBSERVABILITY``，不给出 SOC；
4. 绝不外推。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

from estimation.models import EstimationError


@dataclass(frozen=True)
class OCVEstimate:
    """OCV 反演结果。"""

    soc: float | None
    local_slope_v_per_soc: float | None
    status: str


@dataclass
class OCVSOCTable:
    """可逆 OCV-SOC 查表（带单调化审计）。"""

    soc_values: Sequence[float]
    ocv_values_v: Sequence[float]
    minimum_slope: float = 0.2
    enforce_monotonic: bool = True
    monotonic_indices: tuple[int, ...] = field(default=(), init=False)
    _soc: np.ndarray = field(default=None, init=False, repr=False)
    _ocv_raw: np.ndarray = field(default=None, init=False, repr=False)
    _ocv: np.ndarray = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        soc = np.asarray(self.soc_values, dtype=float).reshape(-1)
        ocv = np.asarray(self.ocv_values_v, dtype=float).reshape(-1)
        if soc.ndim != 1 or ocv.ndim != 1:
            raise EstimationError("Invalid SOC/OCV table")
        if soc.shape != ocv.shape or soc.size < 2:
            raise EstimationError("Invalid table size")
        if not (np.isfinite(soc).all() and np.isfinite(ocv).all()):
            raise EstimationError("Non-finite table")
        if np.any(soc < 0.0) or np.any(soc > 1.0):
            raise EstimationError("SOC out of range")
        if np.any(np.diff(soc) <= 0.0):
            raise EstimationError("SOC not increasing")
        if not (math.isfinite(self.minimum_slope) and self.minimum_slope > 0.0):
            raise EstimationError("Invalid slope threshold")

        if np.any(np.diff(ocv) <= 0.0):
            if not self.enforce_monotonic:
                raise EstimationError("OCV table is not uniquely invertible")
            envelope = np.maximum.accumulate(ocv)
            indices = tuple(int(index) for index in np.where(envelope != ocv)[0])
            if np.any(np.diff(envelope) <= 0.0):
                # 顶部完全平台：给最小增量以保持可逆，同时记录为低可观测性来源。
                steps = np.arange(envelope.size, dtype=float)
                envelope = np.maximum(envelope, envelope[0] + steps * 1e-9)
            object.__setattr__(self, "monotonic_indices", indices)
            ocv = envelope

        object.__setattr__(self, "_soc", soc)
        object.__setattr__(self, "_ocv_raw", np.asarray(self.ocv_values_v, dtype=float).reshape(-1))
        object.__setattr__(self, "_ocv", ocv)

    @classmethod
    def from_ocv_model(cls, model: Any, *, points: int = 2001, minimum_slope: float = 0.2) -> "OCVSOCTable":
        """由第三阶段 OCV 模型（``voltage(soc)`` 接口）等距采样构造反查表。"""
        grid = np.linspace(0.0, 1.0, int(points))
        values = np.asarray([float(model.voltage(float(soc))) for soc in grid], dtype=float)
        return cls(grid, values, minimum_slope=minimum_slope)

    @property
    def soc_table(self) -> np.ndarray:
        return self._soc

    @property
    def ocv_table_v(self) -> np.ndarray:
        return self._ocv

    @property
    def raw_ocv_table_v(self) -> np.ndarray:
        return self._ocv_raw

    def voltage_at(self, soc: float) -> float:
        if not math.isfinite(float(soc)):
            raise EstimationError("Invalid SOC")
        if not self._soc[0] <= float(soc) <= self._soc[-1]:
            raise EstimationError("SOC outside table")
        return float(np.interp(float(soc), self._soc, self._ocv))

    def slope_at(self, soc: float) -> float:
        """局部 dOCV/dSOC（单调包络上的中心差分）。"""
        if not math.isfinite(float(soc)):
            raise EstimationError("Invalid SOC")
        if not self._soc[0] <= float(soc) <= self._soc[-1]:
            raise EstimationError("SOC outside table")
        index = int(np.searchsorted(self._soc, float(soc), side="right")) - 1
        index = min(max(index, 0), self._soc.size - 2)
        slope = (self._ocv[index + 1] - self._ocv[index]) / (self._soc[index + 1] - self._soc[index])
        return float(max(slope, 0.0))

    def slope_series(self) -> tuple[np.ndarray, np.ndarray]:
        """返回 (SOC 中点, 局部斜率)，用于平台区分析。"""
        midpoints = 0.5 * (self._soc[:-1] + self._soc[1:])
        slopes = np.diff(self._ocv) / np.diff(self._soc)
        return midpoints, slopes

    def estimate(self, voltage_v: float) -> OCVEstimate:
        if not math.isfinite(float(voltage_v)):
            return OCVEstimate(None, None, "INVALID_VOLTAGE")
        if not self._ocv[0] <= float(voltage_v) <= self._ocv[-1]:
            return OCVEstimate(None, None, "OUTSIDE_OCV_RANGE")

        index = int(np.searchsorted(self._ocv, float(voltage_v), side="right")) - 1
        index = min(max(index, 0), self._ocv.size - 2)
        slope = (self._ocv[index + 1] - self._ocv[index]) / (self._soc[index + 1] - self._soc[index])

        if slope < self.minimum_slope:
            return OCVEstimate(None, float(slope), "LOW_OBSERVABILITY")

        estimated_soc = float(np.interp(float(voltage_v), self._ocv, self._soc))
        return OCVEstimate(estimated_soc, float(slope), "VALID")

    def soc_interval(self, voltage_v: float) -> tuple[float, float] | None:
        """平台区内返回可能的 SOC 区间（原始单调包络上的等压段）。"""
        if not math.isfinite(float(voltage_v)):
            return None
        matches = np.where(np.isclose(self._ocv, float(voltage_v), atol=1e-9))[0]
        if matches.size < 2:
            return None
        return float(self._soc[matches[0]]), float(self._soc[matches[-1]])

    def audit(self) -> dict[str, Any]:
        return {
            "points": int(self._soc.size),
            "minimum_slope_v_per_soc": float(self.minimum_slope),
            "monotonic_adjusted_indices": list(self.monotonic_indices),
            "monotonic_adjusted_count": int(len(self.monotonic_indices)),
            "ocv_min_v": float(self._ocv[0]),
            "ocv_max_v": float(self._ocv[-1]),
            "raw_non_increasing_count": int(np.sum(np.diff(self._ocv_raw) <= 0.0)),
        }
