"""阶段八：故障注入、通信异常处理、有限重试与可靠性验证。

本包只服务于**模拟环境**的可控故障实验，不代表真实硬件可靠性认证。
默认关闭：只有调用方显式传入故障场景时才会启用注入。
"""

from __future__ import annotations

from .error_classifier import ErrorCategory, classify_error
from .exceptions import (
    CommunicationTimeoutError,
    DeviceDisconnectedError,
    InjectedFaultError,
    InvalidResponseError,
    ReliabilityError,
    RetryExhaustedError,
    UnsafeShutdownError,
)
from .fault_injector import (
    FAULT_INJECTED_SOURCE,
    FaultInjector,
    apply_measurement_faults,
)
from .fault_logger import EventType, FaultLogger, new_event
from .fault_models import (
    FaultScenario,
    FaultScenarioLibrary,
    FaultTarget,
    FaultType,
    load_fault_scenarios,
)
from .reliability_analyzer import (
    ExperimentExpectation,
    ReliabilityAnalyzer,
    evaluate_suite_experiment,
    load_experiments,
)
from .retry_policy import RetryExecutor, RetryPolicy

__all__ = [
    "CommunicationTimeoutError",
    "DeviceDisconnectedError",
    "ErrorCategory",
    "EventType",
    "ExperimentExpectation",
    "FAULT_INJECTED_SOURCE",
    "FaultInjector",
    "FaultLogger",
    "FaultScenario",
    "FaultScenarioLibrary",
    "FaultTarget",
    "FaultType",
    "InjectedFaultError",
    "InvalidResponseError",
    "ReliabilityAnalyzer",
    "ReliabilityError",
    "RetryExhaustedError",
    "RetryExecutor",
    "RetryPolicy",
    "UnsafeShutdownError",
    "apply_measurement_faults",
    "classify_error",
    "evaluate_suite_experiment",
    "load_experiments",
    "load_fault_scenarios",
    "new_event",
]
