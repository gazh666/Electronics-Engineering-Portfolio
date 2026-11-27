"""TestLab 测试执行引擎包。

阶段七入口：:class:`engine.test_runner.TestRunner`（单用例）、
:class:`engine.suite_runner.SuiteRunner`（测试方案）。
旧版字典用例执行器仍以 :class:`ScenarioTestRunner` 保留。
"""

from .fault_injector import FaultInjector
from .models import (
    CheckResult,
    SuiteRunResult,
    SuiteRunStatus,
    TestCase,
    TestResult,
    TestStatus,
    TestSuite,
    summarize_results,
)
from .result_judge import (
    JudgeResult,
    aggregate_status,
    judge,
    judge_range,
    judge_state,
    judge_voltage,
)
from .test_runner import ScenarioTestRunner, TestRunner

__all__ = [
    "TestRunner",
    "ScenarioTestRunner",
    "TestCase",
    "TestSuite",
    "TestResult",
    "TestStatus",
    "CheckResult",
    "SuiteRunResult",
    "SuiteRunStatus",
    "summarize_results",
    "judge",
    "judge_voltage",
    "judge_state",
    "judge_range",
    "aggregate_status",
    "JudgeResult",
    "FaultInjector",
]
