"""自动化测试引擎的公共数据结构。

设计原则
--------
- 测试用例（``TestCase``）、单项检查（``CheckResult``）、用例结果
  （``TestResult``）严格分离，避免“配置”和“实测结果”混在一起。
- 状态统一使用枚举，禁止散落的字符串常量。
- 所有结构都提供 ``to_dict``，可直接写入 JSONL / SQLite。
- 未执行的用例只记录 SKIP 与原因，不填充虚构测量值。

数据来源
--------
本阶段全部结果来自 PyVISA-sim 虚拟仪器与 ``VirtualDUT`` 行为模型，
属于仿真验证，不代表真实硬件认证测试。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence


class TestStatus(str, Enum):
    """单个测试用例的最终状态。"""

    #: 阻止 pytest 把本枚举当作测试类收集
    __test__ = False

    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"
    SKIP = "SKIP"

    def __str__(self) -> str:
        return self.value


class SuiteRunStatus(str, Enum):
    """测试方案（批量任务）的生命周期状态。

    ``COMPLETED`` 只表示流程正常执行结束，不代表全部用例通过。
    """

    #: 阻止 pytest 把本枚举当作测试类收集
    __test__ = False

    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"
    ERROR = "ERROR"

    def __str__(self) -> str:
        return self.value


class CleanupStatus(str, Enum):
    """清理结果：只承诺“是否得到确认”，不推断硬件实际状态。"""

    #: 阻止 pytest 把本枚举当作测试类收集
    __test__ = False

    VERIFIED_OFF = "VERIFIED_OFF"
    NOT_VERIFIED = "NOT_VERIFIED"
    NOT_APPLICABLE = "NOT_APPLICABLE"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class TestCase:
    """一条由 YAML 加载并校验后的测试用例。

    ``limits`` 的键只能是 :mod:`engine.case_loader` 中登记的指标名，
    由加载器负责校验，执行层不再猜测字段含义。
    """

    #: 阻止 pytest 把本类当作测试用例收集
    __test__ = False

    case_id: str
    name: str
    category: str
    vin: float
    input_current_limit: float
    load_current: float
    expected_state: str
    output_enabled: bool = True
    load_enabled: bool = True
    enabled: bool = True
    limits: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.case_id,
            "name": self.name,
            "category": self.category,
            "vin": self.vin,
            "input_current_limit": self.input_current_limit,
            "load_current": self.load_current,
            "expected_state": self.expected_state,
            "output_enabled": self.output_enabled,
            "load_enabled": self.load_enabled,
            "enabled": self.enabled,
            "limits": dict(self.limits),
        }


@dataclass(frozen=True)
class TestSuite:
    """一组按顺序执行的测试用例。"""

    #: 阻止 pytest 把本类当作测试类收集
    __test__ = False

    suite_id: str
    name: str
    case_ids: tuple[str, ...]
    stop_on_fail: bool = False
    stop_on_error: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.suite_id,
            "name": self.name,
            "cases": list(self.case_ids),
            "stop_on_fail": self.stop_on_fail,
            "stop_on_error": self.stop_on_error,
        }


@dataclass(frozen=True)
class CheckResult:
    """一个可判定指标的检查记录。"""

    #: 阻止 pytest 把本类当作测试类收集
    __test__ = False

    name: str
    actual: Any
    expected: Any
    status: TestStatus
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "actual": self.actual,
            "expected": self.expected,
            "status": getattr(self.status, "value", self.status),
            "message": self.message,
        }


@dataclass
class TestResult:
    """单条用例的完整执行记录。

    ``raw_data`` 保留模型原始输出，``metrics`` 保留派生指标，
    两者不互相覆盖；``quality_issues`` 记录数据质量问题。
    """

    #: 阻止 pytest 把本类当作测试类收集
    __test__ = False

    run_id: str
    case_id: str
    case_name: str
    started_at: str
    finished_at: str
    duration_ms: float
    status: TestStatus
    expected_state: str
    actual_state: str | None = None
    raw_data: dict[str, Any] | None = None
    metrics: dict[str, Any] | None = None
    checks: list[CheckResult] = field(default_factory=list)
    error_message: str | None = None
    data_source: str | None = None
    execution_index: int = 0
    quality_issues: list[dict[str, Any]] = field(default_factory=list)
    cleanup_failed: bool = False
    # --- 阶段八：可靠性字段（默认值保证旧记录兼容） ---
    fault_injected: bool = False
    fault_scenario_ids: list[str] = field(default_factory=list)
    fault_events: list[dict[str, Any]] = field(default_factory=list)
    retry_count: int = 0
    retry_exhausted: bool = False
    recovered: bool = False
    error_category: str | None = None
    cleanup_status: str = CleanupStatus.NOT_APPLICABLE.value
    cleanup_errors: list[str] = field(default_factory=list)
    original_model_data: dict[str, Any] | None = None
    observed_data: dict[str, Any] | None = None
    original_data_source: str | None = None
    observed_data_source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """转换为可 JSON 序列化的字典（枚举转字符串）。"""
        return {
            "run_id": self.run_id,
            "execution_index": self.execution_index,
            "case_id": self.case_id,
            "case_name": self.case_name,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "status": getattr(self.status, "value", self.status),
            "expected_state": self.expected_state,
            "actual_state": self.actual_state,
            "raw_data": self.raw_data,
            "metrics": self.metrics,
            "checks": [check.to_dict() for check in self.checks],
            "error_message": self.error_message,
            "data_source": self.data_source,
            "quality_issues": self.quality_issues,
            "cleanup_failed": self.cleanup_failed,
            "fault_injected": self.fault_injected,
            "fault_scenario_ids": list(self.fault_scenario_ids),
            "fault_events": list(self.fault_events),
            "retry_count": self.retry_count,
            "retry_exhausted": self.retry_exhausted,
            "recovered": self.recovered,
            "error_category": self.error_category,
            "cleanup_status": getattr(self.cleanup_status, "value", self.cleanup_status),
            "cleanup_errors": list(self.cleanup_errors),
            "original_model_data": self.original_model_data,
            "observed_data": self.observed_data,
            "original_data_source": self.original_data_source,
            "observed_data_source": self.observed_data_source,
        }

    @property
    def passed(self) -> bool:
        return self.status is TestStatus.PASS


@dataclass
class SuiteRunResult:
    """一次批量执行的整体结果。"""

    #: 阻止 pytest 把本类当作测试类收集
    __test__ = False

    run_id: str
    suite_id: str
    suite_name: str
    status: SuiteRunStatus
    started_at: str
    finished_at: str
    planned_count: int
    results: list[TestResult] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    stop_reason: str | None = None
    suite_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "suite_id": self.suite_id,
            "suite_name": self.suite_name,
            "status": self.status.value,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "planned_count": self.planned_count,
            "summary": self.summary,
            "stop_reason": self.stop_reason,
            "suite_error": self.suite_error,
            "results": [result.to_dict() for result in self.results],
        }


def summarize_results(
    results: Sequence[TestResult], planned_count: int
) -> dict[str, Any]:
    """从真实结果统计用例数量与两种不同口径的比率。

    - ``pass_rate``：有效判定通过率 = PASS / (PASS + FAIL)；
    - ``completion_rate``：执行完成率 = (PASS + FAIL + ERROR) / 计划数；
    - ``planned_pass_rate``：计划用例通过比例 = PASS / 计划数。

    三种口径名称不同，避免用通过率掩盖大量 ERROR 或未执行用例。
    """
    counts = {"PASS": 0, "FAIL": 0, "ERROR": 0, "SKIP": 0}
    for result in results:
        counts[result.status.value] += 1

    passed = counts["PASS"]
    failed = counts["FAIL"]
    errors = counts["ERROR"]
    skipped = counts["SKIP"]
    executed = passed + failed + errors
    valid = passed + failed

    return {
        "total_cases": planned_count,
        "executed_cases": executed,
        "pass_count": passed,
        "fail_count": failed,
        "error_count": errors,
        "skip_count": skipped,
        "pass_rate": passed / valid * 100.0 if valid else None,
        "completion_rate": executed / planned_count * 100.0 if planned_count else None,
        "planned_pass_rate": passed / planned_count * 100.0 if planned_count else None,
        "total_duration_ms": sum(result.duration_ms for result in results),
    }
