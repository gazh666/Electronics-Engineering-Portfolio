"""YAML 测试用例与测试方案加载器。

职责
----
- 读取并校验 ``configs/test_cases.yaml``、``configs/test_suites.yaml``；
- 在**控制任何仪器之前**完成全部配置检查，校验失败直接抛 ``ValueError``；
- 把配置转换为不可变的 :class:`TestCase` / :class:`TestSuite`。

校验范围
--------
必要字段、字段类型、重复 ID、数值有限性、上下限顺序、未知指标、
未知字段、布尔字段（拒绝 ``"false"`` 之类的字符串）、方案引用完整性。

参数范围优先复用仪器驱动常量（``instruments.power_supply`` 与
``instruments.electronic_load`` 的额定范围），避免在两处维护同一限制。
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import yaml

from instruments.electronic_load import MAX_CURRENT as LOAD_MAX_CURRENT
from instruments.electronic_load import MIN_CURRENT as LOAD_MIN_CURRENT
from models.virtual_dut import DUTState

from .models import TestCase, TestSuite

#: 当前支持的配置版本
SUPPORTED_VERSION = "1.0"

#: 每个配置文件的已知顶层字段（未知字段直接拒绝，避免拼写错误被忽略）
TOP_LEVEL_KEYS = {"version", "specification_type", "notes", "test_cases"}
SUITE_TOP_LEVEL_KEYS = {"version", "specification_type", "notes", "test_suites"}

#: 用例允许的字段
CASE_KEYS = {
    "id",
    "name",
    "category",
    "vin",
    "input_current_limit",
    "load_current",
    "expected_state",
    "output_enabled",
    "load_enabled",
    "enabled",
    "limits",
}

#: 测试方案允许的字段
SUITE_KEYS = {"id", "name", "cases", "stop_on_fail", "stop_on_error"}

#: 允许的 DUT 状态（与模型枚举保持单一来源）
VALID_STATES = {state.value for state in DUTState}

#: 输入电压范围复用程控电源驱动（0-30 V）
VIN_MIN = 0.0
VIN_MAX = 30.0

#: 限值允许的指标名：原始模型字段 + 派生指标字段
LIMIT_KEYS = {
    "vin",
    "iin",
    "vout",
    "iout",
    "pin",
    "pout",
    "power_loss",
    "efficiency_percent",
    "voltage_error_v",
    "voltage_error_percent",
    "absolute_voltage_error_percent",
}


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} 必须是映射")
    return value


def _require_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} 必须是非空字符串")
    return value.strip()


def validate_number(
    value: Any, name: str, minimum: float, maximum: float
) -> float:
    """校验有限数字并返回 float；布尔、字符串、NaN/inf 一律拒绝。"""
    if isinstance(value, bool):
        raise ValueError(f"{name} 不能是布尔值")
    if not isinstance(value, (int, float)):
        raise ValueError(f"{name} 必须是数字，收到 {value!r}")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} 必须是有限数值，收到 {value!r}")
    if not minimum <= number <= maximum:
        raise ValueError(
            f"{name} 超出允许范围 {minimum:g}-{maximum:g}，收到 {number:g}"
        )
    return number


def validate_bool(value: Any, name: str) -> bool:
    """严格校验布尔字段，禁止 ``bool("false")`` 这种错误转换。"""
    if not isinstance(value, bool):
        raise ValueError(f"{name} 必须是布尔值 true/false，收到 {value!r}")
    return value


def validate_limits(raw: Any, case_id: str) -> dict[str, dict[str, float]]:
    """校验限值结构：只允许已登记指标，且必须同时提供 min/max。"""
    if raw is None:
        return {}
    limits = _require_mapping(raw, f"{case_id}.limits")

    validated: dict[str, dict[str, float]] = {}
    for metric, bounds in limits.items():
        if metric not in LIMIT_KEYS:
            raise ValueError(
                f"{case_id}.limits 含未知指标 {metric!r}，"
                f"允许值: {', '.join(sorted(LIMIT_KEYS))}"
            )
        bound = _require_mapping(bounds, f"{case_id}.limits.{metric}")
        unknown = set(bound) - {"min", "max"}
        if unknown:
            raise ValueError(
                f"{case_id}.limits.{metric} 含未知字段: {', '.join(sorted(unknown))}"
            )
        if "min" not in bound or "max" not in bound:
            raise ValueError(f"{case_id}.limits.{metric} 必须同时提供 min 与 max")

        lower = validate_number(
            bound["min"], f"{case_id}.limits.{metric}.min", -1e9, 1e9
        )
        upper = validate_number(
            bound["max"], f"{case_id}.limits.{metric}.max", -1e9, 1e9
        )
        if lower > upper:
            raise ValueError(
                f"{case_id}.limits.{metric}: min={lower:g} 不能大于 max={upper:g}"
            )
        validated[metric] = {"min": lower, "max": upper}
    return validated


def _check_version(raw: Mapping[str, Any], label: str) -> None:
    version = raw.get("version")
    if version is None:
        raise ValueError(f"{label} 缺少 version 字段")
    if str(version).strip() != SUPPORTED_VERSION:
        raise ValueError(
            f"{label} 版本不受支持: {version!r}，当前仅支持 {SUPPORTED_VERSION}"
        )


def _check_unknown_keys(
    raw: Mapping[str, Any], allowed: Iterable[str], label: str
) -> None:
    unknown = set(raw) - set(allowed)
    if unknown:
        raise ValueError(f"{label} 含未知字段: {', '.join(sorted(unknown))}")


def load_test_cases(path: str | Path) -> list[TestCase]:
    """读取测试用例文件并返回 ``TestCase`` 列表。

    任一字段非法都会在返回前抛出 ``ValueError``，调用方不应继续控制仪器。
    """
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"测试用例文件不存在: {config_path}")

    with config_path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file)

    if not isinstance(raw, Mapping):
        raise ValueError("测试用例文件顶层必须是映射")

    _check_version(raw, "测试用例文件")
    _check_unknown_keys(raw, TOP_LEVEL_KEYS, "测试用例文件")

    specification_type = raw.get("specification_type")
    if specification_type is not None:
        _require_text(specification_type, "specification_type")

    entries = raw.get("test_cases")
    if not isinstance(entries, list):
        raise ValueError("test_cases 必须是列表")
    if not entries:
        raise ValueError("test_cases 不能为空")

    cases: list[TestCase] = []
    seen_ids: set[str] = set()

    for index, entry in enumerate(entries):
        label = f"test_cases[{index}]"
        item = _require_mapping(entry, label)
        _check_unknown_keys(item, CASE_KEYS, label)

        case_id = _require_text(item.get("id"), f"{label}.id")
        if case_id in seen_ids:
            raise ValueError(f"重复的用例编号: {case_id}")
        seen_ids.add(case_id)

        name = _require_text(item.get("name"), f"{case_id}.name")
        category = _require_text(item.get("category"), f"{case_id}.category")

        expected_state = item.get("expected_state")
        if expected_state not in VALID_STATES:
            raise ValueError(
                f"{case_id}.expected_state 非法: {expected_state!r}，"
                f"允许值: {', '.join(sorted(VALID_STATES))}"
            )

        for key in ("vin", "input_current_limit", "load_current", "expected_state"):
            if key not in item:
                raise ValueError(f"{case_id} 缺少必要字段: {key}")

        case = TestCase(
            case_id=case_id,
            name=name,
            category=category,
            vin=validate_number(item["vin"], f"{case_id}.vin", VIN_MIN, VIN_MAX),
            input_current_limit=validate_number(
                item["input_current_limit"],
                f"{case_id}.input_current_limit",
                LOAD_MIN_CURRENT,
                LOAD_MAX_CURRENT,
            ),
            load_current=validate_number(
                item["load_current"],
                f"{case_id}.load_current",
                LOAD_MIN_CURRENT,
                LOAD_MAX_CURRENT,
            ),
            expected_state=expected_state,
            output_enabled=validate_bool(
                item.get("output_enabled", True), f"{case_id}.output_enabled"
            ),
            load_enabled=validate_bool(
                item.get("load_enabled", True), f"{case_id}.load_enabled"
            ),
            enabled=validate_bool(item.get("enabled", True), f"{case_id}.enabled"),
            limits=validate_limits(item.get("limits"), case_id),
        )
        cases.append(case)

    return cases


def load_test_suites(
    path: str | Path, known_case_ids: Sequence[str]
) -> list[TestSuite]:
    """读取测试方案文件，并校验其引用的用例全部存在。"""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"测试方案文件不存在: {config_path}")

    with config_path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file)

    if not isinstance(raw, Mapping):
        raise ValueError("测试方案文件顶层必须是映射")

    _check_version(raw, "测试方案文件")
    _check_unknown_keys(raw, SUITE_TOP_LEVEL_KEYS, "测试方案文件")

    known = set(known_case_ids)
    entries = raw.get("test_suites")
    if not isinstance(entries, list):
        raise ValueError("test_suites 必须是列表")
    if not entries:
        raise ValueError("test_suites 不能为空")

    suites: list[TestSuite] = []
    seen_ids: set[str] = set()

    for index, entry in enumerate(entries):
        label = f"test_suites[{index}]"
        item = _require_mapping(entry, label)
        _check_unknown_keys(item, SUITE_KEYS, label)

        suite_id = _require_text(item.get("id"), f"{label}.id")
        if suite_id in seen_ids:
            raise ValueError(f"重复的测试方案编号: {suite_id}")
        seen_ids.add(suite_id)

        name = _require_text(item.get("name"), f"{suite_id}.name")

        cases = item.get("cases")
        if not isinstance(cases, list) or not cases:
            raise ValueError(f"{suite_id}.cases 必须是非空列表")

        case_ids: list[str] = []
        for case_id in cases:
            case_id = _require_text(case_id, f"{suite_id}.cases[]")
            if case_id not in known:
                raise ValueError(f"{suite_id} 引用了不存在的用例: {case_id}")
            if case_id in case_ids:
                raise ValueError(f"{suite_id} 重复引用用例: {case_id}")
            case_ids.append(case_id)

        suites.append(
            TestSuite(
                suite_id=suite_id,
                name=name,
                case_ids=tuple(case_ids),
                stop_on_fail=validate_bool(
                    item.get("stop_on_fail", False), f"{suite_id}.stop_on_fail"
                ),
                stop_on_error=validate_bool(
                    item.get("stop_on_error", True), f"{suite_id}.stop_on_error"
                ),
            )
        )

    return suites
