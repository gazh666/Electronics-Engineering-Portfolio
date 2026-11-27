"""批量测试执行器：按测试方案顺序执行用例并实时持久化结果。

职责
----
- 生成全局唯一的 ``run_id``（一次运行只能有一个）；
- 逐条执行、逐条保存，进度回调在保存之后触发；
- 支持 ``stop_on_fail`` / ``stop_on_error``，以及“清理失败强制停止”；
- 未执行用例生成带原因的 SKIP 记录，而不是留空；
- 汇总统计来自真实结果，不使用硬编码。

本模块不依赖 Streamlit，也不直接访问仪器：仪器控制完全由
:class:`engine.test_runner.TestRunner` 完成，便于 CLI 与未来 Web 复用。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Sequence
from uuid import uuid4

from .models import (
    SuiteRunResult,
    SuiteRunStatus,
    TestCase,
    TestResult,
    TestStatus,
    TestSuite,
    summarize_results,
)

LOGGER = logging.getLogger("testlab.engine.suite_runner")

ProgressCallback = Callable[[int, int, TestResult], None]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class SuiteRunner:
    """串行执行一个测试方案，并写入 JSONL/CSV 与 SQLite 存储。"""

    #: 阻止 pytest 把本类当作测试用例收集
    __test__ = False

    def __init__(
        self,
        test_runner: Any,
        result_store: Any | None = None,
        sqlite_store: Any | None = None,
    ) -> None:
        self.test_runner = test_runner
        self.result_store = result_store
        self.sqlite_store = sqlite_store
        self.storage_errors: list[str] = []
        self.callback_errors: list[str] = []
        self._fault_logger: Any | None = None

    # --- 对外入口 ---

    def run_suite(
        self,
        suite: TestSuite,
        cases: Sequence[TestCase],
        progress_callback: ProgressCallback | None = None,
        run_id: str | None = None,
        *,
        fault_scenarios: Sequence[Any] | None = None,
        retry_policy: Any | None = None,
        fault_logger: Any | None = None,
    ) -> SuiteRunResult:
        """执行方案；返回整体结果（不抛出用例级异常）。

        ``fault_scenarios`` 非空时进入故障注入验证模式；配置通过执行器的
        ``configure_reliability`` 注入，不改变 ``run_case`` 的既有签名。
        """
        ordered = self._order_cases(suite, cases)
        run_id = run_id or uuid4().hex
        started_at = _now()

        self.storage_errors = []
        self.callback_errors = []
        self._fault_logger = fault_logger

        if fault_scenarios is not None:
            configure = getattr(self.test_runner, "configure_reliability", None)
            if configure is None:
                raise TypeError(
                    "当前执行器不支持故障注入（缺少 configure_reliability）"
                )
            configure(
                list(fault_scenarios),
                retry_policy=retry_policy,
                fault_logger=fault_logger,
            )

        self._start_stores(run_id, suite, len(ordered), ordered)

        results: list[TestResult] = []
        status = SuiteRunStatus.RUNNING
        stop_reason: str | None = None
        suite_error: str | None = None

        try:
            for index, case in enumerate(ordered):
                try:
                    result = self.test_runner.run_case(case, run_id, index)
                except KeyboardInterrupt:
                    status = SuiteRunStatus.ABORTED
                    stop_reason = "用户中断（KeyboardInterrupt）"
                    break
                except Exception as exc:  # 执行器自身异常，不能静默
                    LOGGER.exception("用例 %s 执行器异常", case.case_id)
                    result = self._error_result(case, run_id, index, exc)

                # 防御性保证：清理失败的结果不能被上层当作 PASS 统计或持久化
                if result.cleanup_failed:
                    result.status = TestStatus.ERROR

                self._persist(result)
                results.append(result)
                self._notify(progress_callback, index + 1, len(ordered), result)

                # 清理失败优先级最高：必须强制停止后续用例
                if result.cleanup_failed:
                    status = SuiteRunStatus.ERROR
                    stop_reason = f"{case.case_id} 清理失败，强制停止"
                    self._emit_abort(run_id, case.case_id, stop_reason, result)
                    break

                if result.status is TestStatus.FAIL and suite.stop_on_fail:
                    stop_reason = f"{case.case_id} 判定 FAIL，按方案停止"
                    break

                if result.status is TestStatus.ERROR and suite.stop_on_error:
                    stop_reason = f"{case.case_id} 判定 ERROR，按方案停止"
                    break

        except Exception as exc:  # 方案级异常（非用例级）
            LOGGER.exception("测试方案执行异常")
            status = SuiteRunStatus.ERROR
            suite_error = f"{type(exc).__name__}: {exc}"

        finally:
            # 未执行用例补 SKIP 记录，写明具体原因
            remaining = ordered[len(results) :]
            for offset, case in enumerate(remaining):
                skip = self._skip_result(
                    case,
                    run_id,
                    len(results) + offset,
                    stop_reason or "方案提前结束，未执行",
                )
                self._persist(skip)
                results.append(skip)

            if status is SuiteRunStatus.RUNNING:
                status = SuiteRunStatus.COMPLETED
            if self.storage_errors:
                status = SuiteRunStatus.ERROR

            summary = summarize_results(results, len(ordered))
            reliability_summary = self._build_reliability_summary(results)
            if reliability_summary is not None:
                summary["reliability"] = reliability_summary
            finished_at = _now()
            self._finish_stores(run_id, status, summary)

            if stop_reason:
                self._log(f"停止原因: {stop_reason}")

        return SuiteRunResult(
            run_id=run_id,
            suite_id=suite.suite_id,
            suite_name=suite.name,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            planned_count=len(ordered),
            results=results,
            summary=summary,
            stop_reason=stop_reason,
            suite_error=suite_error,
        )

    # --- 内部实现 ---

    def _emit_abort(
        self,
        run_id: str,
        case_id: str,
        reason: str,
        result: TestResult,
    ) -> None:
        """清理失败导致强制停止时记录 TEST_ABORTED（日志失败不得阻断停止）。"""
        if self._fault_logger is None:
            return
        try:
            from reliability.fault_logger import EventType, new_event

            event = new_event(
                EventType.TEST_ABORTED,
                run_id=run_id,
                case_id=case_id,
                message=reason,
                cleanup_status=result.cleanup_status,
                details={
                    "cleanup_errors": list(result.cleanup_errors),
                    "stop_reason": reason,
                },
            )
            emit = getattr(self._fault_logger, "emit", None)
            if callable(emit):
                emit(event)
        except Exception:
            # 事件日志失败不能阻止强制停止
            LOGGER.exception("记录 TEST_ABORTED 事件失败")

    @staticmethod
    def _build_reliability_summary(
        results: Sequence[TestResult],
    ) -> dict[str, Any] | None:
        """存在故障/重试/清理事件时，附带可靠性统计。"""
        has_reliability = any(
            result.fault_events
            or result.fault_injected
            or result.retry_count
            or result.cleanup_failed
            for result in results
        )
        if not has_reliability:
            return None
        from reliability.reliability_analyzer import ReliabilityAnalyzer

        events: list[dict[str, Any]] = []
        scenario_results: list[dict[str, Any]] = []
        for result in results:
            events.extend(result.fault_events)
            scenario_results.append(
                {
                    "scenario_id": (
                        result.fault_scenario_ids[0]
                        if result.fault_scenario_ids
                        else "NONE"
                    ),
                    "case_id": result.case_id,
                    "status": result.status.value,
                    "retry_count": result.retry_count,
                    "recovered": result.recovered,
                    "retry_exhausted": result.retry_exhausted,
                    "cleanup_status": result.cleanup_status,
                    "fault_injected": result.fault_injected,
                    "cleanup_failed": result.cleanup_failed,
                    "duration_ms": result.duration_ms,
                    "forced_stop": False,
                }
            )
        return ReliabilityAnalyzer().summarize(events, scenario_results)

    @staticmethod
    def _order_cases(
        suite: TestSuite, cases: Sequence[TestCase]
    ) -> list[TestCase]:
        """按方案声明顺序重排用例，并校验用例集合完整。"""
        available = {case.case_id: case for case in cases}
        missing = [case_id for case_id in suite.case_ids if case_id not in available]
        if missing:
            raise ValueError(
                f"测试方案 {suite.suite_id} 引用的用例未加载: {', '.join(missing)}"
            )
        return [available[case_id] for case_id in suite.case_ids]

    def _start_stores(
        self,
        run_id: str,
        suite: TestSuite,
        planned_count: int,
        cases: Sequence[TestCase],
    ) -> None:
        if self.result_store is not None:
            try:
                self.result_store.start_run(
                    run_id=run_id,
                    suite_id=suite.suite_id,
                    suite_name=suite.name,
                    planned_count=planned_count,
                    cases=cases,
                )
            except Exception as exc:
                self._storage_failure("结果目录初始化失败", exc)

        if self.sqlite_store is not None:
            try:
                self.sqlite_store.start_run(
                    run_id=run_id,
                    suite_id=suite.suite_id,
                    suite_name=suite.name,
                    planned_count=planned_count,
                )
            except Exception as exc:
                self._storage_failure("SQLite 运行记录写入失败", exc)

    def _persist(self, result: TestResult) -> None:
        """逐条持久化；任一存储失败都会记录，不影响另一存储。"""
        if self.result_store is not None:
            try:
                self.result_store.save_result(result)
            except Exception as exc:
                self._storage_failure(
                    f"JSONL/CSV 保存失败（{result.case_id}）", exc
                )

        if self.sqlite_store is not None:
            try:
                self.sqlite_store.save_result(result)
            except Exception as exc:
                self._storage_failure(
                    f"SQLite 保存失败（{result.case_id}）", exc
                )

    def _finish_stores(
        self, run_id: str, status: SuiteRunStatus, summary: dict[str, Any]
    ) -> None:
        if self.result_store is not None:
            try:
                self.result_store.finish_run(run_id, status, summary)
            except Exception as exc:
                self._storage_failure("汇总 JSON 写入失败", exc)

        if self.sqlite_store is not None:
            try:
                self.sqlite_store.finish_run(run_id, status.value, summary)
            except Exception as exc:
                self._storage_failure("SQLite 运行结束写入失败", exc)

    def _storage_failure(self, message: str, exc: Exception) -> None:
        detail = f"{message}: {type(exc).__name__}: {exc}"
        LOGGER.exception(detail)
        self.storage_errors.append(detail)
        self._log(detail)

    def _notify(
        self,
        callback: ProgressCallback | None,
        current: int,
        total: int,
        result: TestResult,
    ) -> None:
        if callback is None:
            return
        try:
            callback(current, total, result)
        except Exception as exc:
            # 回调失败只记录，不影响仪器清理与后续执行
            detail = (
                f"进度回调异常（{result.case_id}）: {type(exc).__name__}: {exc}"
            )
            LOGGER.exception(detail)
            self.callback_errors.append(detail)
            self._log(detail)

    def _log(self, message: str) -> None:
        if self.result_store is not None:
            try:
                self.result_store.log(message)
                return
            except Exception:  # 日志失败不能再引发二次异常
                LOGGER.exception("写入执行日志失败")
        LOGGER.info(message)

    @staticmethod
    def _error_result(
        case: TestCase, run_id: str, index: int, exc: Exception
    ) -> TestResult:
        now = _now()
        return TestResult(
            run_id=run_id,
            case_id=case.case_id,
            case_name=case.name,
            started_at=now,
            finished_at=now,
            duration_ms=0.0,
            status=TestStatus.ERROR,
            expected_state=case.expected_state,
            execution_index=index,
            error_message=f"执行器异常: {type(exc).__name__}: {exc}",
        )

    @staticmethod
    def _skip_result(
        case: TestCase, run_id: str, index: int, reason: str
    ) -> TestResult:
        now = _now()
        return TestResult(
            run_id=run_id,
            case_id=case.case_id,
            case_name=case.name,
            started_at=now,
            finished_at=now,
            duration_ms=0.0,
            status=TestStatus.SKIP,
            expected_state=case.expected_state,
            execution_index=index,
            error_message=f"未执行: {reason}",
        )


def exit_code_for_results(results: Sequence[TestResult]) -> int:
    """命令行退出码：0 全通过；1 存在 FAIL；2 存在 ERROR；3 无有效执行。"""
    statuses = {result.status for result in results}
    if TestStatus.ERROR in statuses:
        return 2
    if TestStatus.FAIL in statuses:
        return 1
    if TestStatus.PASS in statuses:
        return 0
    return 3
