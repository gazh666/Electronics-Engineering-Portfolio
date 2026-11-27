"""故障场景数据结构、严格校验与 YAML 加载。

设计原则
--------
- 配置（想要注入什么）与运行时计数（实际注入了几次）严格分离；
- 每个场景都有唯一编号，并在构造时完成全部合法性检查；
- 同一时刻命中同一操作的两个场景视为**冲突配置**，直接拒绝，避免
  依赖隐式优先级产生不可解释的实验结果；
- 所有参数必须是确定性的有限值，不使用随机数。

场景只在“用户显式选择”时才会进入执行流程。普通测试默认不加载任何
活动故障。
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import yaml

#: 测量故障视图的数据来源标签
FAULT_INJECTED_SOURCE = "fault_injected_model"

#: 可被测量故障修改的字段
MEASUREMENT_FIELDS = ("vin", "iin", "vout", "iout")

#: 支持注入的故障类型
class FaultType(str, Enum):
    """故障类型。

    通信类：``TIMEOUT`` / ``DISCONNECT`` / ``INVALID_RESPONSE``；
    测量数据类：``NAN_VALUE`` / ``INFINITY_VALUE`` / ``VOLTAGE_OFFSET`` /
    ``CURRENT_OFFSET``；
    清理类：``SHUTDOWN_FAILURE``。
    """

    #: 阻止 pytest 把本枚举当作测试类收集
    __test__ = False

    TIMEOUT = "TIMEOUT"
    DISCONNECT = "DISCONNECT"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    NAN_VALUE = "NAN_VALUE"
    INFINITY_VALUE = "INFINITY_VALUE"
    VOLTAGE_OFFSET = "VOLTAGE_OFFSET"
    CURRENT_OFFSET = "CURRENT_OFFSET"
    SHUTDOWN_FAILURE = "SHUTDOWN_FAILURE"


class FaultTarget(str, Enum):
    """故障注入位置。"""

    #: 阻止 pytest 把本枚举当作测试类收集
    __test__ = False

    INSTRUMENT_QUERY = "instrument_query"
    INSTRUMENT_WRITE = "instrument_write"
    MODEL_MEASUREMENT = "model_measurement"
    CLEANUP = "cleanup"


_MEASUREMENT_TYPES = frozenset(
    {
        FaultType.NAN_VALUE,
        FaultType.INFINITY_VALUE,
        FaultType.VOLTAGE_OFFSET,
        FaultType.CURRENT_OFFSET,
    }
)
_OFFSET_TYPES = frozenset({FaultType.VOLTAGE_OFFSET, FaultType.CURRENT_OFFSET})
_COMMUNICATION_TYPES = frozenset(
    {FaultType.TIMEOUT, FaultType.DISCONNECT}
)

_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$")
_DEVICE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_\-]*$")

#: YAML 顶层允许字段
_SCENARIO_FILE_KEYS = {"version", "simulation_only", "notes", "scenarios"}

#: 单个场景允许字段
_SCENARIO_KEYS = {
    "id",
    "name",
    "fault_type",
    "target",
    "operation",
    "trigger_at",
    "occurrences",
    "offset",
    "enabled",
    "device",
    "case_id",
}

SUPPORTED_VERSION = "1.0"


def _require_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} 必须是非空字符串")
    return value.strip()


def _require_int(value: Any, label: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} 必须是整数，收到 {value!r}")
    if not minimum <= value <= maximum:
        raise ValueError(
            f"{label} 必须在 {minimum}-{maximum} 之间，收到 {value}"
        )
    return value


def _require_finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} 必须是数字，收到 {value!r}")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} 必须是有限数值，收到 {value!r}")
    return number


def _require_bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} 必须是布尔值 true/false，收到 {value!r}")
    return value


@dataclass(frozen=True)
class FaultScenario:
    """一条不可变的故障场景配置。

    Parameters
    ----------
    scenario_id
        场景编号，例如 ``F001``；必须唯一。
    name
        人类可读名称。
    fault_type
        :class:`FaultType` 成员（也接受同名字符串）。
    target
        :class:`FaultTarget` 成员（也接受同名字符串）。
    operation
        目标操作：SCPI 命令（``VOLT?`` / ``OUTP 0``）或测量字段
        （``vout`` / ``iin``）。
    trigger_at
        第几次匹配时开始注入，必须 >= 1。
    occurrences
        最多注入次数，必须 >= 1；不会无限注入。
    offset
        偏移量（仅 ``VOLTAGE_OFFSET`` / ``CURRENT_OFFSET`` 使用）。
    enabled
        场景是否启用；默认 ``True``，但整个注入器还需要显式启用。
    device
        目标仪器编号（如 ``PS001``）；``None`` 表示不限定仪器。
    case_id
        仅对指定用例生效；``None`` 表示所有用例。
    """

    #: 阻止 pytest 把本类当作测试用例收集
    __test__ = False

    scenario_id: str
    name: str
    fault_type: FaultType
    target: FaultTarget
    operation: str
    trigger_at: int = 1
    occurrences: int = 1
    offset: float = 0.0
    enabled: bool = True
    device: str | None = None
    case_id: str | None = None

    def __post_init__(self) -> None:
        scenario_id = _require_text(self.scenario_id, "scenario_id")
        if not _ID_PATTERN.match(scenario_id):
            raise ValueError(
                f"scenario_id 只能包含字母、数字、下划线、点和短横线: {scenario_id!r}"
            )
        object.__setattr__(self, "scenario_id", scenario_id)
        object.__setattr__(self, "name", _require_text(self.name, "name"))
        object.__setattr__(
            self,
            "fault_type",
            _coerce_enum(self.fault_type, FaultType, "fault_type"),
        )
        object.__setattr__(
            self,
            "target",
            _coerce_enum(self.target, FaultTarget, "target"),
        )
        operation = _require_text(self.operation, "operation")
        object.__setattr__(self, "operation", operation)
        object.__setattr__(
            self, "trigger_at", _require_int(self.trigger_at, "trigger_at", 1, 1000)
        )
        object.__setattr__(
            self,
            "occurrences",
            _require_int(self.occurrences, "occurrences", 1, 1000),
        )
        object.__setattr__(self, "offset", _require_finite(self.offset, "offset"))
        object.__setattr__(self, "enabled", _require_bool(self.enabled, "enabled"))

        if self.device is not None:
            device = _require_text(self.device, "device")
            if not _DEVICE_PATTERN.match(device):
                raise ValueError(f"device 格式非法: {device!r}")
            object.__setattr__(self, "device", device)
        if self.case_id is not None:
            object.__setattr__(
                self, "case_id", _require_text(self.case_id, "case_id")
            )

        self._validate_combination()

    def _validate_combination(self) -> None:
        """校验故障类型、注入位置与操作名称的组合是否自洽。"""
        fault = self.fault_type
        target = self.target
        operation = self.operation

        if fault in _MEASUREMENT_TYPES and target is not FaultTarget.MODEL_MEASUREMENT:
            raise ValueError(
                f"{self.scenario_id}: {fault.value} 只能用于 model_measurement"
            )
        if fault is FaultType.SHUTDOWN_FAILURE and target is not FaultTarget.CLEANUP:
            raise ValueError(
                f"{self.scenario_id}: SHUTDOWN_FAILURE 只能用于 cleanup"
            )
        if fault is FaultType.INVALID_RESPONSE and target is not FaultTarget.INSTRUMENT_QUERY:
            raise ValueError(
                f"{self.scenario_id}: INVALID_RESPONSE 只能用于 instrument_query"
            )
        if fault in _COMMUNICATION_TYPES and target is FaultTarget.MODEL_MEASUREMENT:
            raise ValueError(
                f"{self.scenario_id}: {fault.value} 不能用于 model_measurement"
            )

        if target is FaultTarget.MODEL_MEASUREMENT and operation not in MEASUREMENT_FIELDS:
            raise ValueError(
                f"{self.scenario_id}: 测量故障字段必须是 {MEASUREMENT_FIELDS}，"
                f"收到 {operation!r}"
            )
        if fault is FaultType.VOLTAGE_OFFSET and operation not in ("vin", "vout"):
            raise ValueError(
                f"{self.scenario_id}: VOLTAGE_OFFSET 只能作用于 vin/vout"
            )
        if fault is FaultType.CURRENT_OFFSET and operation not in ("iin", "iout"):
            raise ValueError(
                f"{self.scenario_id}: CURRENT_OFFSET 只能作用于 iin/iout"
            )
        if fault in _OFFSET_TYPES and self.offset == 0.0:
            raise ValueError(
                f"{self.scenario_id}: {fault.value} 必须提供非零 offset"
            )
        if fault not in _OFFSET_TYPES and self.offset != 0.0:
            raise ValueError(
                f"{self.scenario_id}: 只有偏移类故障允许设置 offset"
            )

    # --- 匹配辅助 ---

    def matches(
        self,
        target: FaultTarget | str,
        operation: str,
        device: str | None,
        case_id: str | None,
    ) -> bool:
        """判断本场景是否应作用于本次操作（不含触发次数判断）。"""
        if not self.enabled:
            return False
        target_value = getattr(target, "value", target)
        if self.target.value != target_value:
            return False
        if self.operation != operation:
            return False
        if self.device is not None and self.device != device:
            return False
        if self.case_id is not None and self.case_id != case_id:
            return False
        return True

    def conflicts_with(self, other: "FaultScenario") -> bool:
        """两个启用场景是否会同时命中同一操作。

        仪器或用例为 ``None`` 时视为通配，因此 ``None`` 与具体值也冲突。
        """
        if not (self.enabled and other.enabled):
            return False
        if self.target is not other.target or self.operation != other.operation:
            return False
        if (
            self.device is not None
            and other.device is not None
            and self.device != other.device
        ):
            return False
        if (
            self.case_id is not None
            and other.case_id is not None
            and self.case_id != other.case_id
        ):
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.scenario_id,
            "name": self.name,
            "fault_type": self.fault_type.value,
            "target": self.target.value,
            "operation": self.operation,
            "trigger_at": self.trigger_at,
            "occurrences": self.occurrences,
            "offset": self.offset,
            "enabled": self.enabled,
            "device": self.device,
            "case_id": self.case_id,
        }


def _coerce_enum(value: Any, enum_cls: type[Enum], label: str) -> Any:
    if isinstance(value, enum_cls):
        return value
    if isinstance(value, str):
        try:
            return enum_cls(value)
        except ValueError:
            pass
    allowed = ", ".join(member.value for member in enum_cls)
    raise ValueError(f"{label} 非法: {value!r}，允许值: {allowed}")


class FaultScenarioLibrary:
    """一组经过校验的故障场景，按编号检索。"""

    #: 阻止 pytest 把本类当作测试用例收集
    __test__ = False

    def __init__(
        self,
        scenarios: Sequence[FaultScenario],
        *,
        version: str = SUPPORTED_VERSION,
        simulation_only: bool = True,
        source_path: str | None = None,
    ) -> None:
        if str(version).strip() != SUPPORTED_VERSION:
            raise ValueError(
                f"故障场景文件版本不受支持: {version!r}，仅支持 {SUPPORTED_VERSION}"
            )
        if simulation_only is not True:
            raise ValueError("故障场景只允许在模拟环境使用（simulation_only: true）")

        ordered = list(scenarios)
        if not ordered:
            raise ValueError("故障场景列表不能为空")

        seen: dict[str, FaultScenario] = {}
        for scenario in ordered:
            if not isinstance(scenario, FaultScenario):
                raise TypeError("scenarios 必须全部是 FaultScenario")
            if scenario.scenario_id in seen:
                raise ValueError(f"重复的故障场景编号: {scenario.scenario_id}")
            seen[scenario.scenario_id] = scenario

        # 同一场景库允许多个“互斥实验”并存（例如 F001/F002 都注入 VOLT?），
        # 但一次运行只能选择其中一个；冲突在 FaultInjector 构造时强制校验。
        self._scenarios = tuple(ordered)
        self._by_id = seen
        self.version = SUPPORTED_VERSION
        self.simulation_only = True
        self.source_path = source_path

    # --- 查询 ---

    @property
    def scenarios(self) -> tuple[FaultScenario, ...]:
        return self._scenarios

    def ids(self) -> list[str]:
        return [scenario.scenario_id for scenario in self._scenarios]

    def get(self, scenario_id: str) -> FaultScenario:
        try:
            return self._by_id[scenario_id]
        except KeyError:
            raise KeyError(
                f"未知故障场景 {scenario_id!r}，可用: {', '.join(self.ids())}"
            ) from None

    def select(self, scenario_ids: Iterable[str]) -> list[FaultScenario]:
        """按编号选择场景，并拒绝未知或已禁用的场景。"""
        selected: list[FaultScenario] = []
        seen: set[str] = set()
        for scenario_id in scenario_ids:
            key = str(scenario_id).strip()
            if key in seen:
                raise ValueError(f"重复选择故障场景: {key}")
            seen.add(key)
            scenario = self.get(key)
            if not scenario.enabled:
                raise ValueError(f"故障场景 {key} 已禁用（enabled: false）")
            selected.append(scenario)
        if not selected:
            raise ValueError("至少需要选择一个故障场景")
        return selected

    def select_one(self, scenario_id: str) -> list[FaultScenario]:
        return self.select([scenario_id])

    def to_dicts(self) -> list[dict[str, Any]]:
        return [scenario.to_dict() for scenario in self._scenarios]


def _build_scenario(entry: Any, index: int) -> FaultScenario:
    label = f"scenarios[{index}]"
    if not isinstance(entry, Mapping):
        raise ValueError(f"{label} 必须是映射")
    unknown = set(entry) - _SCENARIO_KEYS
    if unknown:
        raise ValueError(f"{label} 含未知字段: {', '.join(sorted(unknown))}")

    scenario_id = entry.get("id")
    data = {
        "scenario_id": scenario_id,
        "name": entry.get("name"),
        "fault_type": entry.get("fault_type"),
        "target": entry.get("target"),
        "operation": entry.get("operation"),
        "trigger_at": entry.get("trigger_at", 1),
        "occurrences": entry.get("occurrences", 1),
        "offset": entry.get("offset", 0.0),
        "enabled": entry.get("enabled", True),
        "device": entry.get("device"),
        "case_id": entry.get("case_id"),
    }
    return FaultScenario(**data)


def load_fault_scenarios(path: str | Path) -> FaultScenarioLibrary:
    """读取并严格校验 ``configs/fault_scenarios.yaml``。"""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"故障场景配置不存在: {config_path}")

    with config_path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file)

    if not isinstance(raw, Mapping):
        raise ValueError("故障场景配置顶层必须是映射")
    unknown = set(raw) - _SCENARIO_FILE_KEYS
    if unknown:
        raise ValueError(f"故障场景配置含未知字段: {', '.join(sorted(unknown))}")

    entries = raw.get("scenarios")
    if not isinstance(entries, list) or not entries:
        raise ValueError("scenarios 必须是非空列表")

    notes = raw.get("notes", [])
    if not isinstance(notes, list) or not all(isinstance(note, str) for note in notes):
        raise ValueError("notes 必须是字符串列表")

    scenarios = [
        _build_scenario(entry, index) for index, entry in enumerate(entries)
    ]
    return FaultScenarioLibrary(
        scenarios,
        version=str(raw.get("version", SUPPORTED_VERSION)),
        simulation_only=raw.get("simulation_only", False),
        source_path=str(config_path),
    )
