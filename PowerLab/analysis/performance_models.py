"""第五阶段性能数据模型与配置加载。

每个指标都带状态与数据来源，禁止把 ``None`` 静默当成 0，也禁止把
``analytical_theory`` 或 ``project_assumption`` 冒充 SPICE 结果。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, ClassVar, Mapping

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "configs"


class MetricStatus(str, Enum):
    """指标状态。"""

    AVAILABLE = "AVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    INVALID_DATA = "INVALID_DATA"
    NOT_SETTLED = "NOT_SETTLED"
    NOT_RESOLVED = "NOT_RESOLVED"


class DataSource(str, Enum):
    """指标数据来源。"""

    SPICE_SIMULATION = "spice_simulation"
    SPICE_DERIVED = "spice_derived"
    ANALYTICAL_THEORY = "analytical_theory"
    PROJECT_ASSUMPTION = "project_assumption"


@dataclass(frozen=True)
class PerformanceMetric:
    """单个性能指标。"""

    name: str
    value: float | int | str | None
    unit: str
    status: MetricStatus
    data_source: DataSource
    method: str
    message: str = ""
    conditions: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "status": self.status.value,
            "data_source": self.data_source.value,
            "method": self.method,
            "message": self.message,
            "conditions": dict(self.conditions),
        }

    def numeric(self) -> float | None:
        if isinstance(self.value, (int, float)):
            return float(self.value)
        return None


@dataclass(frozen=True)
class MetricGroup:
    """一组同类指标。"""

    metrics: Mapping[str, PerformanceMetric] = field(default_factory=dict)
    label: ClassVar[str] = "metrics"

    def get(self, name: str) -> PerformanceMetric | None:
        return self.metrics.get(name)

    def value(self, name: str) -> float | int | str | None:
        metric = self.metrics.get(name)
        return None if metric is None else metric.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "metrics": {name: metric.to_dict() for name, metric in self.metrics.items()},
        }

    def flatten(self) -> dict[str, PerformanceMetric]:
        return dict(self.metrics)


class VoltageMetrics(MetricGroup):
    label = "voltage"


class CurrentMetrics(MetricGroup):
    label = "current"


class RippleMetrics(MetricGroup):
    label = "ripple"


class PowerMetrics(MetricGroup):
    label = "power"


class EfficiencyMetrics(MetricGroup):
    label = "efficiency"


class SwitchingMetrics(MetricGroup):
    label = "switching"


class SpectrumMetrics(MetricGroup):
    label = "spectrum"


class RegulationMetrics(MetricGroup):
    label = "regulation"


class QualityMetrics(MetricGroup):
    label = "quality"


@dataclass(frozen=True)
class PerformanceCheck:
    """限值判定结果。"""

    metric_name: str
    actual_value: float | None
    minimum_value: float | None
    maximum_value: float | None
    status: str
    reason: str
    unit: str = ""
    profile: str = ""
    required: bool = False
    data_source: str = "spice_derived"

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "actual_value": self.actual_value,
            "minimum_value": self.minimum_value,
            "maximum_value": self.maximum_value,
            "status": self.status,
            "reason": self.reason,
            "unit": self.unit,
            "profile": self.profile,
            "required": self.required,
            "data_source": self.data_source,
        }


@dataclass(frozen=True)
class PerformanceResult:
    """一次工况的完整性能分析结果。"""

    run_id: str
    circuit_name: str
    variant: str
    data_source: str
    steady_state: Mapping[str, Any]
    groups: Mapping[str, MetricGroup]
    checks: tuple[PerformanceCheck, ...]
    quality: Mapping[str, Any]
    overall_status: str
    notes: tuple[str, ...] = ()
    spectrum_metadata: Mapping[str, Any] = field(default_factory=dict)
    cycle_statistics: Mapping[str, Any] = field(default_factory=dict)
    ripple_decomposition: Mapping[str, Any] = field(default_factory=dict)
    harmonic_entries: tuple[Mapping[str, Any], ...] = ()
    switching_details: Mapping[str, Any] = field(default_factory=dict)
    frame: Any = None
    window_frame: Any = None
    spectrum: Any = None
    circuit_netlist: str | None = None
    raw_point_count: int = 0

    def metrics(self) -> dict[str, PerformanceMetric]:
        merged: dict[str, PerformanceMetric] = {}
        for group in self.groups.values():
            merged.update(group.flatten())
        return merged

    def metric(self, name: str) -> PerformanceMetric | None:
        return self.metrics().get(name)

    def numeric(self, name: str) -> float | None:
        metric = self.metric(name)
        return None if metric is None else metric.numeric()

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "circuit_name": self.circuit_name,
            "variant": self.variant,
            "data_source": self.data_source,
            "raw_point_count": self.raw_point_count,
            "steady_state": dict(self.steady_state),
            "groups": {name: group.to_dict() for name, group in self.groups.items()},
            "metrics": {
                name: metric.to_dict() for name, metric in self.metrics().items()
            },
            "checks": [check.to_dict() for check in self.checks],
            "quality": dict(self.quality),
            "overall_status": self.overall_status,
            "notes": list(self.notes),
            "spectrum": dict(self.spectrum_metadata),
            "cycle_statistics": dict(self.cycle_statistics),
            "ripple_decomposition": dict(self.ripple_decomposition),
        }


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"configuration not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"configuration must be a mapping: {path}")
    return data


def _require(mapping: Mapping[str, Any], key: str, where: str) -> Any:
    if key not in mapping:
        raise ValueError(f"missing key '{key}' in {where}")
    return mapping[key]


def load_analysis_config(path: str | Path | None = None) -> dict[str, Any]:
    """读取 performance_analysis.yaml 并校验必需字段。"""
    target = Path(path) if path is not None else CONFIG_DIR / "performance_analysis.yaml"
    data = _load_yaml(target)
    analysis = _require(data, "analysis", str(target))
    steady = _require(analysis, "steady_state", "analysis")
    ripple = _require(analysis, "ripple", "analysis")
    switching = _require(analysis, "switching", "analysis")
    spectrum = _require(analysis, "spectrum", "analysis")
    quality = _require(analysis, "quality", "analysis")
    for key in ("minimum_cycles", "preferred_cycles"):
        _require(steady, key, "analysis.steady_state")
    for key in ("calculate_vpp", "calculate_ac_rms", "calculate_per_cycle"):
        _require(ripple, key, "analysis.ripple")
    for key in ("low_threshold_ratio", "high_threshold_ratio", "minimum_edge_samples"):
        _require(switching, key, "analysis.switching")
    for key in (
        "enabled",
        "window",
        "preferred_cycles",
        "samples_per_cycle",
        "maximum_harmonic_order",
        "maximum_samples",
        "remove_dc",
    ):
        _require(spectrum, key, "analysis.spectrum")
    for key in ("require_steady_state", "reject_nonfinite_data", "maximum_power_residual_ratio"):
        _require(quality, key, "analysis.quality")
    return data


def load_limits(path: str | Path | None = None) -> dict[str, Any]:
    """读取 performance_limits.yaml。"""
    target = Path(path) if path is not None else CONFIG_DIR / "performance_limits.yaml"
    data = _load_yaml(target)
    profiles = _require(data, "profiles", str(target))
    if not isinstance(profiles, dict) or not profiles:
        raise ValueError("performance_limits.yaml must define profiles")
    return data


def resolve_profile(limits: Mapping[str, Any], name: str) -> dict[str, Any]:
    """取指定限值方案；不存在时显式报错。"""
    profiles = limits.get("profiles", {})
    if name not in profiles:
        raise ValueError(f"unknown limits profile: {name}")
    profile = profiles[name]
    if not isinstance(profile, dict):
        raise ValueError(f"invalid limits profile: {name}")
    return profile


def load_cases(path: str | Path | None = None) -> list[dict[str, Any]]:
    """读取 performance_cases.yaml。"""
    target = Path(path) if path is not None else CONFIG_DIR / "performance_cases.yaml"
    data = _load_yaml(target)
    cases = _require(data, "cases", str(target))
    if not isinstance(cases, list) or not cases:
        raise ValueError("performance_cases.yaml must define at least one case")
    identifiers = [case.get("id") for case in cases]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("case ids must be unique")
    return list(cases)
