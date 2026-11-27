"""确定性故障注入器（模拟环境）。

职责
----
- 在仪器查询/写入/清理钩子以及模型测量视图上注入**精确次数**的故障；
- 每个场景独立计数，状态只属于当前运行，不跨运行共享；
- 默认关闭；关闭时不改变任何正常行为；
- 注入事件在发生瞬间记录（可同时写入 :class:`FaultLogger`），
  不在任务结束后补造；
- 原始模型结果保持不变，测量故障通过 ``dataclasses.replace`` 生成独立视图。

故障注入不是真实硬件故障，不能用于证明真实设备的保护或可靠性。
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Any, Callable, Sequence

from .exceptions import (
    CommunicationTimeoutError,
    DeviceDisconnectedError,
    ReliabilityError,
    UnsafeShutdownError,
)
from .fault_logger import EventType, new_event
from .fault_models import (
    FAULT_INJECTED_SOURCE,
    MEASUREMENT_FIELDS,
    FaultScenario,
    FaultTarget,
    FaultType,
)

__all__ = [
    "FAULT_INJECTED_SOURCE",
    "INVALID_RESPONSE_TEXT",
    "FaultInjector",
    "apply_measurement_faults",
]

#: 非法响应注入返回的文本（驱动层解析时会被拒绝）
INVALID_RESPONSE_TEXT = "INVALID_DATA"


class FaultInjector:
    """按场景注入故障，并记录每次注入的完整上下文。"""

    #: 阻止 pytest 把本类当作测试用例收集
    __test__ = False

    def __init__(
        self,
        scenarios: Sequence[FaultScenario] | None = None,
        enabled: bool = False,
        *,
        run_id: str = "",
        case_id: str | None = None,
        event_sink: Callable[[dict[str, Any]], Any] | None = None,
    ) -> None:
        self.scenarios = list(scenarios or [])
        self.enabled = bool(enabled)
        self.run_id = run_id
        self.case_id = case_id
        self.event_sink = event_sink

        self.call_counts: dict[str, int] = {}
        self.injected_counts: dict[str, int] = {}
        self.events: list[dict[str, Any]] = []
        self.sink_errors: list[str] = []

        self._validate()

    # --- 校验 ---

    def _validate(self) -> None:
        seen: set[str] = set()
        for scenario in self.scenarios:
            if not isinstance(scenario, FaultScenario):
                raise TypeError("scenarios 必须全部是 FaultScenario")
            if scenario.scenario_id in seen:
                raise ValueError(f"重复的故障场景编号: {scenario.scenario_id}")
            seen.add(scenario.scenario_id)

        active = [scenario for scenario in self.scenarios if scenario.enabled]
        for index, left in enumerate(active):
            for right in active[index + 1 :]:
                if left.conflicts_with(right):
                    raise ValueError(
                        "故障场景冲突："
                        f"{left.scenario_id} 与 {right.scenario_id} 会同时命中 "
                        f"{left.target.value}:{left.operation}；"
                        "请一次只选择一个重叠场景"
                    )

    # --- 运行时上下文 ---

    def set_context(self, run_id: str, case_id: str | None = None) -> None:
        self.run_id = run_id
        self.case_id = case_id

    def reset(self) -> None:
        """清空运行计数与事件（不会修改场景配置）。"""
        self.call_counts.clear()
        self.injected_counts.clear()
        self.events.clear()
        self.sink_errors.clear()

    # --- 匹配 ---

    def match(
        self,
        target: FaultTarget | str,
        operation: str,
        device: str | None = None,
    ) -> tuple[FaultScenario, int, int] | None:
        """查找本次调用应命中的场景。

        Returns
        -------
        tuple | None
            ``(scenario, call_number, injection_number)``；未命中返回 ``None``。
        """
        if not self.enabled:
            return None

        target_value = getattr(target, "value", target)
        for scenario in self.scenarios:
            if not scenario.matches(target_value, operation, device, self.case_id):
                continue

            sid = scenario.scenario_id
            calls = self.call_counts.get(sid, 0) + 1
            self.call_counts[sid] = calls

            injected = self.injected_counts.get(sid, 0)
            if calls < scenario.trigger_at:
                continue
            if injected >= scenario.occurrences:
                continue

            self.injected_counts[sid] = injected + 1
            return scenario, calls, injected + 1
        return None

    # --- 仪器钩子 ---

    def before_query(
        self, command: str, device: str | None = None
    ) -> str | None:
        """查询前调用；返回注入的响应文本或 ``None``，通信类故障直接抛出。"""
        match = self.match(FaultTarget.INSTRUMENT_QUERY, command, device)
        if match is None:
            return None
        scenario, calls, injection = match
        fault = scenario.fault_type

        if fault is FaultType.TIMEOUT:
            error = CommunicationTimeoutError(
                f"注入通信超时: {command}（设备 {device or '-'}）"
            )
            self._record(scenario, command, device, calls, injection, exception=error)
            raise error

        if fault is FaultType.DISCONNECT:
            error = DeviceDisconnectedError(
                f"注入仪器断开: {command}（设备 {device or '-'}）"
            )
            self._record(scenario, command, device, calls, injection, exception=error)
            raise error

        if fault is FaultType.INVALID_RESPONSE:
            self._record(
                scenario,
                command,
                device,
                calls,
                injection,
                injected_value=INVALID_RESPONSE_TEXT,
            )
            return INVALID_RESPONSE_TEXT

        raise ReliabilityError(
            f"{scenario.scenario_id}: 不支持查询故障 {fault.value}"
        )

    def before_write(self, command: str, device: str | None = None) -> None:
        """写入前调用；只支持超时/断开，写入默认不重试。"""
        match = self.match(FaultTarget.INSTRUMENT_WRITE, command, device)
        if match is None:
            return
        scenario, calls, injection = match
        fault = scenario.fault_type

        if fault is FaultType.TIMEOUT:
            error = CommunicationTimeoutError(
                f"注入写入超时: {command}（设备 {device or '-'}）"
            )
            self._record(scenario, command, device, calls, injection, exception=error)
            raise error
        if fault is FaultType.DISCONNECT:
            error = DeviceDisconnectedError(
                f"注入写入断开: {command}（设备 {device or '-'}）"
            )
            self._record(scenario, command, device, calls, injection, exception=error)
            raise error
        raise ReliabilityError(
            f"{scenario.scenario_id}: 不支持写入故障 {fault.value}"
        )

    def before_cleanup(self, operation: str, device: str | None = None) -> None:
        """清理前调用；``SHUTDOWN_FAILURE`` 只能在这里生效。"""
        match = self.match(FaultTarget.CLEANUP, operation, device)
        if match is None:
            return
        scenario, calls, injection = match
        fault = scenario.fault_type

        if fault is FaultType.SHUTDOWN_FAILURE:
            error = UnsafeShutdownError(
                f"注入关闭失败: {operation}（设备 {device or '-'}）"
            )
            self._record(scenario, operation, device, calls, injection, exception=error)
            raise error
        if fault is FaultType.TIMEOUT:
            error = CommunicationTimeoutError(
                f"注入清理超时: {operation}（设备 {device or '-'}）"
            )
            self._record(scenario, operation, device, calls, injection, exception=error)
            raise error
        if fault is FaultType.DISCONNECT:
            error = DeviceDisconnectedError(
                f"注入清理断开: {operation}（设备 {device or '-'}）"
            )
            self._record(scenario, operation, device, calls, injection, exception=error)
            raise error
        raise ReliabilityError(
            f"{scenario.scenario_id}: 不支持清理故障 {fault.value}"
        )

    # --- 测量数据 ---

    def transform_measurement(self, field: str, value: Any) -> Any:
        """对模型测量字段注入 NaN/Infinity/偏移；未命中时原样返回。"""
        match = self.match(FaultTarget.MODEL_MEASUREMENT, field)
        if match is None:
            return value

        if isinstance(value, bool):
            raise ReliabilityError(f"测量字段 {field} 是布尔值，无法注入故障")
        try:
            original = float(value)
        except (TypeError, ValueError):
            raise ReliabilityError(
                f"测量字段 {field} 不是数值，无法注入故障: {value!r}"
            ) from None

        scenario, calls, injection = match
        fault = scenario.fault_type

        if fault is FaultType.NAN_VALUE:
            injected = float("nan")
        elif fault is FaultType.INFINITY_VALUE:
            injected = float("inf")
        elif fault in (FaultType.VOLTAGE_OFFSET, FaultType.CURRENT_OFFSET):
            injected = original + scenario.offset
        else:
            raise ReliabilityError(
                f"{scenario.scenario_id}: 不支持测量故障 {fault.value}"
            )

        self._record(
            scenario,
            field,
            None,
            calls,
            injection,
            original_value=original,
            injected_value=injected,
        )
        return injected

    # --- 事件 ---

    def _record(
        self,
        scenario: FaultScenario,
        operation: str,
        device: str | None,
        call_number: int,
        injection_number: int,
        *,
        original_value: Any = None,
        injected_value: Any = None,
        exception: BaseException | None = None,
    ) -> None:
        event = new_event(
            EventType.FAULT_INJECTED,
            run_id=self.run_id,
            case_id=self.case_id,
            scenario_id=scenario.scenario_id,
            fault_type=scenario.fault_type.value,
            target=scenario.target.value,
            device_id=device,
            operation=operation,
            exception_type=type(exception).__name__ if exception is not None else None,
            message=str(exception) if exception is not None else None,
            original_value=original_value,
            injected_value=injected_value,
            details={
                "call_number": call_number,
                "injection_number": injection_number,
                "trigger_at": scenario.trigger_at,
                "occurrences": scenario.occurrences,
                "offset": scenario.offset,
                "scenario_name": scenario.name,
            },
        )
        self.events.append(event)
        if self.event_sink is None:
            return
        try:
            self.event_sink(event)
        except Exception as exc:  # 日志失败不得改变注入行为
            self.sink_errors.append(
                f"故障事件回调失败: {type(exc).__name__}: {exc}"
            )

    # --- 统计 ---

    @property
    def triggered(self) -> bool:
        return bool(self.injected_counts)

    @property
    def total_injected(self) -> int:
        return sum(self.injected_counts.values())

    def injected_scenario_ids(self) -> list[str]:
        return [
            scenario.scenario_id
            for scenario in self.scenarios
            if self.injected_counts.get(scenario.scenario_id, 0) > 0
        ]

    def fault_type_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for scenario in self.scenarios:
            count = self.injected_counts.get(scenario.scenario_id, 0)
            if count <= 0:
                continue
            key = scenario.fault_type.value
            counts[key] = counts.get(key, 0) + count
        return counts

    def to_dicts(self) -> list[dict[str, Any]]:
        return [dict(event) for event in self.events]


# ---------------------------------------------------------------------------
# 模型测量故障适配层
# ---------------------------------------------------------------------------


def _values_equal(left: float, right: float) -> bool:
    try:
        left_value = float(left)
        right_value = float(right)
    except (TypeError, ValueError):
        return left == right
    if math.isnan(left_value) or math.isnan(right_value):
        return False
    return left_value == right_value


def _consistent_view(result: Any, fields: dict[str, float]) -> Any | None:
    """按“效率保持”假设重算派生功率，得到自洽的测量视图。

    仅当输出侧（vout/iout）发生变化且原始效率有效时才能重算；否则返回
    ``None``，由调用方退化为“只改字段、保留原功率”的不一致视图。
    """
    state = getattr(result.state, "value", result.state)
    if state != "NORMAL":
        return None

    efficiency = getattr(result, "efficiency", None)
    if efficiency is None or not math.isfinite(float(efficiency)):
        return None
    efficiency = float(efficiency)
    if not 0 < efficiency <= 1:
        return None

    vin = float(fields["vin"])
    vout = float(fields["vout"])
    iout = float(fields["iout"])
    if vin <= 0 or vout < 0 or iout < 0:
        return None

    pout = vout * iout
    pin = pout / efficiency
    iin = pin / vin
    values = (vin, iin, vout, iout, pin, pout, pin - pout)
    if not all(math.isfinite(value) for value in values):
        return None

    return replace(
        result,
        vin=vin,
        iin=iin,
        vout=vout,
        iout=iout,
        pin=pin,
        pout=pout,
        power_loss=pin - pout,
        efficiency=efficiency,
        source=FAULT_INJECTED_SOURCE,
    )


def apply_measurement_faults(
    result: Any,
    fault_injector: FaultInjector | None,
    *,
    consistent: bool = True,
) -> Any:
    """返回注入测量故障后的独立视图，不修改原始 ``DUTResult``。

    - ``consistent=True``（默认）：输出侧偏移后按原始效率重算 pin/pout/
      iin/power_loss，得到“数据自洽但可能超限”的测量视图（用于验证
      性能限值判定）。
    - ``consistent=False``：只改测量字段，保留原始功率与效率字段，用于
      验证数据一致性检查会报 ERROR。
    - NaN/Infinity 无法参与自洽重算，始终走不一致视图，由数据质量模块
      识别，绝不替换为正常值。
    """
    if fault_injector is None or not getattr(fault_injector, "enabled", False):
        return result

    measurement_scenarios = [
        scenario
        for scenario in fault_injector.scenarios
        if scenario.enabled and scenario.target is FaultTarget.MODEL_MEASUREMENT
    ]
    if not measurement_scenarios:
        return result

    fields: dict[str, float] = {}
    changed = False
    non_finite = False
    for name in MEASUREMENT_FIELDS:
        original = getattr(result, name)
        modified = fault_injector.transform_measurement(name, original)
        fields[name] = modified
        if not _values_equal(original, modified):
            changed = True
        try:
            if not math.isfinite(float(modified)):
                non_finite = True
        except (TypeError, ValueError):
            non_finite = True

    if not changed:
        return result

    if not consistent or non_finite:
        return replace(result, **fields, source=FAULT_INJECTED_SOURCE)

    output_changed = not (
        _values_equal(fields["vout"], getattr(result, "vout"))
        and _values_equal(fields["iout"], getattr(result, "iout"))
    )
    if not output_changed:
        # 只改输入侧时无法在不篡改测量值的前提下保持功率自洽
        return replace(result, **fields, source=FAULT_INJECTED_SOURCE)

    view = _consistent_view(result, fields)
    if view is None:
        return replace(result, **fields, source=FAULT_INJECTED_SOURCE)
    return view
