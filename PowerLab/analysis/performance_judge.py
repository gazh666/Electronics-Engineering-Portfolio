"""性能限值判定。

判定状态与数据状态分离：

- ``PASS`` / ``FAIL``：数据可用且与限值比较完成；
- ``NOT_VERIFIED``：指标存在但未解析/未稳定；
- ``NOT_APPLICABLE``：模型不适用（例如 SW 基线没有栅极电荷）；
- ``ERROR``：指标缺失或数据非法；
- ``SKIP``：限值被显式关闭。
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from .performance_models import MetricStatus, PerformanceCheck, PerformanceMetric

COMPARISON_STATUSES = ("PASS", "FAIL")


def judge_metric(
    name: str,
    metric: PerformanceMetric | None,
    rule: Mapping[str, Any],
    *,
    profile: str = "",
    unit: str = "",
) -> PerformanceCheck:
    """按单条限值规则判定一个指标。"""
    rule_unit = str(rule.get("unit", unit))
    minimum = rule.get("min")
    maximum = rule.get("max")
    required = bool(rule.get("required", False))
    minimum_value = None if minimum is None else float(minimum)
    maximum_value = None if maximum is None else float(maximum)

    if not bool(rule.get("enabled", True)):
        return PerformanceCheck(
            metric_name=name,
            actual_value=None if metric is None else metric.numeric(),
            minimum_value=minimum_value,
            maximum_value=maximum_value,
            status="SKIP",
            reason="limit_disabled",
            unit=rule_unit,
            profile=profile,
            required=required,
            data_source="project_assumption",
        )

    if metric is None:
        return PerformanceCheck(
            metric_name=name,
            actual_value=None,
            minimum_value=minimum_value,
            maximum_value=maximum_value,
            status="ERROR" if required else "SKIP",
            reason="metric_missing" if required else "metric_missing_optional",
            unit=rule_unit,
            profile=profile,
            required=required,
            data_source="project_assumption",
        )

    if metric.status == MetricStatus.NOT_APPLICABLE:
        return PerformanceCheck(
            metric_name=name,
            actual_value=None,
            minimum_value=minimum_value,
            maximum_value=maximum_value,
            status="NOT_APPLICABLE",
            reason=metric.message or "metric_not_applicable",
            unit=metric.unit or rule_unit,
            profile=profile,
            required=required,
            data_source=metric.data_source.value,
        )

    if metric.status in (MetricStatus.NOT_RESOLVED, MetricStatus.NOT_SETTLED):
        return PerformanceCheck(
            metric_name=name,
            actual_value=metric.numeric(),
            minimum_value=minimum_value,
            maximum_value=maximum_value,
            status="NOT_VERIFIED",
            reason=metric.message or metric.status.value,
            unit=metric.unit or rule_unit,
            profile=profile,
            required=required,
            data_source=metric.data_source.value,
        )

    if metric.status == MetricStatus.INVALID_DATA:
        return PerformanceCheck(
            metric_name=name,
            actual_value=metric.numeric(),
            minimum_value=minimum_value,
            maximum_value=maximum_value,
            status="ERROR",
            reason=metric.message or "invalid_data",
            unit=metric.unit or rule_unit,
            profile=profile,
            required=required,
            data_source=metric.data_source.value,
        )

    actual = metric.numeric()
    if actual is None:
        return PerformanceCheck(
            metric_name=name,
            actual_value=None,
            minimum_value=minimum_value,
            maximum_value=maximum_value,
            status="ERROR",
            reason="non_numeric_value",
            unit=metric.unit or rule_unit,
            profile=profile,
            required=required,
            data_source=metric.data_source.value,
        )

    below = minimum_value is not None and actual < minimum_value
    above = maximum_value is not None and actual > maximum_value
    if below:
        reason = f"below_minimum ({actual:.6g} < {minimum_value:.6g})"
    elif above:
        reason = f"above_maximum ({actual:.6g} > {maximum_value:.6g})"
    else:
        reason = "within_limits"
    return PerformanceCheck(
        metric_name=name,
        actual_value=float(actual),
        minimum_value=minimum_value,
        maximum_value=maximum_value,
        status="FAIL" if (below or above) else "PASS",
        reason=reason,
        unit=metric.unit or rule_unit,
        profile=profile,
        required=required,
        data_source=metric.data_source.value,
    )


def judge_profile(
    metrics: Mapping[str, PerformanceMetric],
    profile: Mapping[str, Any],
    *,
    profile_name: str = "",
) -> list[PerformanceCheck]:
    """按一个 profile 判定全部指标。"""
    checks: list[PerformanceCheck] = []
    for name, rule in profile.items():
        if name in ("note", "description"):
            continue
        if not isinstance(rule, Mapping):
            raise ValueError(f"invalid limit rule for metric: {name}")
        checks.append(
            judge_metric(
                name,
                metrics.get(name),
                rule,
                profile=profile_name,
                unit=str(rule.get("unit", "")),
            )
        )
    return checks


def overall_status(checks: Iterable[PerformanceCheck]) -> str:
    """汇总判定：``ERROR > FAIL > INCOMPLETE > PASS``。"""
    items = list(checks)
    if not items:
        return "INCOMPLETE"
    statuses = [check.status for check in items]
    if "ERROR" in statuses:
        return "ERROR"
    if "FAIL" in statuses:
        return "FAIL"
    if all(status == "SKIP" for status in statuses):
        return "INCOMPLETE"
    if any(
        check.status in ("NOT_VERIFIED", "NOT_APPLICABLE") and check.required
        for check in items
    ):
        return "INCOMPLETE"
    return "PASS"


def summarize_checks(checks: Iterable[PerformanceCheck]) -> dict[str, Any]:
    """统计各状态数量并给出总体结论。"""
    items = list(checks)
    counts: dict[str, int] = {}
    for check in items:
        counts[check.status] = counts.get(check.status, 0) + 1
    return {
        "overall_status": overall_status(items),
        "counts": counts,
        "total": len(items),
        "failed": [check.to_dict() for check in items if check.status == "FAIL"],
        "errors": [check.to_dict() for check in items if check.status == "ERROR"],
        "not_verified": [
            check.to_dict() for check in items if check.status == "NOT_VERIFIED"
        ],
        "not_applicable": [
            check.to_dict() for check in items if check.status == "NOT_APPLICABLE"
        ],
        "skipped": [check.to_dict() for check in items if check.status == "SKIP"],
    }
