"""接口校验：测量包结构、证据文件真实性与状态一致性。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from integration.measurement_exchange import VALID_SOURCES, VALID_STATUS


def validate_measurement_bundle(bundle: dict[str, Any], *, evidence_root: Path | None = None) -> dict[str, Any]:
    """校验测量交换包；返回问题清单，不抛断言式"通过"。"""
    issues: list[dict[str, Any]] = []

    required = ("schema_version", "run_id", "source", "hardware_validated", "measurements")
    for key in required:
        if key not in bundle:
            issues.append({"level": "ERROR", "field": key, "reason": "MISSING_FIELD"})

    if bundle.get("schema_version") != "1.0":
        issues.append({"level": "ERROR", "field": "schema_version", "reason": "UNSUPPORTED_VERSION"})
    if bundle.get("source") not in VALID_SOURCES:
        issues.append({"level": "ERROR", "field": "source", "reason": "UNKNOWN_SOURCE"})
    if bundle.get("hardware_validated") is not False:
        issues.append({"level": "ERROR", "field": "hardware_validated", "reason": "MUST_BE_FALSE"})

    measurements = bundle.get("measurements")
    if not isinstance(measurements, list) or not measurements:
        issues.append({"level": "ERROR", "field": "measurements", "reason": "EMPTY_OR_INVALID"})
        measurements = []

    seen: set[str] = set()
    for index, item in enumerate(measurements):
        prefix = f"measurements[{index}]"
        if not isinstance(item, dict):
            issues.append({"level": "ERROR", "field": prefix, "reason": "NOT_A_MAPPING"})
            continue
        metric = item.get("metric")
        if not metric:
            issues.append({"level": "ERROR", "field": f"{prefix}.metric", "reason": "MISSING"})
        elif metric in seen:
            issues.append({"level": "WARN", "field": f"{prefix}.metric", "reason": "DUPLICATE"})
        else:
            seen.add(metric)
        if item.get("status") not in VALID_STATUS:
            issues.append({"level": "ERROR", "field": f"{prefix}.status", "reason": "INVALID_STATUS"})
        if item.get("status") == "VERIFIED":
            value = item.get("value")
            if value is None:
                issues.append({"level": "ERROR", "field": f"{prefix}.value", "reason": "VERIFIED_WITHOUT_VALUE"})
            if not item.get("source_run_id") or not item.get("evidence_path"):
                issues.append({"level": "ERROR", "field": prefix, "reason": "VERIFIED_WITHOUT_EVIDENCE"})
            evidence = item.get("evidence_path")
            if evidence_root is not None and evidence:
                candidate = Path(evidence)
                if not candidate.is_absolute():
                    candidate = Path(evidence_root) / candidate
                if not candidate.exists():
                    issues.append(
                        {"level": "ERROR", "field": f"{prefix}.evidence_path", "reason": "EVIDENCE_NOT_FOUND"}
                    )

    errors = [item for item in issues if item["level"] == "ERROR"]
    return {
        "status": "PASS" if not errors else "FAIL",
        "error_count": len(errors),
        "warning_count": len(issues) - len(errors),
        "measurement_count": len(measurements),
        "issues": issues,
    }


def validate_schema_file(path: str | Path) -> dict[str, Any]:
    """确认 JSON Schema 文件可解析且声明了 draft-07。"""
    target = Path(path)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:  # noqa: BLE001
        return {"path": str(target), "status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}
    return {
        "path": str(target),
        "status": "OK" if payload.get("$schema", "").endswith("draft-07/schema#") else "WARN",
        "title": payload.get("title"),
        "required": payload.get("required", []),
    }


__all__ = ["validate_measurement_bundle", "validate_schema_file"]
