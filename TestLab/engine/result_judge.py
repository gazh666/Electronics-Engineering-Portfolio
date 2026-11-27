"""测试判定：把测量值与工程限值比较，输出 PASS/FAIL/ERROR。

本模块提供两层接口：

- 旧接口 ``judge`` / ``judge_voltage``：返回 ``PASS / FAIL / ERROR`` 字符串；
- 阶段七接口 ``judge_state`` / ``judge_range`` / ``aggregate_status``：
  返回带实际值、期望值与说明的 :class:`CheckResult`，供执行引擎使用。

判定优先级固定为 ``ERROR > FAIL > PASS``；``SKIP`` 只表示用例未执行或
明确标记为不适用的检查项，不会掩盖异常。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

from .models import CheckResult, TestStatus


@dataclass(frozen=True)
class JudgeResult:
    """单项判定结果。"""

    passed: bool
    detail: str


def judge_voltage(value: float, lower: float, upper: float) -> str:
    """按上下限判定单个电压值。

    Returns
    -------
    str
        - ``ERROR``：任一值非有限，或 ``lower > upper``（配置/数据错误）；
        - ``PASS``：``lower <= value <= upper``；
        - ``FAIL``：值超出限值。
    """
    if not all(math.isfinite(x) for x in (value, lower, upper)):
        return "ERROR"

    if lower > upper:
        return "ERROR"

    if lower <= value <= upper:
        return "PASS"

    return "FAIL"


def judge(value: float, minimum: float | None = None, maximum: float | None = None) -> JudgeResult:
    """按上下限判定单个测量值，返回带说明的判定对象。

    ``minimum``/``maximum`` 为 None 表示对应方向不设限。
    """
    if value is None or math.isnan(value):
        return JudgeResult(False, "测量值无效（NaN）")

    if minimum is not None and maximum is not None and minimum > maximum:
        raise ValueError(f"限值配置错误: min={minimum} > max={maximum}")

    if minimum is not None and value < minimum:
        return JudgeResult(False, f"{value:.6g} < 下限 {minimum:.6g}")
    if maximum is not None and value > maximum:
        return JudgeResult(False, f"{value:.6g} > 上限 {maximum:.6g}")

    bounds = []
    if minimum is not None:
        bounds.append(f"min={minimum:.6g}")
    if maximum is not None:
        bounds.append(f"max={maximum:.6g}")
    return JudgeResult(True, f"{value:.6g} 在限值内 ({', '.join(bounds) or '无限值'})")


# ---------------------------------------------------------------------------
# 阶段七：分层判定接口（数据质量 -> DUT 状态 -> 工程限值）
# ---------------------------------------------------------------------------


def judge_state(actual_state: Any, expected_state: Any) -> CheckResult:
    """比较 DUT 实际状态与用例预期状态。

    保护状态符合预期时属于 PASS（例如过流测试预期 OVERCURRENT）。
    """
    actual = getattr(actual_state, "value", actual_state)
    expected = getattr(expected_state, "value", expected_state)
    passed = actual == expected
    return CheckResult(
        name="dut_state",
        actual=actual,
        expected=expected,
        status=TestStatus.PASS if passed else TestStatus.FAIL,
        message=(
            "状态与预期一致"
            if passed
            else f"预期 {expected}，实际 {actual}"
        ),
    )


def judge_range(
    name: str,
    actual: Any,
    lower: float,
    upper: float,
    abs_tol: float = 1e-9,
) -> CheckResult:
    """判定一个数值是否落在 ``[lower, upper]`` 内。

    - 布尔值、字符串、``None``、NaN/inf 一律返回 ERROR，绝不当 PASS；
    - ``lower > upper`` 视为限值配置错误，直接抛 ``ValueError``；
    - ``abs_tol`` 只用于吸收浮点表示误差，不代表仪器测量不确定度。
    """
    expected = {"min": lower, "max": upper}

    if isinstance(actual, bool):
        return CheckResult(
            name=name,
            actual=actual,
            expected=expected,
            status=TestStatus.ERROR,
            message="测量值是布尔值，无法判定",
        )

    try:
        value = float(actual)
    except (TypeError, ValueError):
        return CheckResult(
            name=name,
            actual=actual,
            expected=expected,
            status=TestStatus.ERROR,
            message="指标缺失或不是数字，无法判定",
        )

    if not all(math.isfinite(item) for item in (value, lower, upper)):
        return CheckResult(
            name=name,
            actual=value,
            expected=expected,
            status=TestStatus.ERROR,
            message="指标或限值不是有限数值，无法判定",
        )

    if lower > upper:
        raise ValueError(
            f"{name}: 限值配置错误，min={lower:g} 大于 max={upper:g}"
        )

    passed = (lower - abs_tol) <= value <= (upper + abs_tol)
    return CheckResult(
        name=name,
        actual=value,
        expected=expected,
        status=TestStatus.PASS if passed else TestStatus.FAIL,
        message=(
            f"{value:.6g} 在 {lower:g}-{upper:g} 范围内"
            if passed
            else f"{value:.6g} 超出 {lower:g}-{upper:g} 范围"
        ),
    )


def aggregate_status(checks: Sequence[CheckResult]) -> TestStatus:
    """按 ``ERROR > FAIL > PASS`` 汇总检查项。

    没有检查项时返回 ERROR（不能因为“没检查”而默认通过）。
    全部为 SKIP 时才返回 SKIP。
    """
    if not checks:
        return TestStatus.ERROR

    statuses = {check.status for check in checks}
    if TestStatus.ERROR in statuses:
        return TestStatus.ERROR
    if TestStatus.FAIL in statuses:
        return TestStatus.FAIL
    if TestStatus.PASS in statuses:
        return TestStatus.PASS
    return TestStatus.SKIP
