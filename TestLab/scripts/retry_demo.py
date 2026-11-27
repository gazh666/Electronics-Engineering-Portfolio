"""有限重试演示（阶段八）。

五个场景全部真实调用 :class:`RetryExecutor`：

1. 正常查询，第一次成功；
2. 单次超时后重试成功（验证恢复）；
3. 持续超时，有限次后 ``RetryExhaustedError``；
4. 非法数据：不重试；
5. 写入超时：不重试。

退出码：0 全部符合预期；1 有场景不符合预期；2 运行错误。

本演示只覆盖 PyVISA-sim 模拟环境，不代表真实仪器超时后的通信恢复能力。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from instruments.exceptions import InstrumentResponseError  # noqa: E402
from reliability.exceptions import RetryExhaustedError  # noqa: E402
from reliability.fault_injector import FaultInjector  # noqa: E402
from reliability.fault_models import FaultScenario, FaultTarget, FaultType  # noqa: E402
from reliability.retry_policy import RetryExecutor, RetryPolicy  # noqa: E402

RETRY_CONFIG = PROJECT_ROOT / "configs" / "retry_policy.yaml"


def _scenario(
    scenario_id: str,
    fault_type: FaultType,
    target: FaultTarget,
    operation: str,
    occurrences: int,
) -> FaultScenario:
    return FaultScenario(
        scenario_id=scenario_id,
        name=scenario_id,
        fault_type=fault_type,
        target=target,
        operation=operation,
        occurrences=occurrences,
        device="PS001",
    )


def _print_events(executor: RetryExecutor) -> None:
    for event in executor.events:
        details = event.get("details") or {}
        extra = ""
        if event.get("event_type") == "RETRY_SCHEDULED":
            extra = f" delay={details.get('delay_seconds')}s"
        print(
            f"    {event.get('event_type'):<16} attempt={event.get('attempt_number')} "
            f"category={event.get('error_category') or '-'}{extra}"
        )


def _check(name: str, actual, expected, checks: list[tuple[str, bool, str]]) -> None:
    ok = actual == expected
    checks.append((name, ok, f"{name}: 实际={actual!r} 预期={expected!r}"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TestLab 有限重试演示")
    parser.add_argument(
        "--no-sleep",
        action="store_true",
        help="使用零延迟便于快速演示（默认使用配置中的真实退避等待）",
    )
    args = parser.parse_args(argv)

    policy = RetryPolicy.from_yaml(RETRY_CONFIG)
    if args.no_sleep:
        policy = RetryPolicy(
            enabled=policy.enabled,
            max_attempts=policy.max_attempts,
            initial_delay=0.0,
            multiplier=policy.multiplier,
            max_delay=0.0,
            retryable_categories=policy.retryable_categories,
            allowed_query_commands=policy.allowed_query_commands,
        )

    checks: list[tuple[str, bool, str]] = []
    print(f"重试策略: max_attempts={policy.max_attempts}, "
          f"initial={policy.initial_delay}s, multiplier={policy.multiplier}, "
          f"max_delay={policy.max_delay}s, 白名单={list(policy.allowed_query_commands)}")

    # 场景 1：正常查询
    executor = RetryExecutor(policy)
    value = executor.execute(lambda: 12.0, "VOLT?", retry_safe=True)
    print("\n[1] 正常查询")
    print(f"  返回值: {value}  重试次数: {executor.retries}  恢复: {executor.recovered}")
    _print_events(executor)
    _check("场景1 返回值", value, 12.0, checks)
    _check("场景1 重试次数", executor.retries, 0, checks)

    # 场景 2：单次超时后成功
    injector = FaultInjector(
        [_scenario("R001", FaultType.TIMEOUT, FaultTarget.INSTRUMENT_QUERY, "VOLT?", 1)],
        enabled=True,
        run_id="retry_demo",
        case_id="RETRY",
    )
    executor = RetryExecutor(policy, run_id="retry_demo", case_id="RETRY")

    def query_with_timeout() -> float:
        injected = injector.before_query("VOLT?", device="PS001")
        raw = injected if injected is not None else "12.0"
        return float(raw)

    value = executor.execute(query_with_timeout, "VOLT?", retry_safe=True)
    print("\n[2] 单次超时后重试成功")
    print(f"  返回值: {value}  重试次数: {executor.retries}  恢复: {executor.recovered}")
    _print_events(executor)
    _check("场景2 返回值", value, 12.0, checks)
    _check("场景2 重试次数", executor.retries, 1, checks)
    _check("场景2 恢复", executor.recovered, True, checks)

    # 场景 3：持续超时，有限次后耗尽
    injector = FaultInjector(
        [_scenario("R002", FaultType.TIMEOUT, FaultTarget.INSTRUMENT_QUERY, "VOLT?", 5)],
        enabled=True,
        run_id="retry_demo",
        case_id="RETRY",
    )
    executor = RetryExecutor(policy, run_id="retry_demo", case_id="RETRY")
    raised = None
    try:
        executor.execute(query_with_timeout, "VOLT?", retry_safe=True)
    except RetryExhaustedError as exc:
        raised = exc
    print("\n[3] 持续超时，有限重试后耗尽")
    print(
        f"  异常: {type(raised).__name__ if raised else '未抛出'}  "
        f"重试次数: {executor.retries}  耗尽: {executor.exhausted_operations}"
    )
    _print_events(executor)
    _check("场景3 抛出 RetryExhaustedError", raised is not None, True, checks)
    _check("场景3 重试次数", executor.retries, policy.max_attempts - 1, checks)
    _check("场景3 耗尽次数", executor.exhausted_operations, 1, checks)

    # 场景 4：非法数据不重试
    injector = FaultInjector(
        [
            _scenario(
                "R003",
                FaultType.INVALID_RESPONSE,
                FaultTarget.INSTRUMENT_QUERY,
                "VOLT?",
                1,
            )
        ],
        enabled=True,
        run_id="retry_demo",
        case_id="RETRY",
    )
    executor = RetryExecutor(policy, run_id="retry_demo", case_id="RETRY")

    def query_invalid() -> float:
        injected = injector.before_query("VOLT?", device="PS001")
        raw = injected if injected is not None else "12.0"
        try:
            return float(raw)
        except ValueError:
            raise InstrumentResponseError(
                f"psu: 响应不是数字 {raw!r}"
            ) from None

    raised = None
    try:
        executor.execute(query_invalid, "VOLT?", retry_safe=True)
    except InstrumentResponseError as exc:
        raised = exc
    print("\n[4] 非法数据不重试")
    print(
        f"  异常: {type(raised).__name__ if raised else '未抛出'}  "
        f"尝试次数: {executor.attempts}  重试次数: {executor.retries}"
    )
    _print_events(executor)
    _check("场景4 抛出 InstrumentResponseError", raised is not None, True, checks)
    _check("场景4 重试次数", executor.retries, 0, checks)

    # 场景 5：写入超时不重试
    injector = FaultInjector(
        [
            _scenario(
                "R004",
                FaultType.TIMEOUT,
                FaultTarget.INSTRUMENT_WRITE,
                "OUTP 1",
                1,
            )
        ],
        enabled=True,
        run_id="retry_demo",
        case_id="RETRY",
    )
    executor = RetryExecutor(policy, run_id="retry_demo", case_id="RETRY")

    def write_output() -> None:
        injector.before_write("OUTP 1", device="PS001")

    raised = None
    try:
        executor.execute(write_output, "OUTP 1", retry_safe=False)
    except Exception as exc:
        raised = exc
    print("\n[5] 写入超时不重试")
    print(
        f"  异常: {type(raised).__name__ if raised else '未抛出'}  "
        f"尝试次数: {executor.attempts}  重试次数: {executor.retries}"
    )
    _print_events(executor)
    _check("场景5 抛出异常", raised is not None, True, checks)
    _check("场景5 重试次数", executor.retries, 0, checks)

    failures = [message for _, ok, message in checks if not ok]
    print("\n结果汇总")
    for name, ok, message in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {message}")
    if failures:
        print(f"\n{len(failures)} 项不符合预期", file=sys.stderr)
        return 1
    print("\n全部场景符合预期（仅模拟环境）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
