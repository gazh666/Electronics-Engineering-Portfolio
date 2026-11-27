"""第六阶段脚本公共工具：结果目录、检查项、限值判定与打印。"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from analysis.charging_validation import (  # noqa: E402
    evaluate_limits,
    load_preregistered_limits,
)
from storage.result_store import RunDirectory  # noqa: E402

STAGE = "stage6"


@dataclass(frozen=True)
class Check:
    name: str
    measured: float | None
    limit: float | None
    unit: str
    status: str
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "measured": self.measured,
            "limit": self.limit,
            "unit": self.unit,
            "status": self.status,
            "note": self.note,
        }


def check_at_most(name: str, measured: float | None, limit: float, unit: str, note: str = "") -> Check:
    passed = measured is not None and float(measured) <= limit
    return Check(name, measured, limit, unit, "PASS" if passed else ("NOT_MEASURED" if measured is None else "FAIL"), note)


def check_at_least(name: str, measured: float | None, limit: float, unit: str, note: str = "") -> Check:
    passed = measured is not None and float(measured) >= limit
    return Check(name, measured, limit, unit, "PASS" if passed else ("NOT_MEASURED" if measured is None else "FAIL"), note)


def check_within(name: str, measured: float | None, limit: float, unit: str, note: str = "") -> Check:
    passed = measured is not None and abs(float(measured)) <= limit
    return Check(name, measured, limit, unit, "PASS" if passed else ("NOT_MEASURED" if measured is None else "FAIL"), note)


def check_true(name: str, condition: bool, note: str = "") -> Check:
    return Check(name, 1.0 if condition else 0.0, 1.0, "bool", "PASS" if condition else "FAIL", note)


def summarize_checks(checks: Sequence[Check]) -> dict[str, Any]:
    passed = sum(1 for item in checks if item.status == "PASS")
    failed = sum(1 for item in checks if item.status == "FAIL")
    not_measured = sum(1 for item in checks if item.status == "NOT_MEASURED")
    return {
        "stage": STAGE,
        "checks": [item.to_dict() for item in checks],
        "passed": passed,
        "failed": failed,
        "not_measured": not_measured,
        "total": len(checks),
        "status": "PASS" if failed == 0 and not_measured == 0 else ("FAIL" if failed else "INCOMPLETE"),
    }


def make_run(kind: str) -> RunDirectory:
    run_dir = RunDirectory(STAGE)
    run_dir.write_metadata({"stage": STAGE, "kind": kind})
    return run_dir


def finish_run(run_dir: RunDirectory, summary: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(summary)
    payload["run_id"] = run_dir.run_id
    payload["run_dir"] = str(run_dir.path)
    run_dir.write_summary(payload)
    run_dir.flush_log()
    return payload


def limits_checks(measured: Mapping[str, Any], limits: Mapping[str, float] | None = None) -> dict[str, Any]:
    return evaluate_limits(measured, limits)


def stage_limits() -> dict[str, float]:
    return load_preregistered_limits()


def format_table(rows: Iterable[Sequence[Any]], headers: Sequence[str]) -> str:
    data = [[("" if value is None else str(value)) for value in row] for row in rows]
    widths = [len(str(header)) for header in headers]
    for row in data:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))
    lines = [" | ".join(str(header).ljust(widths[index]) for index, header in enumerate(headers))]
    lines.append("-+-".join("-" * width for width in widths))
    for row in data:
        lines.append(" | ".join(value.ljust(widths[index]) for index, value in enumerate(row)))
    return "\n".join(lines)


def fmt(value: Any, digits: int = 6) -> str:
    if value is None:
        return "-"
    if isinstance(value, (bool, np.bool_)):
        return "YES" if value else "NO"
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)):
        number = float(value)
        if not np.isfinite(number):
            return "-"
        return f"{number:.{digits}g}"
    return str(value)


def print_checks(checks: Sequence[Check]) -> None:
    for item in checks:
        print(f"  [{item.status:12s}] {item.name:38s} {fmt(item.measured):>14s} {item.unit:6s}  {item.note}")


def counts_by_status(checks: Sequence[Check]) -> str:
    passed = sum(1 for item in checks if item.status == "PASS")
    failed = sum(1 for item in checks if item.status == "FAIL")
    not_measured = sum(1 for item in checks if item.status == "NOT_MEASURED")
    return f"PASS {passed} / FAIL {failed} / NOT_MEASURED {not_measured} / 合计 {len(checks)}"
