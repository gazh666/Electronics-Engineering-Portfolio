"""统一仿真数据结构。

``SimulationResult`` 同时保存数据、参数、单位、环境信息与数据来源，
避免上层脚本各自拼装结果字典。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import pandas as pd

DATA_SOURCE_SPICE = "spice_simulation"
DATA_SOURCE_THEORY = "analytical_theory"


class AnalysisType(str, Enum):
    """本阶段支持的四类分析。"""

    OP = "operating_point"
    DC = "dc"
    AC = "ac"
    TRANSIENT = "transient"


@dataclass
class SimulationResult:
    """一次真实 SPICE 求解的不可变式快照（DataFrame 为独立副本）。"""

    run_id: str
    circuit_name: str
    analysis_type: AnalysisType
    backend: str
    data: pd.DataFrame
    circuit_netlist: str
    duration_ms: float
    parameters: dict[str, Any] = field(default_factory=dict)
    units: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    data_source: str = DATA_SOURCE_SPICE
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def __post_init__(self) -> None:
        if not isinstance(self.analysis_type, AnalysisType):
            raise ValueError("analysis_type must be AnalysisType")
        if not isinstance(self.data, pd.DataFrame):
            raise ValueError("data must be a pandas.DataFrame")
        if self.data_source != DATA_SOURCE_SPICE:
            raise ValueError("SimulationResult.data_source must be spice_simulation")
        if self.duration_ms < 0:
            raise ValueError("duration_ms must be nonnegative")

    @property
    def point_count(self) -> int:
        """数据点数量（行数）。"""
        return int(len(self.data))

    @property
    def columns(self) -> list[str]:
        return list(self.data.columns)

    def to_metadata(self) -> dict[str, Any]:
        """导出可 JSON 序列化的元数据（不含 DataFrame）。"""
        return {
            "run_id": self.run_id,
            "circuit_name": self.circuit_name,
            "analysis_type": self.analysis_type.value,
            "backend": self.backend,
            "duration_ms": self.duration_ms,
            "point_count": self.point_count,
            "columns": self.columns,
            "units": dict(self.units),
            "parameters": dict(self.parameters),
            "metadata": dict(self.metadata),
            "data_source": self.data_source,
            "created_at": self.created_at,
        }
