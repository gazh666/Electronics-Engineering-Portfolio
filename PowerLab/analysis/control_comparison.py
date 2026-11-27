"""开环与闭环控制效果对比。

所有差值只在两个数值都有限时计算；任何一侧为 ``NaN``/``NOT_RECOVERED``
时保留原状态，不把缺失值当成 0，也不计算“提升百分比”。
"""

from __future__ import annotations

import math
from typing import Any, Iterable

import pandas as pd

COMPARISON_FIELDS = (
    "pre_event_mean_v",
    "post_event_min_v",
    "post_event_max_v",
    "droop_v",
    "overshoot_v",
    "maximum_absolute_deviation_v",
    "maximum_relative_deviation_percent",
    "final_mean_v",
    "steady_state_error_v",
    "iae_vs",
    "ise_v2s",
)


def _recovery(metrics: dict[str, Any]) -> tuple[float, str]:
    payload = metrics.get("recovery_strict") or {}
    value = payload.get("recovery_time_s")
    status = payload.get("status", "NOT_RESOLVED")
    if value is None or not math.isfinite(float(value)):
        return math.nan, status
    return float(value), status


def comparison_row(
    scheme: str, metrics: dict[str, Any], *, data_source: str | None = None
) -> dict[str, Any]:
    event = metrics.get("event", {})
    recovery, recovery_status = _recovery(metrics)
    row = {
        "scheme": scheme,
        "event_id": event.get("event_id"),
        "event_type": event.get("event_type"),
        "data_source": data_source or metrics.get("data_source"),
        "recovery_strict_s": recovery,
        "recovery_status": recovery_status,
        "status": metrics.get("status"),
    }
    for field in COMPARISON_FIELDS:
        row[field] = metrics.get(field)
    return row


def _difference(open_value: Any, closed_value: Any) -> tuple[float, float | None]:
    try:
        a = float(open_value)
        b = float(closed_value)
    except (TypeError, ValueError):
        return math.nan, None
    if not (math.isfinite(a) and math.isfinite(b)):
        return math.nan, None
    delta = b - a
    percent = 100.0 * delta / abs(a) if a != 0 else None
    return delta, percent


def compare_event_metrics(
    open_metrics: dict[str, Any], closed_metrics: dict[str, Any]
) -> dict[str, Any]:
    """逐项给出闭环相对开环的差值与百分比（仅在可计算时）。"""
    open_row = comparison_row("open_loop", open_metrics)
    closed_row = comparison_row("closed_loop", closed_metrics)
    differences: dict[str, Any] = {}
    for field in COMPARISON_FIELDS + ("recovery_strict_s",):
        delta, percent = _difference(open_row.get(field), closed_row.get(field))
        differences[field] = {
            "open_loop": open_row.get(field),
            "closed_loop": closed_row.get(field),
            "absolute_difference": delta if math.isfinite(delta) else None,
            "relative_difference_percent": percent,
        }
    return {
        "event_id": open_row.get("event_id"),
        "open_loop": open_row,
        "closed_loop": closed_row,
        "differences": differences,
        "notes": [
            "relative differences are omitted when either side is non-finite",
            "recovery times refer to the strict cycle-mean criterion",
        ],
    }


def comparison_table(rows: Iterable[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


def compare_startup(
    open_metrics: dict[str, Any], closed_metrics: dict[str, Any]
) -> dict[str, Any]:
    fields = (
        "rise_time_s",
        "overshoot_percent",
        "settling_time_s",
        "peak_inductor_current_a",
        "peak_input_current_a",
        "steady_state_error_v",
    )
    payload: dict[str, Any] = {"fields": {}}
    for field in fields:
        delta, percent = _difference(open_metrics.get(field), closed_metrics.get(field))
        payload["fields"][field] = {
            "open_loop": open_metrics.get(field),
            "closed_loop": closed_metrics.get(field),
            "absolute_difference": delta if math.isfinite(delta) else None,
            "relative_difference_percent": percent,
        }
    return payload


def evaluate_limits(metrics: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    """按限值表判定；缺测项返回 NOT_RESOLVED，不默认通过。"""
    checks: list[dict[str, Any]] = []
    for name, rule in profile.items():
        value = metrics.get(name)
        status = "NOT_RESOLVED"
        limit = None
        if isinstance(rule, dict):
            if "min" in rule:
                limit = rule["min"]
                if value is not None and math.isfinite(float(value)):
                    status = "PASS" if float(value) >= float(limit) else "FAIL"
            elif "max" in rule:
                limit = rule["max"]
                if value is not None and math.isfinite(float(value)):
                    status = "PASS" if float(value) <= float(limit) else "FAIL"
            elif "value" in rule:
                limit = rule["value"]
                if value is not None and math.isfinite(float(value)):
                    status = "PASS" if abs(float(value) - float(limit)) <= 1e-12 else "FAIL"
        checks.append({"name": name, "limit": limit, "value": value, "status": status})
    if any(item["status"] == "FAIL" for item in checks):
        overall = "FAIL"
    elif any(item["status"] == "NOT_RESOLVED" for item in checks):
        overall = "NOT_RESOLVED"
    else:
        overall = "PASS"
    return {"checks": checks, "status": overall}


__all__ = [
    "COMPARISON_FIELDS",
    "comparison_row",
    "comparison_table",
    "compare_event_metrics",
    "compare_startup",
    "evaluate_limits",
]
