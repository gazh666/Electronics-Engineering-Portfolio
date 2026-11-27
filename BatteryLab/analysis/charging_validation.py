"""第六阶段验收判定：限值在运行前登记，结果不达标保留 FAIL。

任何"未测到" "未验证" 一律记为 NOT_MEASURED，不得当成通过。
未登记的指标名直接抛错，避免用临时改名绕过预登记限值。
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from battery_models.parameters import load_yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LIMITS_PATH = PROJECT_ROOT / "configs" / "stage6_validation.yaml"

# 名称 → (方向, 单位, 是否取绝对值后比较)
LIMIT_SPECS: dict[str, tuple[str, str, bool]] = {
    "cc_mean_error_a": ("max", "A", True),
    "cc_period_average_error_a": ("max", "A", True),
    "cc_startup_overshoot_fraction": ("max", "1", False),
    "cv_mean_error_v": ("max", "V", True),
    "cv_period_average_error_v": ("max", "V", True),
    "cc_cv_voltage_overshoot_v": ("max", "V", False),
    "power_stage_efficiency_min_percent": ("min", "%", False),
    "power_conservation_residual_fraction": ("max", "1", True),
    "phase_margin_deg": ("min", "deg", False),
    "gain_margin_db": ("min", "dB", False),
    "bandwidth_separation_ratio": ("min", "1", False),
    "soc_consistency_tolerance_ah": ("max", "Ah", True),
    "intrinsic_solver_consistency_ppm": ("max", "ppm", True),
}


def load_preregistered_limits(path: str | Path | None = None) -> dict[str, float]:
    target = Path(path) if path is not None else DEFAULT_LIMITS_PATH
    raw = load_yaml(target)
    section = raw.get("preregistered_limits")
    if not isinstance(section, Mapping):
        raise ValueError(f"{target} 缺少 preregistered_limits")
    limits: dict[str, float] = {}
    for name, value in section.items():
        if name not in LIMIT_SPECS:
            raise ValueError(f"未登记的限值项: {name}")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            number = float(value)
            if math.isfinite(number):
                limits[name] = number
    missing = sorted(set(LIMIT_SPECS) - set(limits))
    if missing:
        raise ValueError(f"预登记限值缺失: {missing}")
    return limits


def _require_spec(name: str) -> tuple[str, str, bool]:
    if name not in LIMIT_SPECS:
        raise ValueError(f"未登记的指标: {name}")
    return LIMIT_SPECS[name]


def extract_value(measured: Any) -> float | None:
    if measured is None:
        return None
    if isinstance(measured, Mapping):
        measured = measured.get("value")
        if measured is None:
            return None
    if isinstance(measured, bool) or not isinstance(measured, (int, float)):
        raise ValueError(f"指标值非法: {measured!r}")
    value = float(measured)
    return value if math.isfinite(value) else None


def evaluate_limit(name: str, measured: Any, limit: float) -> dict[str, Any]:
    direction, unit, use_abs = _require_spec(name)
    if not math.isfinite(limit):
        raise ValueError(f"限值非法: {name}")
    if isinstance(measured, Mapping) and measured.get("infinite") is True:
        if direction != "min":
            raise ValueError("只有下限类指标允许 INFINITE 判定")
        return {
            "name": name,
            "value": None,
            "limit": float(limit),
            "direction": direction,
            "unit": unit,
            "status": "PASS",
            "note": "INFINITE_MARGIN_NO_PHASE_CROSSOVER",
        }
    raw = extract_value(measured)
    if raw is None:
        return {
            "name": name,
            "value": None,
            "limit": float(limit),
            "direction": direction,
            "unit": unit,
            "status": "NOT_MEASURED",
        }
    value = abs(raw) if use_abs else raw
    passed = value <= limit if direction == "max" else value >= limit
    return {
        "name": name,
        "value": raw,
        "compared_value": value,
        "limit": float(limit),
        "direction": direction,
        "unit": unit,
        "status": "PASS" if passed else "FAIL",
    }


def evaluate_limits(
    measured: Mapping[str, Any],
    limits: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    active_limits = dict(limits) if limits is not None else load_preregistered_limits()
    unknown = sorted(set(measured) - set(LIMIT_SPECS))
    if unknown:
        raise ValueError(f"未登记的指标: {unknown}")

    results = [
        evaluate_limit(name, measured.get(name), active_limits[name])
        for name in active_limits
    ]
    failures = [item["name"] for item in results if item["status"] == "FAIL"]
    not_measured = [item["name"] for item in results if item["status"] == "NOT_MEASURED"]
    if failures:
        overall = "FAIL"
    elif not_measured:
        overall = "INCOMPLETE"
    else:
        overall = "PASS"

    return {
        "overall_status": overall,
        "passed": [item["name"] for item in results if item["status"] == "PASS"],
        "failed": failures,
        "not_measured": not_measured,
        "results": results,
    }


def compare_limits(
    baseline: Mapping[str, float],
    current: Mapping[str, float],
    relative_tolerance: float = 1e-9,
) -> list[str]:
    """返回被放松的限值名；空列表表示当前限值不弱于基线。"""
    relaxations: list[str] = []
    for name, baseline_value in baseline.items():
        direction, _, _ = _require_spec(name)
        if name not in current:
            relaxations.append(name)
            continue
        current_value = float(current[name])
        if direction == "max":
            weakened = current_value > baseline_value * (1.0 + relative_tolerance)
        else:
            weakened = current_value < baseline_value * (1.0 - relative_tolerance)
        if weakened:
            relaxations.append(name)
    return relaxations


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    """把手写清单（如终验项）汇总成统一状态。"""
    failures = [item.get("name", "?") for item in results if item.get("status") == "FAIL"]
    not_measured = [
        item.get("name", "?") for item in results if item.get("status") == "NOT_MEASURED"
    ]
    if failures:
        overall = "FAIL"
    elif not_measured:
        overall = "INCOMPLETE"
    else:
        overall = "PASS"
    return {
        "overall_status": overall,
        "total": len(results),
        "failed": failures,
        "not_measured": not_measured,
    }


def percentile_summary(values: Any, percentiles: tuple[float, ...] = (5.0, 50.0, 95.0)) -> dict[str, float]:
    """辅助统计（如周期平均误差分布），不参与验收判定。"""
    array = np.asarray(values, dtype=float)
    if array.ndim != 1 or array.size == 0 or not np.all(np.isfinite(array)):
        raise ValueError("统计序列非法")
    return {f"p{int(p)}": float(np.percentile(array, p)) for p in percentiles}
