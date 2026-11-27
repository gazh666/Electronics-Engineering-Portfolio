"""基础波形质量检查。

只判断"数据是否可用"，不判断"电路行为是否符合预期"：
- RLC 正常振荡过冲、二极管非线性偏差都属于合法数据；
- 只有空数据、非有限值、轴不递增、长度不一致、区间未覆盖等问题才判为非法。
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping

import numpy as np


def _report(ok: bool, detail: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": bool(ok), "detail": detail}
    payload.update(extra)
    return payload


def check_not_empty(name: str, values: Any) -> dict[str, Any]:
    size = int(np.asarray(values).size)
    return _report(size > 0, f"{name} has {size} samples", sample_count=size)


def check_finite(name: str, values: Any) -> dict[str, Any]:
    array = np.asarray(values)
    if array.size == 0:
        return _report(False, f"{name} is empty")
    if np.iscomplexobj(array):
        ok = bool(np.isfinite(array.real).all() and np.isfinite(array.imag).all())
    else:
        ok = bool(np.isfinite(array).all())
    return _report(ok, f"{name} finite={ok}")


def check_strictly_increasing(name: str, values: Any, *, positive: bool = False) -> dict[str, Any]:
    array = np.asarray(values, dtype=float)
    if array.ndim != 1 or array.size < 2:
        return _report(False, f"{name} needs a 1D array with at least 2 samples")
    if not np.isfinite(array).all():
        return _report(False, f"{name} contains NaN or Infinity")
    if positive and np.any(array <= 0):
        return _report(False, f"{name} contains non-positive values")
    increasing = bool(np.all(np.diff(array) > 0))
    return _report(increasing, f"{name} strictly_increasing={increasing}")


def check_lengths(columns: Mapping[str, Any]) -> dict[str, Any]:
    lengths = {name: int(np.asarray(values).size) for name, values in columns.items()}
    ok = len(set(lengths.values())) <= 1
    return _report(ok, f"lengths={lengths}", lengths=lengths)


def check_complex_parts(real: Any, imag: Any, name: str) -> dict[str, Any]:
    real_array = np.asarray(real, dtype=float)
    imag_array = np.asarray(imag, dtype=float)
    if real_array.shape != imag_array.shape:
        return _report(False, f"{name} real/imag shape mismatch")
    ok = bool(np.isfinite(real_array).all() and np.isfinite(imag_array).all())
    return _report(ok, f"{name} complex parts finite={ok}")


def check_dc_sweep(
    sweep: Any,
    start_v: float,
    stop_v: float,
    step_v: float,
    *,
    tolerance: float = 1e-9,
) -> dict[str, Any]:
    """检查直流扫描方向、步长符号与覆盖区间。"""
    array = np.asarray(sweep, dtype=float)
    if array.ndim != 1 or array.size < 2:
        return _report(False, "DC sweep needs at least 2 samples")
    if not np.isfinite(array).all():
        return _report(False, "DC sweep contains NaN or Infinity")

    ascending = stop_v > start_v
    diffs = np.diff(array)
    direction_ok = bool(np.all(diffs > 0)) if ascending else bool(np.all(diffs < 0))
    step_ok = bool(np.all(np.isclose(np.abs(diffs), abs(step_v), rtol=1e-6, atol=tolerance)))
    low, high = (start_v, stop_v) if ascending else (stop_v, start_v)
    span = abs(high - low)
    cover_ok = bool(
        array.min() <= low + max(tolerance, span * 1e-6)
        and array.max() >= high - max(tolerance, span * 1e-6)
    )
    ok = direction_ok and step_ok and cover_ok
    return _report(
        ok,
        f"direction_ok={direction_ok}, step_ok={step_ok}, coverage_ok={cover_ok}",
        direction_ok=direction_ok,
        step_ok=step_ok,
        coverage_ok=cover_ok,
        sample_count=int(array.size),
        start=float(array[0]),
        stop=float(array[-1]),
    )


def check_frequency_axis(
    frequency_hz: Any,
    start_hz: float | None = None,
    stop_hz: float | None = None,
) -> dict[str, Any]:
    """检查频率轴为正、严格递增并覆盖请求区间。"""
    array = np.asarray(frequency_hz, dtype=float)
    if array.ndim != 1 or array.size < 2:
        return _report(False, "frequency axis needs at least 2 samples")
    if not np.isfinite(array).all() or np.any(array <= 0):
        return _report(False, "frequency axis must be finite and positive")
    increasing = bool(np.all(np.diff(array) > 0))
    coverage = True
    if start_hz is not None and stop_hz is not None:
        coverage = bool(
            array[0] <= start_hz * (1 + 1e-9)
            and array[-1] >= stop_hz * (1 - 1e-9)
        )
    ok = increasing and coverage
    return _report(
        ok,
        f"strictly_increasing={increasing}, coverage={coverage}",
        strictly_increasing=increasing,
        coverage=coverage,
        sample_count=int(array.size),
        start_hz=float(array[0]),
        stop_hz=float(array[-1]),
    )


def check_time_axis(
    time_s: Any,
    *,
    expected_end_s: float | None = None,
    tolerance_s: float | None = None,
) -> dict[str, Any]:
    """检查时间轴严格递增，并确认仿真实际结束时间达到要求。"""
    array = np.asarray(time_s, dtype=float)
    if array.ndim != 1 or array.size < 2:
        return _report(False, "time axis needs at least 2 samples")
    if not np.isfinite(array).all():
        return _report(False, "time axis contains NaN or Infinity")
    if array[0] < 0:
        return _report(False, "time axis starts before 0 s")
    increasing = bool(np.all(np.diff(array) > 0))
    reached = True
    tolerance = tolerance_s
    if expected_end_s is not None:
        if tolerance is None:
            tolerance = max(1e-12, abs(expected_end_s) * 1e-6)
        reached = bool(array[-1] >= expected_end_s - tolerance)
    ok = increasing and reached
    return _report(
        ok,
        f"strictly_increasing={increasing}, reached_end={reached}",
        strictly_increasing=increasing,
        reached_end=reached,
        sample_count=int(array.size),
        start_s=float(array[0]),
        end_s=float(array[-1]),
        expected_end_s=expected_end_s,
    )


def combine_checks(checks: Iterable[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    """合并多个检查结果；任一项失败则整体非法。"""
    details: dict[str, Any] = {}
    issues: list[str] = []
    for name, report in checks:
        details[name] = report
        if not report.get("ok", False):
            issues.append(f"{name}: {report.get('detail', 'failed')}")
    return {"valid": not issues, "issues": issues, "checks": details}


def assess_operating_point(nodes: Mapping[str, float], branches: Mapping[str, float]) -> dict[str, Any]:
    """工作点数据质量：非空且全部有限。"""
    checks = [("nodes_finite", check_finite("operating point nodes", list(nodes.values())))]
    if branches:
        checks.append(("branches_finite", check_finite("operating point branches", list(branches.values()))))
    else:
        checks.append(("branches_finite", _report(True, "no branch currents recorded")))
    return combine_checks(checks)


def assess_dc(
    sweep: Any,
    columns: Mapping[str, Any],
    start_v: float,
    stop_v: float,
    step_v: float,
) -> dict[str, Any]:
    """直流扫描数据质量。"""
    checks: list[tuple[str, dict[str, Any]]] = [
        ("sweep", check_dc_sweep(sweep, start_v, stop_v, step_v)),
        ("lengths", check_lengths({"sweep": sweep, **columns})),
    ]
    for name, values in columns.items():
        checks.append((f"finite:{name}", check_finite(name, values)))
    return combine_checks(checks)


def assess_ac(
    frequency_hz: Any,
    columns: Mapping[str, Any],
    *,
    start_hz: float,
    stop_hz: float,
    complex_pairs: Mapping[str, tuple[Any, Any]],
) -> dict[str, Any]:
    """交流扫描数据质量，包含复数完整性检查。"""
    checks: list[tuple[str, dict[str, Any]]] = [
        ("frequency", check_frequency_axis(frequency_hz, start_hz, stop_hz)),
        ("lengths", check_lengths({"frequency_hz": frequency_hz, **columns})),
    ]
    for name, values in columns.items():
        checks.append((f"finite:{name}", check_finite(name, values)))
    for name, (real, imag) in complex_pairs.items():
        checks.append((f"complex:{name}", check_complex_parts(real, imag, name)))
    return combine_checks(checks)


def assess_transient(
    time_s: Any,
    columns: Mapping[str, Any],
    *,
    expected_end_s: float,
) -> dict[str, Any]:
    """瞬态数据质量，并报告采样是否非均匀。"""
    time_array = np.asarray(time_s, dtype=float)
    nonuniform = False
    if time_array.size >= 3:
        diffs = np.diff(time_array)
        nonuniform = bool(diffs.max() > diffs.min() * 1.05)

    checks: list[tuple[str, dict[str, Any]]] = [
        ("time", check_time_axis(time_array, expected_end_s=expected_end_s)),
        ("lengths", check_lengths({"time_s": time_array, **columns})),
    ]
    for name, values in columns.items():
        checks.append((f"finite:{name}", check_finite(name, values)))

    report = combine_checks(checks)
    report["nonuniform_sampling"] = nonuniform
    report["checks"]["sampling"] = _report(
        True,
        f"nonuniform_sampling={nonuniform}",
        nonuniform_sampling=nonuniform,
    )
    return report


def ensure_valid(report: Mapping[str, Any], context: str) -> None:
    """质量报告非法时抛 ``ValueError``（由调用方包装成仿真异常）。"""
    if report.get("valid", False):
        return
    issues = "; ".join(report.get("issues", [])) or "unknown issue"
    raise ValueError(f"{context} waveform quality check failed: {issues}")
