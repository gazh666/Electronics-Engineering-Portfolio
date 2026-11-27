"""测试数据统计：区分跨工况变化与同工况重复测量离散度。

统计模块只做描述性统计，不做 Cp/Cpk、良率或过程能力分析——当前没有
真实生产过程数据，任何过程能力结论都会失去意义。
"""

from __future__ import annotations

import math
import statistics as stdlib_statistics
from typing import Any, Iterable, Mapping, Sequence


def _valid_numbers(values: Iterable[Any]) -> tuple[list[float], int]:
    valid: list[float] = []
    invalid = 0
    for item in values:
        if isinstance(item, bool):
            invalid += 1
            continue
        try:
            value = float(item)
        except (TypeError, ValueError):
            invalid += 1
            continue
        if not math.isfinite(value):
            invalid += 1
            continue
        valid.append(value)
    return valid, invalid


def summarize(values: Iterable[Any]) -> dict[str, float | int | None]:
    """汇总一列数据，自动跳过非法值。

    返回字段：``count``（有效样本）、``invalid_count``、``mean``、``min``、
    ``max``、``range``、``median``、``sample_std``。无有效样本时统计量为
    ``None``，而不是 0；单样本标准差为 ``None``。
    """
    valid_values, invalid_count = _valid_numbers(values)
    count = len(valid_values)

    if count == 0:
        return {
            "count": 0,
            "invalid_count": invalid_count,
            "mean": None,
            "min": None,
            "max": None,
            "range": None,
            "median": None,
            "sample_std": None,
        }

    minimum = min(valid_values)
    maximum = max(valid_values)

    return {
        "count": count,
        "invalid_count": invalid_count,
        "mean": stdlib_statistics.fmean(valid_values),
        "min": minimum,
        "max": maximum,
        "range": maximum - minimum,
        "median": stdlib_statistics.median(valid_values),
        "sample_std": (
            stdlib_statistics.stdev(valid_values) if count >= 2 else None
        ),
    }


def summarize_field(
    records: Sequence[Mapping[str, Any]], field: str
) -> dict[str, float | int | None]:
    """对记录列表中的某个字段做汇总。"""
    return summarize(record.get(field) for record in records)


def summarize_by_group(
    records: Sequence[Mapping[str, Any]],
    value_field: str,
    group_fields: Sequence[str],
) -> dict[tuple[Any, ...], dict[str, float | int | None]]:
    """按工况字段分组汇总，用于观察不同负载/输入电压下的性能变化。"""
    groups: dict[tuple[Any, ...], list[Any]] = {}
    for record in records:
        key = tuple(record.get(field) for field in group_fields)
        groups.setdefault(key, []).append(record.get(value_field))
    return {key: summarize(values) for key, values in groups.items()}
