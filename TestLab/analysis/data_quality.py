"""数据质量检查：在工程指标计算之前识别不可信数据。

工业测试中，通信异常、字段缺失、单位混用和功率不守恒都可能产生
“看起来正常”的数值。本模块只负责标记问题，不修改原始记录，也不
静默删除异常数据。

注意事项
--------
- 负电流限制针对当前单向 DC-DC 模型；双向电源、充放电系统的电流
  可以为负，接入这类设备时需要调整校验规则。
- 所有异常记录必须保留原始值，并记录排除原因与数量。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

#: 当前模型支持的正常/保护状态
PROTECTION_STATES = frozenset(
    {
        "OUTPUT_OFF",
        "UNDERVOLTAGE",
        "OVERVOLTAGE",
        "OVERCURRENT",
        "INPUT_CURRENT_LIMIT",
    }
)
VALID_STATES = frozenset({"NORMAL"}) | PROTECTION_STATES

#: 性能分析必需的数值字段
POWER_FIELDS = ("vin", "iin", "vout", "iout")

#: 单条记录必需字段
REQUIRED_FIELDS = POWER_FIELDS + ("state", "source")

#: 工况上下文字段（缺失记 WARNING，不直接丢弃记录）
CONTEXT_FIELDS = ("vin_setpoint", "input_current_limit", "load_current_setpoint")


@dataclass(frozen=True)
class QualityIssue:
    """一条数据质量问题。"""

    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class RecordQuality:
    """单条记录的检查结果。"""

    index: int
    issues: tuple[QualityIssue, ...]

    @property
    def valid(self) -> bool:
        """没有 ERROR 级问题时视为可用于性能分析。"""
        return not any(issue.severity == "ERROR" for issue in self.issues)


@dataclass(frozen=True)
class DatasetQualityReport:
    """数据集质量报告：保留排除索引、原因与统计，不删除原始记录。"""

    total_records: int
    records: tuple[RecordQuality, ...]
    dataset_issues: tuple[QualityIssue, ...]
    excluded_indices: tuple[int, ...]
    excluded_reasons: tuple[str, ...]

    @property
    def valid_indices(self) -> tuple[int, ...]:
        excluded = set(self.excluded_indices)
        return tuple(
            record.index
            for record in self.records
            if record.valid and record.index not in excluded
        )

    @property
    def valid_count(self) -> int:
        return len(self.valid_indices)

    @property
    def excluded_count(self) -> int:
        return len(self.excluded_indices)

    def to_dict(self) -> dict[str, Any]:
        """转换为可 JSON 序列化的结构。"""
        return {
            "total_records": self.total_records,
            "valid_count": self.valid_count,
            "excluded_count": self.excluded_count,
            "excluded_indices": list(self.excluded_indices),
            "excluded_reasons": list(self.excluded_reasons),
            "dataset_issues": [
                _issue_dict(issue) for issue in self.dataset_issues
            ],
            "records": [
                {
                    "index": record.index,
                    "valid": record.valid,
                    "issues": [_issue_dict(issue) for issue in record.issues],
                }
                for record in self.records
            ],
        }


def _issue_dict(issue: QualityIssue) -> dict[str, str]:
    return {
        "code": issue.code,
        "severity": issue.severity,
        "message": issue.message,
    }


def _to_number(value: Any) -> float | None:
    """把值转换为有限浮点数；布尔、字符串、NaN/inf 返回 ``None``。"""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def inspect_power_data(
    vin: float,
    iin: float,
    vout: float,
    iout: float,
    reported_pin: float | None = None,
    reported_pout: float | None = None,
    reported_loss: float | None = None,
    reported_efficiency_percent: float | None = None,
    abs_tol: float = 1e-6,
    rel_tol: float = 1e-6,
) -> list[QualityIssue]:
    """检查电压/电流/功率字段的自洽性。

    任一基础字段非法时立即返回，避免用错误数据继续计算。
    """
    issues: list[QualityIssue] = []
    values = {"vin": vin, "iin": iin, "vout": vout, "iout": iout}
    converted: dict[str, float] = {}

    for name, value in values.items():
        if isinstance(value, bool):
            issues.append(
                QualityIssue("INVALID_NUMBER", "ERROR", f"Invalid {name}")
            )
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            issues.append(
                QualityIssue("INVALID_NUMBER", "ERROR", f"Invalid {name}")
            )
            continue
        if not math.isfinite(number):
            issues.append(
                QualityIssue("NON_FINITE", "ERROR", f"Non-finite {name}")
            )
        elif number < 0:
            issues.append(
                QualityIssue("NEGATIVE_VALUE", "ERROR", f"Negative {name}")
            )
        else:
            converted[name] = number

    if issues:
        return issues

    pin = converted["vin"] * converted["iin"]
    pout = converted["vout"] * converted["iout"]

    if not (math.isfinite(pin) and math.isfinite(pout)):
        return [
            QualityIssue(
                "INVALID_POWER", "ERROR", "Calculated power is not finite"
            )
        ]

    if pout > pin and not math.isclose(
        pout, pin, rel_tol=rel_tol, abs_tol=abs_tol
    ):
        issues.append(
            QualityIssue(
                "POWER_BALANCE_ERROR",
                "ERROR",
                "Output power exceeds input power",
            )
        )

    if pin == 0 and pout > 0:
        issues.append(
            QualityIssue(
                "ZERO_INPUT_POWER",
                "ERROR",
                "Input power is zero but output power is positive",
            )
        )

    reported_values = [
        ("input power", reported_pin, pin),
        ("output power", reported_pout, pout),
        ("power loss", reported_loss, pin - pout),
    ]

    for name, reported, expected in reported_values:
        if reported is None:
            continue
        value = _to_number(reported)
        if value is None:
            issues.append(
                QualityIssue(
                    "INVALID_REPORTED_VALUE", "ERROR", f"Invalid {name}"
                )
            )
            continue
        if not math.isclose(value, expected, rel_tol=rel_tol, abs_tol=abs_tol):
            issues.append(
                QualityIssue(
                    "METRIC_MISMATCH", "ERROR", f"Inconsistent {name}"
                )
            )

    if reported_efficiency_percent is not None:
        value = _to_number(reported_efficiency_percent)
        if value is None:
            issues.append(
                QualityIssue(
                    "INVALID_REPORTED_VALUE",
                    "ERROR",
                    "Invalid efficiency",
                )
            )
        elif pin == 0:
            issues.append(
                QualityIssue(
                    "METRIC_MISMATCH",
                    "ERROR",
                    "Efficiency should be undefined when input power is zero",
                )
            )
        else:
            expected = pout / pin * 100.0
            if not math.isclose(value, expected, rel_tol=rel_tol, abs_tol=abs_tol):
                issues.append(
                    QualityIssue(
                        "METRIC_MISMATCH",
                        "ERROR",
                        "Inconsistent efficiency",
                    )
                )

    return issues


def validate_record(
    record: Mapping[str, Any],
    *,
    expected_source: str | None = "behavioral_model",
    require_context: bool = True,
    abs_tol: float = 1e-6,
    rel_tol: float = 1e-6,
    index: int = -1,
) -> RecordQuality:
    """检查单条记录，返回问题列表；不修改原始记录。"""
    issues: list[QualityIssue] = []

    if not isinstance(record, Mapping):
        return RecordQuality(
            index=index,
            issues=(
                QualityIssue(
                    "INVALID_RECORD", "ERROR", "Record is not a mapping"
                ),
            ),
        )

    for field in REQUIRED_FIELDS:
        if field not in record:
            issues.append(
                QualityIssue(
                    "MISSING_FIELD", "ERROR", f"Missing required field: {field}"
                )
            )

    if require_context:
        for field in CONTEXT_FIELDS:
            if record.get(field) is None:
                issues.append(
                    QualityIssue(
                        "MISSING_CONTEXT",
                        "WARNING",
                        f"Missing operating context: {field}",
                    )
                )

    # 基础字段缺失时无法继续计算功率关系
    if any(issue.code == "MISSING_FIELD" and issue.message.split(": ")[-1] in POWER_FIELDS for issue in issues):
        return RecordQuality(index=index, issues=tuple(issues))

    issues.extend(
        inspect_power_data(
            record.get("vin"),
            record.get("iin"),
            record.get("vout"),
            record.get("iout"),
            reported_pin=record.get("pin"),
            reported_pout=record.get("pout"),
            reported_loss=record.get("power_loss"),
            reported_efficiency_percent=record.get("efficiency_percent"),
            abs_tol=abs_tol,
            rel_tol=rel_tol,
        )
    )

    # 效率异常：保留原始数值，由上层标记 ERROR
    efficiency = record.get("efficiency_percent")
    if efficiency is None and record.get("efficiency") is not None:
        factor = _to_number(record.get("efficiency"))
        if factor is not None:
            efficiency = factor * 100.0
    if efficiency is not None:
        value = _to_number(efficiency)
        if value is None:
            issues.append(
                QualityIssue("INVALID_NUMBER", "ERROR", "Invalid efficiency")
            )
        elif value > 100.0:
            issues.append(
                QualityIssue(
                    "EFFICIENCY_ABOVE_100",
                    "ERROR",
                    f"Efficiency {value:.6f}% exceeds 100%",
                )
            )

    state = record.get("state")
    if state not in VALID_STATES:
        issues.append(
            QualityIssue("INVALID_STATE", "ERROR", f"Unknown state: {state!r}")
        )
    elif state in PROTECTION_STATES:
        outputs = [
            _to_number(record.get("vout")),
            _to_number(record.get("iout")),
            _to_number(record.get("pin")),
            _to_number(record.get("pout")),
        ]
        if any(value is None or abs(value) > abs_tol for value in outputs):
            issues.append(
                QualityIssue(
                    "STATE_OUTPUT_MISMATCH",
                    "ERROR",
                    f"Protection state {state} must output zeros",
                )
            )

    source = record.get("source")
    if not isinstance(source, str) or not source.strip():
        issues.append(
            QualityIssue("INVALID_SOURCE", "ERROR", "Missing data source")
        )
    elif expected_source is not None and source != expected_source:
        issues.append(
            QualityIssue(
                "SOURCE_MISMATCH",
                "ERROR",
                f"Expected source {expected_source}, got {source}",
            )
        )

    return RecordQuality(index=index, issues=tuple(issues))


def detect_duplicate_records(
    records: Sequence[Mapping[str, Any]],
) -> tuple[tuple[int, ...], ...]:
    """按工况参数检测重复记录，返回重复索引分组。

    同一工况重复测量在统计模块中用于计算离散程度；但在“每工况一条”
    的数据集中重复出现通常意味着采集或拼接错误，因此由调用方决定
    是否排除。本函数只检测，不删除。
    """
    groups: dict[tuple, list[int]] = {}
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            continue
        key = (
            record.get("vin_setpoint"),
            record.get("input_current_limit"),
            record.get("load_current_setpoint"),
        )
        if all(value is None for value in key):
            key = (
                record.get("vin"),
                record.get("iin"),
                record.get("vout"),
                record.get("iout"),
            )
        groups.setdefault(key, []).append(index)
    return tuple(tuple(indices) for indices in groups.values() if len(indices) > 1)


def validate_dataset(
    records: Sequence[Mapping[str, Any]],
    *,
    expected_source: str | None = "behavioral_model",
    require_context: bool = True,
    detect_duplicates: bool = True,
    abs_tol: float = 1e-6,
    rel_tol: float = 1e-6,
) -> DatasetQualityReport:
    """检查整个数据集，保留原始记录并记录排除原因。"""
    record_results = tuple(
        validate_record(
            record,
            expected_source=expected_source,
            require_context=require_context,
            abs_tol=abs_tol,
            rel_tol=rel_tol,
            index=index,
        )
        for index, record in enumerate(records)
    )

    dataset_issues: list[QualityIssue] = []
    excluded: list[int] = []
    reasons: list[str] = []

    if detect_duplicates:
        for group in detect_duplicate_records(records):
            # 保留第一次出现，后续重复项排除，避免重复计入统计
            for index in group[1:]:
                excluded.append(index)
                reasons.append(f"duplicate of record {group[0]}")
            dataset_issues.append(
                QualityIssue(
                    "DUPLICATE_RECORD",
                    "WARNING",
                    f"Duplicate operating points: {list(group)}",
                )
            )

    for result in record_results:
        if not result.valid and result.index not in excluded:
            excluded.append(result.index)
            reasons.append(
                "invalid data: "
                + "; ".join(
                    issue.code
                    for issue in result.issues
                    if issue.severity == "ERROR"
                )
            )

    return DatasetQualityReport(
        total_records=len(records),
        records=record_results,
        dataset_issues=tuple(dataset_issues),
        excluded_indices=tuple(excluded),
        excluded_reasons=tuple(reasons),
    )


def summarize_quality_issues(
    issues: Iterable[QualityIssue],
) -> dict[str, Any]:
    """统计问题数量与代码分布。"""
    issue_list = list(issues)
    by_code: dict[str, int] = {}
    for issue in issue_list:
        by_code[issue.code] = by_code.get(issue.code, 0) + 1
    return {
        "total": len(issue_list),
        "error_count": sum(
            1 for issue in issue_list if issue.severity == "ERROR"
        ),
        "warning_count": sum(
            1 for issue in issue_list if issue.severity == "WARNING"
        ),
        "by_code": by_code,
    }
