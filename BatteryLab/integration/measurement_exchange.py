"""系统级工程量数据模型（Task 23）。

``VERIFIED`` 只表示"数据来源与计算已验证"，不代表指标满足设计限值；
工程 PASS/FAIL 由 ``validation/system_result_judge.py`` 单独判定。
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "1.0"
VALID_STATUS = ("VERIFIED", "NOT_VERIFIED", "FAIL", "ERROR")
VALID_SOURCES = (
    "historical_replay",
    "quasi_steady_coupled_simulation",
    "averaged_dynamic_coupled_simulation",
    "spice_coupled_simulation",
    "behavioral_protection_simulation",
)


@dataclass(frozen=True)
class SystemMeasurement:
    metric: str
    value: float | None
    unit: str
    source: str
    source_run_id: str | None
    evidence_path: str | None
    status: str
    case_id: str | None = None

    def __post_init__(self) -> None:
        if not self.metric:
            raise ValueError("Missing metric")
        if not self.unit:
            raise ValueError("Missing unit")
        if self.status not in VALID_STATUS:
            raise ValueError(f"Invalid status: {self.status!r}")
        if self.source not in VALID_SOURCES:
            raise ValueError(f"Invalid source: {self.source!r}")
        if self.value is not None and not math.isfinite(self.value):
            raise ValueError("Non-finite measurement")
        if self.status == "VERIFIED":
            if self.value is None:
                raise ValueError("Missing verified value")
            if not (self.source_run_id and self.evidence_path):
                raise ValueError("Missing evidence")

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "value": self.value,
            "unit": self.unit,
            "status": self.status,
            "source": self.source,
            "source_run_id": self.source_run_id,
            "evidence_path": self.evidence_path,
            "case_id": self.case_id,
        }


def measurement_from_dict(payload: dict[str, Any]) -> SystemMeasurement:
    return SystemMeasurement(
        metric=str(payload["metric"]),
        value=None if payload.get("value") is None else float(payload["value"]),
        unit=str(payload["unit"]),
        source=str(payload["source"]),
        source_run_id=payload.get("source_run_id"),
        evidence_path=payload.get("evidence_path"),
        status=str(payload["status"]),
        case_id=payload.get("case_id"),
    )


def build_bundle(
    *,
    run_id: str,
    source: str,
    measurements: Iterable[SystemMeasurement],
    case_id: str | None = None,
    model_type: str | None = None,
    battery_parameter_source: str | None = None,
    converter_configuration: dict[str, Any] | None = None,
    time_window: dict[str, float] | None = None,
    power_boundary: str | None = None,
    code_hash: str | None = None,
    config_hash: str | None = None,
) -> dict[str, Any]:
    if source not in VALID_SOURCES:
        raise ValueError(f"Invalid source: {source!r}")
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "source": source,
        "hardware_validated": False,
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "case_id": case_id,
        "model_type": model_type,
        "battery_parameter_source": battery_parameter_source,
        "converter_configuration": converter_configuration,
        "time_window": time_window,
        "power_boundary": power_boundary,
        "code_hash": code_hash,
        "config_hash": config_hash,
        "measurements": [item.to_dict() for item in measurements],
    }


def save_bundle(bundle: dict[str, Any], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def load_bundle(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


__all__ = [
    "SCHEMA_VERSION",
    "SystemMeasurement",
    "build_bundle",
    "load_bundle",
    "measurement_from_dict",
    "save_bundle",
]
