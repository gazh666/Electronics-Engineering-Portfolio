"""有限重试策略与执行器单元测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from reliability.error_classifier import ErrorCategory
from reliability.exceptions import (
    CommunicationTimeoutError,
    DeviceDisconnectedError,
    RetryExhaustedError,
    UnsafeShutdownError,
)
from reliability.fault_logger import EventType
from reliability.retry_policy import RetryExecutor, RetryPolicy

ROOT = Path(__file__).resolve().parents[1]


def _policy(**overrides):
    data = {
        "max_attempts": 3,
        "initial_delay": 0.0,
        "multiplier": 2.0,
        "max_delay": 0.0,
    }
    data.update(overrides)
    return RetryPolicy(**data)


def _events(executor):
    return [event["event_type"] for event in executor.events]


def test_default_policy_is_bounded():
    policy = RetryPolicy()
    assert policy.max_attempts == 3
    assert policy.max_attempts <= 10
    assert policy.retry_writes is False


def test_policy_rejects_invalid_max_attempts():
    for value in (0, 11, True, 2.5):
        with pytest.raises(ValueError):
            _policy(max_attempts=value)


def test_policy_rejects_initial_delay_above_max_delay():
    with pytest.raises(ValueError):
        RetryPolicy(initial_delay=2.0, max_delay=1.0)


def test_policy_rejects_multiplier_below_one():
    with pytest.raises(ValueError):
        RetryPolicy(multiplier=0.5)


def test_policy_rejects_unknown_category():
    with pytest.raises(ValueError):
        RetryPolicy(retryable_categories=("SOMETHING",))


def test_policy_rejects_empty_whitelist():
    with pytest.raises(ValueError):
        RetryPolicy(allowed_query_commands=())


def test_backoff_is_capped():
    policy = RetryPolicy(
        initial_delay=0.5, multiplier=3.0, max_delay=1.0
    )
    assert policy.backoff_delay(1) == pytest.approx(0.5)
    assert policy.backoff_delay(2) == pytest.approx(1.0)
    assert policy.backoff_delay(3) == pytest.approx(1.0)


def test_retry_policy_yaml_loads():
    policy = RetryPolicy.from_yaml(ROOT / "configs" / "retry_policy.yaml")
    assert policy.max_attempts == 3
    assert "VOLT?" in policy.allowed_query_commands
    assert policy.retryable_categories == (ErrorCategory.TRANSIENT_COMMUNICATION,)


def test_executor_success_without_retry():
    executor = RetryExecutor(_policy())
    assert executor.execute(lambda: 12.0, "VOLT?", retry_safe=True) == 12.0
    assert executor.retries == 0
    assert executor.recovered is False
    assert executor.events == []


def test_executor_recovers_after_single_timeout():
    sleeps = []
    executor = RetryExecutor(_policy(initial_delay=0.1, max_delay=0.5), sleeper=sleeps.append)
    calls = {"count": 0}

    def operation():
        calls["count"] += 1
        if calls["count"] == 1:
            raise CommunicationTimeoutError("timeout")
        return 12.0

    assert executor.execute(operation, "VOLT?", retry_safe=True) == 12.0
    assert executor.retries == 1
    assert executor.recovered is True
    assert executor.recovered_operations == 1
    assert sleeps == [pytest.approx(0.1)]
    assert _events(executor) == [
        EventType.ATTEMPT_FAILED.value,
        EventType.RETRY_SCHEDULED.value,
        EventType.RECOVERED.value,
    ]


def test_executor_exhausts_after_max_attempts():
    sleeps = []
    executor = RetryExecutor(_policy(max_attempts=3, initial_delay=0.1, max_delay=1.0), sleeper=sleeps.append)

    def operation():
        raise CommunicationTimeoutError("timeout")

    with pytest.raises(RetryExhaustedError) as excinfo:
        executor.execute(operation, "VOLT?", retry_safe=True)

    assert isinstance(excinfo.value.__cause__, CommunicationTimeoutError)
    assert excinfo.value.category is ErrorCategory.TRANSIENT_COMMUNICATION
    assert executor.retries == 2
    assert executor.exhausted_operations == 1
    assert executor.attempts == 3
    assert sleeps == [pytest.approx(0.1), pytest.approx(0.2)]
    assert _events(executor).count(EventType.RETRY_EXHAUSTED.value) == 1


def test_executor_does_not_retry_invalid_data():
    from instruments.exceptions import InstrumentResponseError

    executor = RetryExecutor(_policy())
    calls = {"count": 0}

    def operation():
        calls["count"] += 1
        raise InstrumentResponseError("bad data")

    with pytest.raises(InstrumentResponseError):
        executor.execute(operation, "VOLT?", retry_safe=True)
    assert calls["count"] == 1
    assert executor.retries == 0
    assert executor.events[0]["error_category"] == "INVALID_DATA"


def test_executor_does_not_retry_disconnect():
    executor = RetryExecutor(_policy())
    calls = {"count": 0}

    def operation():
        calls["count"] += 1
        raise DeviceDisconnectedError("lost")

    with pytest.raises(DeviceDisconnectedError):
        executor.execute(operation, "VOLT?", retry_safe=True)
    assert calls["count"] == 1
    assert executor.retries == 0


def test_executor_does_not_retry_unknown():
    executor = RetryExecutor(_policy())
    with pytest.raises(RuntimeError):
        executor.execute(lambda: (_ for _ in ()).throw(RuntimeError("boom")), "VOLT?", retry_safe=True)
    assert executor.retries == 0


def test_executor_does_not_retry_shutdown_failure():
    executor = RetryExecutor(_policy())
    with pytest.raises(UnsafeShutdownError):
        executor.execute(lambda: (_ for _ in ()).throw(UnsafeShutdownError("off")), "OUTP 0", retry_safe=True)
    assert executor.retries == 0


def test_executor_does_not_retry_writes():
    executor = RetryExecutor(_policy())
    calls = {"count": 0}

    def operation():
        calls["count"] += 1
        raise CommunicationTimeoutError("timeout")

    with pytest.raises(CommunicationTimeoutError):
        executor.execute(operation, "OUTP 1", retry_safe=False)
    assert calls["count"] == 1
    assert executor.retries == 0


def test_executor_does_not_retry_non_whitelisted_query():
    executor = RetryExecutor(_policy())
    with pytest.raises(CommunicationTimeoutError):
        executor.execute(
            lambda: (_ for _ in ()).throw(CommunicationTimeoutError("timeout")),
            "SYST:ERR?",
            retry_safe=True,
        )
    assert executor.retries == 0


def test_disabled_policy_single_attempt():
    executor = RetryExecutor(_policy(enabled=False))
    calls = {"count": 0}

    def operation():
        calls["count"] += 1
        raise CommunicationTimeoutError("timeout")

    with pytest.raises(CommunicationTimeoutError):
        executor.execute(operation, "VOLT?", retry_safe=True)
    assert calls["count"] == 1
    assert executor.retries == 0
    assert executor.events[0]["event_type"] == EventType.ATTEMPT_FAILED.value


def test_max_attempts_one_exhausts_without_retry():
    executor = RetryExecutor(_policy(max_attempts=1))
    with pytest.raises(RetryExhaustedError):
        executor.execute(
            lambda: (_ for _ in ()).throw(CommunicationTimeoutError("timeout")),
            "VOLT?",
            retry_safe=True,
        )
    assert executor.retries == 0
    assert executor.exhausted_operations == 1


def test_callback_error_does_not_mask_original_exception():
    def broken_callback(event):
        raise RuntimeError("callback broken")

    executor = RetryExecutor(_policy(max_attempts=2), event_callback=broken_callback)
    with pytest.raises(RetryExhaustedError):
        executor.execute(
            lambda: (_ for _ in ()).throw(CommunicationTimeoutError("timeout")),
            "VOLT?",
            retry_safe=True,
        )
    assert executor.callback_errors
    assert "callback broken" in executor.callback_errors[0]


def test_keyboard_interrupt_is_not_retried():
    executor = RetryExecutor(_policy())
    calls = {"count": 0}

    def operation():
        calls["count"] += 1
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        executor.execute(operation, "VOLT?", retry_safe=True)
    assert calls["count"] == 1
    assert executor.retries == 0


def test_executor_reset_clears_counters():
    executor = RetryExecutor(_policy())
    executor.execute(lambda: 1.0, "VOLT?", retry_safe=True)
    executor.reset()
    assert executor.events == []
    assert executor.operations == 0
    assert executor.retries == 0
    assert executor.operation_records == {}
