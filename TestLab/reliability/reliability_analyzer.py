"""可靠性统计与实验判定。

统计口径（必须保持区分）
------------------------
- 故障场景数量 ≠ 注入次数 ≠ 重试次数；
- 恢复率分母是“符合重试条件的故障操作数”，按 ``operation_id`` 去重；
- 同一操作多次超时后最终成功，只算一次操作恢复成功；
- 可靠性实验通过率 ≠ 产品良率，也不代表真实设备 MTBF/MTTR；
- 业务测试的 ERROR/FAIL 不会被改写为 PASS，实验结论单独计算。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import yaml

from .fault_logger import EventType

__all__ = [
    "ExperimentExpectation",
    "ReliabilityAnalyzer",
    "evaluate_suite_experiment",
    "load_experiments",
    "validate_experiment_coverage",
]

VALID_STATUSES = frozenset({"PASS", "FAIL", "ERROR"})
VALID_CLEANUP_STATUSES = frozenset(
    {"VERIFIED_OFF", "NOT_VERIFIED", "NOT_APPLICABLE"}
)

_EXPERIMENT_FILE_KEYS = {"version", "simulation_only", "notes", "experiments"}
_EXPERIMENT_KEYS = {
    "scenario_id",
    "name",
    "expected_status",
    "expected_retry_count",
    "expected_recovered",
    "expected_retry_exhausted",
    "expected_cleanup_status",
    "expect_fault_injected",
    "expect_forced_stop",
}


@dataclass(frozen=True)
class ExperimentExpectation:
    """在运行前固定下来的可靠性实验预期。"""

    #: 阻止 pytest 把本类当作测试类收集
    __test__ = False

    scenario_id: str
    name: str
    expected_status: str
    expected_retry_count: int = 0
    expected_recovered: bool = False
    expected_retry_exhausted: bool = False
    expected_cleanup_status: str = "VERIFIED_OFF"
    expect_fault_injected: bool = False
    expect_forced_stop: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.scenario_id, str) or not self.scenario_id.strip():
            raise ValueError("scenario_id 必须是非空字符串")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError(f"{self.scenario_id}: name 必须是非空字符串")
        if self.expected_status not in VALID_STATUSES:
            raise ValueError(
                f"{self.scenario_id}: expected_status 非法 {self.expected_status!r}"
            )
        if (
            isinstance(self.expected_retry_count, bool)
            or not isinstance(self.expected_retry_count, int)
            or self.expected_retry_count < 0
        ):
            raise ValueError(
                f"{self.scenario_id}: expected_retry_count 必须是非负整数"
            )
        if self.expected_cleanup_status not in VALID_CLEANUP_STATUSES:
            raise ValueError(
                f"{self.scenario_id}: expected_cleanup_status 非法 "
                f"{self.expected_cleanup_status!r}"
            )
        for name in (
            "expected_recovered",
            "expected_retry_exhausted",
            "expect_fault_injected",
            "expect_forced_stop",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{self.scenario_id}: {name} 必须是布尔值")

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "name": self.name,
            "expected_status": self.expected_status,
            "expected_retry_count": self.expected_retry_count,
            "expected_recovered": self.expected_recovered,
            "expected_retry_exhausted": self.expected_retry_exhausted,
            "expected_cleanup_status": self.expected_cleanup_status,
            "expect_fault_injected": self.expect_fault_injected,
            "expect_forced_stop": self.expect_forced_stop,
        }


def load_experiments(path: str | Path) -> dict[str, ExperimentExpectation]:
    """读取并严格校验 ``configs/reliability_experiments.yaml``。"""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"可靠性实验预期配置不存在: {config_path}")

    with config_path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file)

    if not isinstance(raw, Mapping):
        raise ValueError("可靠性实验预期顶层必须是映射")
    unknown = set(raw) - _EXPERIMENT_FILE_KEYS
    if unknown:
        raise ValueError(f"可靠性实验预期含未知字段: {', '.join(sorted(unknown))}")

    if raw.get("simulation_only", False) is not True:
        raise ValueError("可靠性实验只允许在模拟环境使用（simulation_only: true）")

    entries = raw.get("experiments")
    if not isinstance(entries, list) or not entries:
        raise ValueError("experiments 必须是非空列表")

    experiments: dict[str, ExperimentExpectation] = {}
    for index, entry in enumerate(entries):
        label = f"experiments[{index}]"
        if not isinstance(entry, Mapping):
            raise ValueError(f"{label} 必须是映射")
        unknown_entry = set(entry) - _EXPERIMENT_KEYS
        if unknown_entry:
            raise ValueError(
                f"{label} 含未知字段: {', '.join(sorted(unknown_entry))}"
            )
        expectation = ExperimentExpectation(
            scenario_id=entry.get("scenario_id"),
            name=entry.get("name"),
            expected_status=entry.get("expected_status"),
            expected_retry_count=entry.get("expected_retry_count", 0),
            expected_recovered=entry.get("expected_recovered", False),
            expected_retry_exhausted=entry.get("expected_retry_exhausted", False),
            expected_cleanup_status=entry.get(
                "expected_cleanup_status", "VERIFIED_OFF"
            ),
            expect_fault_injected=entry.get("expect_fault_injected", False),
            expect_forced_stop=entry.get("expect_forced_stop", False),
        )
        if expectation.scenario_id in experiments:
            raise ValueError(f"重复的实验预期: {expectation.scenario_id}")
        experiments[expectation.scenario_id] = expectation
    return experiments


def validate_experiment_coverage(
    scenario_ids: Iterable[str],
    experiments: Mapping[str, ExperimentExpectation],
) -> None:
    """确保每个可执行场景都有预先固定的预期，防止“跑完再改预期”。"""
    missing = [sid for sid in scenario_ids if sid not in experiments]
    if missing:
        raise ValueError(
            "以下故障场景缺少实验预期: " + ", ".join(sorted(missing))
        )
    unknown = [
        sid
        for sid in experiments
        if sid not in set(scenario_ids) and sid != "NONE"
    ]
    if unknown:
        raise ValueError(
            "实验预期引用了不存在的场景: " + ", ".join(sorted(unknown))
        )


class ReliabilityAnalyzer:
    """从真实事件与业务结果计算可靠性统计。"""

    #: 阻止 pytest 把本类当作测试用例收集
    __test__ = False

    def summarize(
        self,
        events: Sequence[Mapping[str, Any]],
        scenario_results: Sequence[Mapping[str, Any]],
        *,
        expected_fault_types: Iterable[str] = (),
    ) -> dict[str, Any]:
        unique = self._unique_events(events)
        by_type: dict[str, list[dict[str, Any]]] = {}
        for event in unique:
            key = str(event.get("event_type") or "")
            by_type.setdefault(key, []).append(event)

        injected = by_type.get(EventType.FAULT_INJECTED.value, [])
        fault_type_counts = Counter(
            str(event.get("fault_type")) for event in injected if event.get("fault_type")
        )
        injected_scenarios = {
            str(event.get("scenario_id"))
            for event in injected
            if event.get("scenario_id")
        }

        attempts_failed = by_type.get(EventType.ATTEMPT_FAILED.value, [])
        retry_scheduled = by_type.get(EventType.RETRY_SCHEDULED.value, [])
        recovered = by_type.get(EventType.RECOVERED.value, [])
        exhausted = by_type.get(EventType.RETRY_EXHAUSTED.value, [])

        eligible_operations = {
            str(event.get("operation_id"))
            for event in attempts_failed
            if event.get("operation_id")
            and str(event.get("error_category")) == "TRANSIENT_COMMUNICATION"
            and bool((event.get("details") or {}).get("retry_safe", True))
        }
        recovered_operations = {
            str(event.get("operation_id"))
            for event in recovered
            if event.get("operation_id")
        }
        exhausted_operations = {
            str(event.get("operation_id"))
            for event in exhausted
            if event.get("operation_id")
        }

        retry_overhead_ms = 0.0
        for event in retry_scheduled:
            details = event.get("details") or {}
            delay = details.get("delay_seconds", 0.0)
            try:
                retry_overhead_ms += float(delay) * 1000.0
            except (TypeError, ValueError):
                continue

        executed_results = [
            result
            for result in scenario_results
            if str(result.get("status")) != "SKIP"
        ]
        cleanup_failure_count = sum(
            1
            for result in executed_results
            if result.get("cleanup_status") == "NOT_VERIFIED"
        )
        cleanup_failed_events = len(by_type.get(EventType.CLEANUP_FAILED.value, []))
        forced_stop_count = sum(
            1 for result in scenario_results if result.get("forced_stop")
        )
        aborted_events = len(by_type.get(EventType.TEST_ABORTED.value, []))

        passed_experiments = sum(
            1 for result in scenario_results if result.get("experiment_passed") is True
        )
        failed_experiments = sum(
            1 for result in scenario_results if result.get("experiment_passed") is False
        )

        eligible_count = len(eligible_operations)
        recovered_count = len(recovered_operations & eligible_operations)

        expected_types = [str(item) for item in expected_fault_types]
        coverage = [
            {
                "fault_type": fault_type,
                "triggered": fault_type_counts.get(fault_type, 0),
                "covered": fault_type_counts.get(fault_type, 0) > 0,
            }
            for fault_type in expected_types
        ]

        return {
            "data_mode": "SIMULATION",
            "scenario_count": len(scenario_results),
            "executed_scenario_count": len(executed_results),
            "fault_scenario_count": sum(
                1
                for result in scenario_results
                if result.get("scenario_id") not in (None, "NONE")
            ),
            "triggered_scenario_count": len(injected_scenarios),
            "total_fault_injections": len(injected),
            "injected_fault_type_counts": dict(sorted(fault_type_counts.items())),
            "injected_timeout_count": fault_type_counts.get("TIMEOUT", 0),
            "injected_disconnect_count": fault_type_counts.get("DISCONNECT", 0),
            "injected_invalid_data_count": (
                fault_type_counts.get("INVALID_RESPONSE", 0)
                + fault_type_counts.get("NAN_VALUE", 0)
                + fault_type_counts.get("INFINITY_VALUE", 0)
            ),
            "transient_failure_count": len(
                [
                    event
                    for event in attempts_failed
                    if str(event.get("error_category")) == "TRANSIENT_COMMUNICATION"
                ]
            ),
            "disconnect_failure_count": len(
                [
                    event
                    for event in attempts_failed
                    if str(event.get("error_category")) == "DEVICE_DISCONNECTED"
                ]
            ),
            "invalid_data_failure_count": len(
                [
                    event
                    for event in attempts_failed
                    if str(event.get("error_category")) == "INVALID_DATA"
                ]
            ),
            "attempt_count": len(attempts_failed) + len(recovered) + len(
                [event for event in exhausted if event.get("attempt_number") == 1]
            ),
            "retry_count": len(retry_scheduled),
            "retry_eligible_operations": eligible_count,
            "recovered_operations": recovered_count,
            "recovery_rate": (
                recovered_count / eligible_count * 100.0
                if eligible_count
                else None
            ),
            "retry_exhausted_count": len(exhausted_operations) or len(exhausted),
            "forced_stop_count": forced_stop_count or aborted_events,
            "cleanup_failure_count": cleanup_failure_count or cleanup_failed_events,
            "experiment_pass_count": passed_experiments,
            "experiment_fail_count": failed_experiments,
            "retry_overhead_ms": round(retry_overhead_ms, 3),
            "fault_detection_coverage": coverage,
            "notes": [
                "本统计来自 PyVISA-sim 模拟环境，不代表真实设备 MTBF/MTTR。",
                "恢复率分母是可重试的故障操作数，不是故障注入次数。",
                "业务测试状态与可靠性实验结论分开统计。",
            ],
        }

    @staticmethod
    def _unique_events(
        events: Sequence[Mapping[str, Any]]
    ) -> list[dict[str, Any]]:
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for event in events:
            payload = dict(event)
            event_id = str(payload.get("event_id") or "")
            if event_id:
                if event_id in seen:
                    continue
                seen.add(event_id)
            unique.append(payload)
        return unique


def evaluate_suite_experiment(
    results: Sequence[Any],
    expectation: ExperimentExpectation,
    *,
    stopped_early: bool | None = None,
) -> tuple[bool, list[str], dict[str, Any]]:
    """比较业务结果与预设实验预期。

    Returns
    -------
    (passed, reasons, actual)
        ``passed`` 只表示“系统行为符合预期”，不改变业务测试状态。
    """
    reasons: list[str] = []
    executed = [
        result
        for result in results
        if str(getattr(getattr(result, "status", None), "value", getattr(result, "status", None)))
        != "SKIP"
    ]
    if not executed:
        return False, ["没有任何实际执行的业务结果"], {}

    primary = executed[0]
    status = str(
        getattr(getattr(primary, "status", None), "value", getattr(primary, "status", None))
    )
    events = list(getattr(primary, "fault_events", None) or [])
    retry_exhausted = bool(getattr(primary, "retry_exhausted", False)) or any(
        str(event.get("event_type")) == EventType.RETRY_EXHAUSTED.value
        for event in events
    )
    actual = {
        "scenario_id": expectation.scenario_id,
        "case_id": getattr(primary, "case_id", None),
        "status": status,
        "retry_count": int(getattr(primary, "retry_count", 0) or 0),
        "recovered": bool(getattr(primary, "recovered", False)),
        "retry_exhausted": retry_exhausted,
        "cleanup_status": str(
            getattr(primary, "cleanup_status", "NOT_APPLICABLE")
        ),
        "fault_injected": bool(getattr(primary, "fault_injected", False)),
        "cleanup_failed": bool(getattr(primary, "cleanup_failed", False)),
        "executed_case_count": len(executed),
        "skipped_case_count": len(results) - len(executed),
    }

    if status != expectation.expected_status:
        reasons.append(
            f"业务状态 {status} != 预期 {expectation.expected_status}"
        )
    if actual["retry_count"] != expectation.expected_retry_count:
        reasons.append(
            f"重试次数 {actual['retry_count']} != 预期 "
            f"{expectation.expected_retry_count}"
        )
    if actual["recovered"] != expectation.expected_recovered:
        reasons.append(
            f"恢复状态 {actual['recovered']} != 预期 "
            f"{expectation.expected_recovered}"
        )
    if actual["retry_exhausted"] != expectation.expected_retry_exhausted:
        reasons.append(
            f"重试耗尽 {actual['retry_exhausted']} != 预期 "
            f"{expectation.expected_retry_exhausted}"
        )
    if actual["cleanup_status"] != expectation.expected_cleanup_status:
        reasons.append(
            f"清理状态 {actual['cleanup_status']} != 预期 "
            f"{expectation.expected_cleanup_status}"
        )
    if actual["fault_injected"] != expectation.expect_fault_injected:
        reasons.append(
            f"故障注入标记 {actual['fault_injected']} != 预期 "
            f"{expectation.expect_fault_injected}"
        )

    if expectation.expect_forced_stop:
        if stopped_early is None:
            stopped_early = any(
                str(
                    getattr(
                        getattr(result, "status", None),
                        "value",
                        getattr(result, "status", None),
                    )
                )
                == "SKIP"
                for result in results[1:]
            )
        observed_stop = bool(stopped_early)
        actual["forced_stop"] = observed_stop
        if not observed_stop:
            reasons.append("预期清理失败后强制停止后续任务，但未观察到停止")
    else:
        actual["forced_stop"] = bool(stopped_early)

    return not reasons, reasons, actual
