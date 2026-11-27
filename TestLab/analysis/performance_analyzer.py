"""统一性能分析器：指标计算 + 数据质量检查 + 工程限值判定。

限值来自 ``configs/performance_limits.yaml``，与算法代码分离。
本模块只做确定性数值判定，不使用任何大模型或外部服务。
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from .data_quality import validate_record
from .metrics import PerformanceMetrics, calculate_metrics

#: 默认限值配置路径（相对项目根目录）
DEFAULT_LIMITS_PATH = (
    Path(__file__).resolve().parents[1] / "configs" / "performance_limits.yaml"
)

PROTECTION_STATES = frozenset(
    {
        "OUTPUT_OFF",
        "UNDERVOLTAGE",
        "OVERVOLTAGE",
        "OVERCURRENT",
        "INPUT_CURRENT_LIMIT",
    }
)


def _number(value: Any, name: str, *, allow_zero: bool = True) -> float:
    """读取有限数字，拒绝布尔、字符串和 NaN/inf。"""
    if isinstance(value, bool):
        raise ValueError(f"{name} 不能是布尔值")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} 必须是数字") from None
    if not math.isfinite(number):
        raise ValueError(f"{name} 必须是有限数值")
    if not allow_zero and number <= 0:
        raise ValueError(f"{name} 必须大于 0")
    if allow_zero and number < 0:
        raise ValueError(f"{name} 不能为负")
    return number


def _section(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = data.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"缺少或非法的配置段: {key}")
    return value


@dataclass(frozen=True)
class PerformanceLimits:
    """工程性能限值（教学项目自定义假设）。"""

    name: str
    specification_type: str
    nominal_output_voltage: float
    voltage_min_v: float
    voltage_max_v: float
    max_absolute_voltage_error_percent: float
    min_efficiency_percent: float
    max_efficiency_percent: float
    max_load_regulation_percent: float
    max_line_regulation_percent: float
    power_balance_absolute_tolerance_w: float
    power_balance_relative_tolerance: float
    notes: tuple[str, ...] = ()


def load_performance_limits(
    config_path: str | Path = DEFAULT_LIMITS_PATH,
) -> PerformanceLimits:
    """读取并校验 YAML 限值配置。"""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"性能限值配置不存在: {path}")

    with path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file)

    if not isinstance(raw, Mapping) or "profile" not in raw:
        raise ValueError("性能限值配置缺少 profile 段")

    profile = _section(raw, "profile")
    voltage = _section(profile, "output_voltage")
    error = _section(profile, "voltage_error")
    efficiency = _section(profile, "efficiency")
    load_regulation = _section(profile, "load_regulation")
    line_regulation = _section(profile, "line_regulation")
    data_quality = _section(profile, "data_quality")

    nominal = _number(
        profile.get("nominal_output_voltage"),
        "nominal_output_voltage",
        allow_zero=False,
    )
    voltage_min = _number(voltage.get("min_v"), "output_voltage.min_v")
    voltage_max = _number(voltage.get("max_v"), "output_voltage.max_v")
    if voltage_min >= voltage_max:
        raise ValueError("output_voltage.min_v 必须小于 max_v")
    if not voltage_min <= nominal <= voltage_max:
        raise ValueError("标称输出电压必须位于输出限值范围内")

    max_error = _number(
        error.get("max_absolute_percent"), "voltage_error.max_absolute_percent"
    )
    eff_min = _number(efficiency.get("min_percent"), "efficiency.min_percent")
    eff_max = _number(efficiency.get("max_percent"), "efficiency.max_percent")
    if eff_min > eff_max:
        raise ValueError("efficiency.min_percent 不能大于 max_percent")
    if eff_max > 100.0:
        raise ValueError("efficiency.max_percent 不能超过 100")

    load_reg = _number(
        load_regulation.get("max_percent"), "load_regulation.max_percent"
    )
    line_reg = _number(
        line_regulation.get("max_percent"), "line_regulation.max_percent"
    )
    abs_tol = _number(
        data_quality.get("power_balance_absolute_tolerance_w"),
        "data_quality.power_balance_absolute_tolerance_w",
    )
    rel_tol = _number(
        data_quality.get("power_balance_relative_tolerance"),
        "data_quality.power_balance_relative_tolerance",
    )

    notes_raw = profile.get("notes", [])
    if not isinstance(notes_raw, list) or not all(
        isinstance(note, str) for note in notes_raw
    ):
        raise ValueError("profile.notes 必须是字符串列表")

    name = profile.get("name", "unnamed")
    specification_type = profile.get("specification_type", "project_assumption")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("profile.name 必须是非空字符串")
    if not isinstance(specification_type, str) or not specification_type.strip():
        raise ValueError("profile.specification_type 必须是非空字符串")

    return PerformanceLimits(
        name=name,
        specification_type=specification_type,
        nominal_output_voltage=nominal,
        voltage_min_v=voltage_min,
        voltage_max_v=voltage_max,
        max_absolute_voltage_error_percent=max_error,
        min_efficiency_percent=eff_min,
        max_efficiency_percent=eff_max,
        max_load_regulation_percent=load_reg,
        max_line_regulation_percent=line_reg,
        power_balance_absolute_tolerance_w=abs_tol,
        power_balance_relative_tolerance=rel_tol,
        notes=tuple(notes_raw),
    )


def _check(
    metric: str,
    value: float | None,
    unit: str,
    *,
    lower: float | None = None,
    upper: float | None = None,
    status: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """组装单项限值检查结果。"""
    if status is None:
        if value is None:
            status = "N/A"
        elif lower is not None and value < lower:
            status = "FAIL"
        elif upper is not None and value > upper:
            status = "FAIL"
        else:
            status = "PASS"
    result = {
        "metric": metric,
        "value": value,
        "unit": unit,
        "lower": lower,
        "upper": upper,
        "status": status,
    }
    if reason is not None:
        result["reason"] = reason
    return result


class PerformanceAnalyzer:
    """把 DUT 结果转换为可用于报告的性能分析记录。"""

    def __init__(
        self,
        limits: PerformanceLimits | str | Path | None = None,
        *,
        expected_source: str = "behavioral_model",
    ) -> None:
        if limits is None:
            self.limits = load_performance_limits(DEFAULT_LIMITS_PATH)
        elif isinstance(limits, PerformanceLimits):
            self.limits = limits
        else:
            self.limits = load_performance_limits(limits)
        self.expected_source = expected_source

    @property
    def nominal_voltage(self) -> float:
        return self.limits.nominal_output_voltage

    def analyze(
        self,
        result: Any,
        *,
        expected_source: str | None = None,
    ) -> dict[str, Any]:
        """分析单条 DUT 结果，返回可 JSON 序列化的记录。

        原始字段保留在顶层，指标写入 ``metrics``，判定写入 ``checks``；
        不覆盖原始电压、电流、功率值。

        ``expected_source`` 用于故障注入的测量视图：调用方显式传入
        ``fault_injected_model`` 时，数据质量检查仍完整执行，只调整来源
        标签预期，不会关闭任何校验。
        """
        if hasattr(result, "__dataclass_fields__"):
            row = asdict(result)
        elif isinstance(result, Mapping):
            row = dict(result)
        else:
            raise TypeError("result 必须是 DUTResult 或映射")

        state = getattr(result, "state", row.get("state"))
        state_value = getattr(state, "value", state)
        row["state"] = state_value

        quality = validate_record(
            row,
            expected_source=(
                self.expected_source if expected_source is None else expected_source
            ),
            abs_tol=self.limits.power_balance_absolute_tolerance_w,
            rel_tol=self.limits.power_balance_relative_tolerance,
        )
        row["quality_issues"] = [asdict(issue) for issue in quality.issues]
        row["quality_status"] = "ERROR" if not quality.valid else "VALID"
        row["data_quality_status"] = row["quality_status"]

        if not quality.valid:
            row["metrics"] = None
            row["metric_status"] = "INVALID_DATA"
            row["checks"] = []
            return row

        if state_value != "NORMAL":
            row["metrics"] = None
            row["metric_status"] = "NOT_APPLICABLE"
            row["checks"] = [
                _check(
                    "output_voltage",
                    None,
                    "V",
                    lower=self.limits.voltage_min_v,
                    upper=self.limits.voltage_max_v,
                    status="N/A",
                    reason=f"保护状态 {state_value}，不参与稳压性能判定",
                ),
                _check(
                    "voltage_error",
                    None,
                    "%",
                    upper=self.limits.max_absolute_voltage_error_percent,
                    status="N/A",
                    reason=f"保护状态 {state_value}，不参与电压误差判定",
                ),
                _check(
                    "efficiency",
                    None,
                    "%",
                    lower=self.limits.min_efficiency_percent,
                    upper=self.limits.max_efficiency_percent,
                    status="N/A",
                    reason="保护状态，效率不可定义",
                ),
            ]
            return row

        metrics: PerformanceMetrics = calculate_metrics(
            vin=row["vin"],
            iin=row["iin"],
            vout=row["vout"],
            iout=row["iout"],
            nominal_voltage=self.nominal_voltage,
        )
        row["metrics"] = asdict(metrics)
        row["metric_status"] = "AVAILABLE"
        row["efficiency_percent"] = metrics.efficiency_percent

        checks = [
            _check(
                "output_voltage",
                row["vout"],
                "V",
                lower=self.limits.voltage_min_v,
                upper=self.limits.voltage_max_v,
            ),
            _check(
                "voltage_error",
                metrics.absolute_voltage_error_percent,
                "%",
                upper=self.limits.max_absolute_voltage_error_percent,
            ),
        ]

        if metrics.efficiency_percent is None:
            checks.append(
                _check(
                    "efficiency",
                    None,
                    "%",
                    lower=self.limits.min_efficiency_percent,
                    upper=self.limits.max_efficiency_percent,
                    status="N/A",
                    reason="输入功率为 0，效率不可定义（空载）",
                )
            )
        else:
            checks.append(
                _check(
                    "efficiency",
                    metrics.efficiency_percent,
                    "%",
                    lower=self.limits.min_efficiency_percent,
                    upper=self.limits.max_efficiency_percent,
                )
            )

        # 调整率是扫描级指标，单条记录不判定
        checks.extend(
            [
                _check(
                    "load_regulation",
                    None,
                    "%",
                    upper=self.limits.max_load_regulation_percent,
                    status="N/A",
                    reason="需要空载/满载扫描数据集",
                ),
                _check(
                    "line_regulation",
                    None,
                    "%",
                    upper=self.limits.max_line_regulation_percent,
                    status="N/A",
                    reason="需要输入电压扫描数据集",
                ),
            ]
        )
        row["checks"] = checks
        return row

    def analyze_many(self, results: Sequence[Any]) -> list[dict[str, Any]]:
        """批量分析，逐条保留原始数据与判定结果。"""
        return [self.analyze(result) for result in results]
