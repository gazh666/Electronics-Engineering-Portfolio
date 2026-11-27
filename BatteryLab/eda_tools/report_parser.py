"""ERC / DRC JSON 报告解析。

不同 KiCad 版本结构可能不同，因此：
- 报告缺失 → ERROR；
- 结构不认识 → NOT_VERIFIED；
- 解析成功 → 返回真实计数，绝不在未知结构上返回"零错误"。
"""

from __future__ import annotations

import json
from pathlib import Path


def read_json_report(report_path: str | Path) -> dict:
    path = Path(report_path)
    if not path.is_file():
        raise FileNotFoundError(path)

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Unexpected report format")
    return data


def count_severities(violations: list[dict]) -> dict:
    result = {"error": 0, "warning": 0, "excluded": 0, "unknown": 0}

    for violation in violations:
        severity = str(violation.get("severity", "unknown")).lower()
        if severity in result:
            result[severity] += 1
        else:
            result["unknown"] += 1

    return result


def _find_violation_container(data: dict) -> tuple[list[str], list[dict]]:
    """返回 (来源路径, 违规列表)；支持 sheets/violations 与平铺 violations。"""
    for key in ("violations", "issues", "items"):
        value = data.get(key)
        if isinstance(value, list):
            return [key], value

    collected_paths: list[str] = []
    collected: list[dict] = []
    for sheet_name, sheet in data.items():
        if isinstance(sheet, dict):
            for key in ("violations", "issues"):
                value = sheet.get(key)
                if isinstance(value, list):
                    collected_paths.append(f"{sheet_name}.{key}")
                    collected.extend(value)
    return collected_paths, collected


def summarize_report(report_path: str | Path) -> dict:
    try:
        data = read_json_report(report_path)
    except FileNotFoundError:
        return {"status": "ERROR", "reason": "REPORT_MISSING", "path": str(report_path)}
    except (ValueError, json.JSONDecodeError) as exc:
        return {"status": "ERROR", "reason": f"UNPARSABLE_REPORT: {exc}", "path": str(report_path)}

    sources, violations = _find_violation_container(data)
    if not sources:
        return {
            "status": "NOT_VERIFIED",
            "reason": "UNRECOGNIZED_STRUCTURE",
            "top_level_keys": sorted(data.keys()),
            "path": str(report_path),
        }

    severities = count_severities(violations)

    unconnected = data.get("unconnected_items")
    if not isinstance(unconnected, list):
        unconnected_count = None
        unconnected_status = "NOT_VERIFIED"
    else:
        unconnected_count = len(unconnected)
        unconnected_status = "REPORTED"

    return {
        "status": "PARSED",
        "sources": sources,
        "violation_count": len(violations),
        "severities": severities,
        "unconnected_count": unconnected_count,
        "unconnected_status": unconnected_status,
        "rule_counts": _count_rules(violations),
        "path": str(report_path),
    }


def _count_rules(violations: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for violation in violations:
        rule = violation.get("type") or violation.get("rule") or "UNKNOWN"
        counts[str(rule)] = counts.get(str(rule), 0) + 1
    return counts


def export_summary(report_path: str | Path, output_path: str | Path) -> dict:
    summary = summarize_report(report_path)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary
