"""有限重试策略与执行器（指数退避 + 明确白名单）。

核心边界
--------
- ``max_attempts`` 是**总尝试次数**（含第一次），最大 10，禁止无限重试；
- 只对“显式标记为可安全重试的只读查询 + 可恢复通信超时”重试；
- 写入、断开、非法数据、未知异常、清理失败一律不自动重试；
- ``KeyboardInterrupt`` 不是普通异常，不参与重试；
- 每次尝试都产生独立事件，累计等待时间可追溯。

真实仪器超时后通信缓冲区可能处于不确定状态。本策略只适用于当前
PyVISA-sim 模拟后端，不能宣称已满足实体仪器的通信恢复要求。
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

import yaml

from .error_classifier import ErrorCategory, classify_error
from .exceptions import RetryExhaustedError
from .fault_logger import EventType, new_event

__all__ = [
    "DEFAULT_ALLOWED_QUERIES",
    "RetryExecutor",
    "RetryPolicy",
    "load_retry_policy",
]

#: 允许自动重试的只读查询白名单
DEFAULT_ALLOWED_QUERIES = (
    "*IDN?",
    "VOLT?",
    "CURR?",
    "OUTP?",
    "INP?",
    "MODE?",
)

_RETRY_KEYS = {
    "enabled",
    "max_attempts",
    "initial_delay_seconds",
    "backoff_multiplier",
    "max_delay_seconds",
    "retryable_categories",
    "allowed_query_commands",
    "retry_writes",
    "retry_invalid_data",
    "retry_failed_test",
    "retry_shutdown_failure",
}
_TOP_LEVEL_KEYS = {"version", "retry", "notes"}

MAX_ATTEMPTS_LIMIT = 10
MAX_DELAY_LIMIT = 60.0


def _require_bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} 必须是布尔值 true/false，收到 {value!r}")
    return value


def _require_int(value: Any, label: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} 必须是整数，收到 {value!r}")
    if not minimum <= value <= maximum:
        raise ValueError(
            f"{label} 必须在 {minimum}-{maximum} 之间，收到 {value}"
        )
    return value


def _require_delay(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} 必须是数字，收到 {value!r}")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{label} 必须是有限非负数，收到 {value!r}")
    if number > MAX_DELAY_LIMIT:
        raise ValueError(f"{label} 不能超过 {MAX_DELAY_LIMIT:g} 秒")
    return number


@dataclass(frozen=True)
class RetryPolicy:
    """有限重试配置（不可变）。

    所有字段在构造时校验，非法配置直接抛出 ``ValueError``，避免进入
    执行阶段后才暴露。
    """

    #: 阻止 pytest 把本类当作测试用例收集
    __test__ = False

    enabled: bool = True
    max_attempts: int = 3
    initial_delay: float = 0.1
    multiplier: float = 2.0
    max_delay: float = 1.0
    retryable_categories: tuple[ErrorCategory, ...] = (
        ErrorCategory.TRANSIENT_COMMUNICATION,
    )
    allowed_query_commands: tuple[str, ...] = DEFAULT_ALLOWED_QUERIES
    retry_writes: bool = False
    retry_invalid_data: bool = False
    retry_failed_test: bool = False
    retry_shutdown_failure: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "enabled", _require_bool(self.enabled, "enabled"))
        object.__setattr__(
            self,
            "max_attempts",
            _require_int(self.max_attempts, "max_attempts", 1, MAX_ATTEMPTS_LIMIT),
        )
        initial = _require_delay(self.initial_delay, "initial_delay")
        max_delay = _require_delay(self.max_delay, "max_delay")
        if initial > max_delay:
            raise ValueError(
                f"initial_delay={initial:g} 不能大于 max_delay={max_delay:g}"
            )
        object.__setattr__(self, "initial_delay", initial)
        object.__setattr__(self, "max_delay", max_delay)

        multiplier = self.multiplier
        if isinstance(multiplier, bool) or not isinstance(multiplier, (int, float)):
            raise ValueError(f"multiplier 必须是数字，收到 {multiplier!r}")
        multiplier = float(multiplier)
        if not math.isfinite(multiplier) or multiplier < 1.0:
            raise ValueError(f"multiplier 必须是 >=1 的有限数，收到 {multiplier!r}")
        object.__setattr__(self, "multiplier", multiplier)

        categories: list[ErrorCategory] = []
        for item in self.retryable_categories:
            if isinstance(item, ErrorCategory):
                category = item
            else:
                try:
                    category = ErrorCategory(str(item))
                except ValueError:
                    raise ValueError(f"未知异常类别: {item!r}") from None
            if category not in categories:
                categories.append(category)
        if not categories:
            raise ValueError("retryable_categories 不能为空")
        object.__setattr__(self, "retryable_categories", tuple(categories))

        commands: list[str] = []
        for item in self.allowed_query_commands:
            if not isinstance(item, str) or not item.strip():
                raise ValueError(f"allowed_query_commands 含非法命令: {item!r}")
            normalized = item.strip().upper()
            if normalized not in commands:
                commands.append(normalized)
        if not commands:
            raise ValueError("allowed_query_commands 不能为空")
        object.__setattr__(self, "allowed_query_commands", tuple(commands))

        for name in (
            "retry_writes",
            "retry_invalid_data",
            "retry_failed_test",
            "retry_shutdown_failure",
        ):
            object.__setattr__(self, name, _require_bool(getattr(self, name), name))

    # --- 便捷查询 ---

    def is_allowed_query(self, operation_name: str) -> bool:
        return str(operation_name).strip().upper() in self.allowed_query_commands

    def backoff_delay(self, retry_number: int) -> float:
        """第 ``retry_number`` 次重试前的等待时间（1 表示第一次重试）。"""
        if retry_number < 1:
            raise ValueError("retry_number 必须 >= 1")
        delay = self.initial_delay * (self.multiplier ** (retry_number - 1))
        return min(delay, self.max_delay)

    # --- YAML ---

    @classmethod
    def from_yaml(cls, path: str | Path) -> "RetryPolicy":
        """从 ``configs/retry_policy.yaml`` 加载并校验。"""
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"重试策略配置不存在: {config_path}")
        with config_path.open("r", encoding="utf-8") as file:
            raw = yaml.safe_load(file)
        if not isinstance(raw, Mapping):
            raise ValueError("重试策略配置顶层必须是映射")
        unknown = set(raw) - _TOP_LEVEL_KEYS
        if unknown:
            raise ValueError(f"重试策略配置含未知字段: {', '.join(sorted(unknown))}")
        retry = raw.get("retry")
        if not isinstance(retry, Mapping):
            raise ValueError("重试策略配置缺少 retry 段")
        unknown_retry = set(retry) - _RETRY_KEYS
        if unknown_retry:
            raise ValueError(
                f"retry 段含未知字段: {', '.join(sorted(unknown_retry))}"
            )
        return cls(
            enabled=retry.get("enabled", True),
            max_attempts=retry.get("max_attempts", 3),
            initial_delay=retry.get("initial_delay_seconds", 0.1),
            multiplier=retry.get("backoff_multiplier", 2.0),
            max_delay=retry.get("max_delay_seconds", 1.0),
            retryable_categories=tuple(retry.get("retryable_categories", ())),
            allowed_query_commands=tuple(
                retry.get("allowed_query_commands", DEFAULT_ALLOWED_QUERIES)
            ),
            retry_writes=retry.get("retry_writes", False),
            retry_invalid_data=retry.get("retry_invalid_data", False),
            retry_failed_test=retry.get("retry_failed_test", False),
            retry_shutdown_failure=retry.get("retry_shutdown_failure", False),
        )


def load_retry_policy(path: str | Path) -> RetryPolicy:
    """模块级便捷函数。"""
    return RetryPolicy.from_yaml(path)


class RetryExecutor:
    """在有限次数内执行一个操作，并记录每次尝试与恢复结果。"""

    #: 阻止 pytest 把本类当作测试用例收集
    __test__ = False

    def __init__(
        self,
        policy: RetryPolicy | None = None,
        *,
        sleeper: Callable[[float], None] = time.sleep,
        event_callback: Callable[[dict[str, Any]], Any] | None = None,
        run_id: str = "",
        case_id: str | None = None,
        operation_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.policy = policy or RetryPolicy()
        self.sleeper = sleeper
        self.event_callback = event_callback
        self.run_id = run_id
        self.case_id = case_id
        self._operation_id_factory = operation_id_factory

        self.events: list[dict[str, Any]] = []
        self.callback_errors: list[str] = []
        self.operations = 0
        self.attempts = 0
        self.retries = 0
        self.recovered_operations = 0
        self.exhausted_operations = 0
        self.cumulative_wait_seconds = 0.0
        self.last_error: BaseException | None = None
        self.last_operation_id: str | None = None
        self.operation_records: dict[str, dict[str, Any]] = {}

    # --- 上下文 ---

    def set_context(self, run_id: str, case_id: str | None = None) -> None:
        self.run_id = run_id
        self.case_id = case_id

    def reset(self) -> None:
        self.events.clear()
        self.callback_errors.clear()
        self.operations = 0
        self.attempts = 0
        self.retries = 0
        self.recovered_operations = 0
        self.exhausted_operations = 0
        self.cumulative_wait_seconds = 0.0
        self.last_error = None
        self.last_operation_id = None
        self.operation_records.clear()

    @property
    def retry_count(self) -> int:
        """实际安排的重试次数（不包含第一次尝试）。"""
        return self.retries

    @property
    def recovered(self) -> bool:
        return self.recovered_operations > 0

    # --- 执行 ---

    def execute(
        self,
        operation: Callable[[], Any],
        operation_name: str,
        retry_safe: bool = False,
    ) -> Any:
        """执行操作；仅在允许的异常与操作上重试。

        Parameters
        ----------
        operation
            无参可调用对象。
        operation_name
            操作名称（通常为 SCPI 命令），用于白名单匹配与事件记录。
        retry_safe
            调用方是否确认该操作可以安全重复执行。写入与非幂等操作必须
            传 ``False``。
        """
        policy = self.policy
        operation_id = self._new_operation_id()
        self.last_operation_id = operation_id
        self.operations += 1
        record = {
            "operation_id": operation_id,
            "operation": operation_name,
            "retry_safe": bool(retry_safe),
            "attempts": 0,
            "retries": 0,
            "recovered": False,
            "exhausted": False,
        }
        self.operation_records[operation_id] = record

        max_attempts = policy.max_attempts if policy.enabled else 1

        for attempt in range(1, max_attempts + 1):
            try:
                value = operation()
            except Exception as exc:  # 业务异常：分类后再决定是否重试
                self.attempts += 1
                self.last_error = exc
                record["attempts"] = attempt
                category = classify_error(exc)
                self._emit(
                    EventType.ATTEMPT_FAILED,
                    operation_id=operation_id,
                    operation=operation_name,
                    attempt_number=attempt,
                    retry_number=attempt - 1,
                    error_category=category.value,
                    exception_type=type(exc).__name__,
                    message=str(exc),
                    details={
                        "retry_safe": bool(retry_safe),
                        "retry_enabled": policy.enabled,
                        "max_attempts": policy.max_attempts,
                    },
                )

                if not self._should_retry(exc, category, operation_name, retry_safe):
                    raise

                if attempt >= max_attempts:
                    self.exhausted_operations += 1
                    record["exhausted"] = True
                    error = RetryExhaustedError(
                        f"{operation_name} 在 {attempt} 次尝试后仍失败（{category.value}）",
                        category=category,
                    )
                    self.last_error = error
                    self._emit(
                        EventType.RETRY_EXHAUSTED,
                        operation_id=operation_id,
                        operation=operation_name,
                        attempt_number=attempt,
                        retry_number=attempt - 1,
                        error_category=category.value,
                        exception_type="RetryExhaustedError",
                        message=str(error),
                        details={"max_attempts": policy.max_attempts},
                    )
                    raise error from exc

                delay = policy.backoff_delay(attempt)
                self.retries += 1
                record["retries"] = attempt
                self.cumulative_wait_seconds += delay
                self._emit(
                    EventType.RETRY_SCHEDULED,
                    operation_id=operation_id,
                    operation=operation_name,
                    attempt_number=attempt,
                    retry_number=attempt,
                    error_category=category.value,
                    exception_type=type(exc).__name__,
                    message=str(exc),
                    details={"delay_seconds": delay, "next_attempt": attempt + 1},
                )
                if delay > 0:
                    self.sleeper(delay)
            else:
                self.attempts += 1
                record["attempts"] = attempt
                if attempt > 1:
                    self.recovered_operations += 1
                    record["recovered"] = True
                    self._emit(
                        EventType.RECOVERED,
                        operation_id=operation_id,
                        operation=operation_name,
                        attempt_number=attempt,
                        retry_number=attempt - 1,
                        details={"max_attempts": policy.max_attempts},
                    )
                return value

        raise RuntimeError("重试循环异常结束，属于程序缺陷")  # pragma: no cover

    # --- 内部实现 ---

    def _new_operation_id(self) -> str:
        if self._operation_id_factory is not None:
            return self._operation_id_factory()
        import uuid

        return uuid.uuid4().hex

    def _should_retry(
        self,
        exc: BaseException,
        category: ErrorCategory,
        operation_name: str,
        retry_safe: bool,
    ) -> bool:
        policy = self.policy
        if not policy.enabled:
            return False
        if not retry_safe:
            # 写入或非幂等操作：无论异常类别如何都不自动重试
            return False
        if not policy.is_allowed_query(operation_name):
            return False
        if category not in policy.retryable_categories:
            return False
        if category is ErrorCategory.INVALID_DATA and not policy.retry_invalid_data:
            return False
        if category is ErrorCategory.SHUTDOWN_ERROR and not policy.retry_shutdown_failure:
            return False
        # 防御：断开与未知异常即使误配进类别也拒绝
        if category is ErrorCategory.DEVICE_DISCONNECTED:
            return False
        if category is ErrorCategory.UNKNOWN_ERROR:
            return False
        if category is ErrorCategory.CONFIGURATION_ERROR:
            return False
        return True

    def _emit(self, event_type: EventType | str, **fields: Any) -> None:
        event = new_event(
            event_type,
            run_id=self.run_id,
            case_id=self.case_id,
            **fields,
        )
        self.events.append(event)
        if self.event_callback is None:
            return
        try:
            self.event_callback(event)
        except Exception as exc:  # 回调失败不能掩盖原始异常
            message = f"重试事件回调失败: {type(exc).__name__}: {exc}"
            self.callback_errors.append(message)
