"""自动化测试执行引擎：读取 YAML 用例，驱动虚拟仪器与 DUT 行为模型。

数据来源约定
------------
- 输入电压、负载电流设定值来自虚拟仪器 SCPI 回读（``pyvisa-sim SCPI``）；
- 输出电压、电流、功率、保护状态来自 ``VirtualDUT`` 行为模型
  （``behavioral_model``）；
- DMM 读数 = 模型真值 + ADC 噪声（``model(virtual_dut)+dmm_noise``）。

判定使用模型输出的**确定性数值**（不受 ADC 噪声影响），因此保护状态的
``voltage_min = voltage_max = 0`` 可以稳定判定为 PASS。
"""

from __future__ import annotations

import inspect
import math
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence, TypeVar

import yaml

from analysis.metrics import (
    efficiency_anomaly,
    efficiency_percent,
    input_power,
    mean as mean_of,
    missing_fields,
    output_power,
    voltage_absolute_error,
    voltage_error_percent,
)
from instruments.electronic_load import ElectronicLoad
from instruments.multimeter import DMM_SOURCE, VirtualMultimeter
from instruments.power_supply import PowerSupply
from instruments.base import InstrumentError, InstrumentTimeoutError
from models.virtual_dut import MODEL_SOURCE, VirtualDUT
from reliability.error_classifier import ErrorCategory, classify_error
from reliability.fault_injector import (
    FaultInjector as ReliabilityFaultInjector,
    apply_measurement_faults,
)
from reliability.fault_logger import EventType, new_event
from reliability.fault_models import FaultScenario
from reliability.retry_policy import RetryExecutor, RetryPolicy

from .dut_bridge import BridgeReading, DutDataBridge
from .fault_injector import (
    LOCATION_BRIDGE,
    LOCATION_DMM_CURRENT,
    LOCATION_DMM_VOLTAGE,
    FaultInjector,
    FaultSpec,
)
from .models import CleanupStatus, TestCase, TestResult, TestStatus
from .result_judge import (
    aggregate_status,
    judge_range,
    judge_state,
    judge_voltage,
)

T = TypeVar("T")

#: 模型支持的保护/工作状态
KNOWN_STATES = frozenset(
    {
        "NORMAL",
        "OUTPUT_OFF",
        "UNDERVOLTAGE",
        "OVERVOLTAGE",
        "OVERCURRENT",
        "INPUT_CURRENT_LIMIT",
    }
)

#: 每条测试记录必须包含的字段
REQUIRED_RECORD_FIELDS = (
    "run_id",
    "case_id",
    "case_name",
    "timestamp",
    "vin",
    "iin",
    "vout",
    "iout",
    "pin",
    "pout",
    "efficiency",
    "expected_state",
    "actual_state",
    "status",
    "duration_ms",
    "error_message",
    "data_source",
)


class ScenarioTestRunner:
    """旧版“字典用例”执行器（阶段四~六使用，保留以兼容既有测试与 demo）。

    新代码请使用本模块底部的 :class:`TestRunner`（阶段七自动化执行引擎）。
    """

    #: 阻止 pytest 把本类当作测试用例收集
    __test__ = False

    #: 测量层与模型值的一致性阈值，超出视为测量偏移/数据异常
    MEASUREMENT_VOLTAGE_TOLERANCE_V = 0.05
    MEASUREMENT_CURRENT_TOLERANCE_A = 0.05

    def __init__(
        self,
        psu: PowerSupply,
        dmm: VirtualMultimeter,
        load: ElectronicLoad,
        dut: VirtualDUT,
        settle_time: float = 0.05,
        sample_count: int = 5,
        max_retries: int = 2,
        fault_specs: Sequence[FaultSpec] = (),
        run_id: str | None = None,
    ) -> None:
        self.psu = psu
        self.dmm = dmm
        self.load = load
        self.dut = dut
        self.nominal_voltage = dut.nominal_voltage
        self.settle_time = settle_time
        self.sample_count = sample_count
        self.max_retries = max_retries
        self.fault_specs = list(fault_specs)
        self.bridge = DutDataBridge(psu, load, dut)
        self._fixed_run_id = run_id
        self.run_id = run_id or ""

    # --- 对外入口 ---

    def run_file(self, path: str | Path) -> list[dict[str, Any]]:
        """从 YAML 文件读取 ``test_cases`` 并执行。"""
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError("用例文件顶层必须是映射")

        defaults = data.get("defaults", {}) or {}
        self.settle_time = float(defaults.get("settle_time_s", self.settle_time))
        self.sample_count = int(defaults.get("sample_count", self.sample_count))
        self.max_retries = int(defaults.get("max_retries", self.max_retries))

        cases = data.get("test_cases")
        if cases is None:
            raise ValueError("用例文件缺少 test_cases")
        if not isinstance(cases, list):
            raise ValueError("test_cases 必须是列表")
        return self.run_cases(cases)

    def run_cases(self, cases: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        """顺序执行用例；单个用例异常不会中断后续用例。"""
        self.run_id = self._fixed_run_id or datetime.now().strftime(
            "run_%Y%m%d_%H%M%S_%f"
        )
        records: list[dict[str, Any]] = []
        try:
            for case in cases:
                records.append(self._run_case(case))
        finally:
            self._safe_shutdown()
        return records

    # --- 单个用例 ---

    def _run_case(self, case: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        if not isinstance(case, dict):
            case = {}
        record = self._new_record(case)
        injector = FaultInjector()

        try:
            params = self._validate_case(case)
            if not params["enabled"]:
                record["status"] = "SKIP"
                record["error_message"] = "用例未启用（enabled: false）"
            else:
                injector = FaultInjector(
                    specs=[*self.fault_specs, *self._case_fault_specs(case)]
                )
                self.bridge.fault_injector = injector
                self._setup(params)
                reading = self._acquire(params, injector)
                self._fill_measurement(record, params, reading, injector)
                self._judge(record, params, reading)
        except Exception as exc:  # 测试框架必须记录异常而不是崩溃
            record["status"] = "ERROR"
            record["error_message"] = f"{type(exc).__name__}: {exc}"
        finally:
            self.bridge.fault_injector = None
            record["duration_ms"] = round((time.perf_counter() - started) * 1000.0, 2)
            self._safe_shutdown()
            self._detect_missing(record)
            injector.finalize(record["status"])
            record["faults"] = injector.to_dicts()
            record["retries"] = injector.total_retries

        return record

    def _new_record(self, case: dict[str, Any]) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "case_id": str(case.get("id", "")),
            "case_name": str(case.get("name", "")),
            "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
            "vin": None,
            "iin": None,
            "vout": None,
            "iout": None,
            "pin": None,
            "pout": None,
            "efficiency": None,
            "expected_state": case.get("expected_state"),
            "actual_state": None,
            "status": "ERROR",
            "duration_ms": 0.0,
            "error_message": None,
            "data_source": MODEL_SOURCE,
            "data_sources": {},
            "voltage_absolute_error_v": None,
            "voltage_error_percent": None,
            "vout_measured": None,
            "iout_measured": None,
            "dmm_samples": [],
            "data_anomalies": [],
            "missing_fields": [],
            "checks": [],
            "faults": [],
            "retries": 0,
        }

    def _validate_case(self, case: dict[str, Any]) -> dict[str, Any]:
        """校验用例参数；不合法直接抛出 ValueError。"""
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError("用例缺少有效 id")

        name = case.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{case_id}: 用例缺少有效 name")

        vin = self._number(case.get("vin"), f"{case_id}.vin", 0.0, 30.0)
        load_current = self._number(
            case.get("load_current"), f"{case_id}.load_current", 0.0, 5.0
        )
        lower = self._number(case.get("voltage_min"), f"{case_id}.voltage_min", 0.0, 30.0)
        upper = self._number(case.get("voltage_max"), f"{case_id}.voltage_max", 0.0, 30.0)
        if lower > upper:
            raise ValueError(
                f"{case_id}: voltage_min={lower:g} 不能大于 voltage_max={upper:g}"
            )

        expected_state = case.get("expected_state")
        if expected_state not in KNOWN_STATES:
            raise ValueError(f"{case_id}: 未知 expected_state {expected_state!r}")

        enabled = case.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError(f"{case_id}: enabled 必须是 bool")

        output_enabled = case.get("output_enabled", True)
        if not isinstance(output_enabled, bool):
            raise ValueError(f"{case_id}: output_enabled 必须是 bool")

        load_enabled = case.get("load_enabled", load_current > 0.0)
        if not isinstance(load_enabled, bool):
            raise ValueError(f"{case_id}: load_enabled 必须是 bool")

        max_retries = case.get("max_retries", self.max_retries)
        if not isinstance(max_retries, int) or isinstance(max_retries, bool):
            raise ValueError(f"{case_id}: max_retries 必须是整数")
        if not 0 <= max_retries <= 10:
            raise ValueError(f"{case_id}: max_retries 必须在 0-10 之间")

        current_limit = case.get("current_limit", max(1.0, load_current + 0.5))
        current_limit = self._number(
            current_limit, f"{case_id}.current_limit", 0.0, 5.0
        )

        return {
            "case_id": case_id,
            "name": name,
            "vin": vin,
            "load_current": load_current,
            "current_limit": current_limit,
            "load_enabled": load_enabled,
            "output_enabled": output_enabled,
            "expected_state": expected_state,
            "voltage_min": lower,
            "voltage_max": upper,
            "max_retries": max_retries,
            "enabled": enabled,
        }

    @staticmethod
    def _number(value: Any, label: str, low: float, high: float) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{label} 必须是数字，收到 {value!r}") from None
        if not math.isfinite(number):
            raise ValueError(f"{label} 必须是有限数值，收到 {value!r}")
        if not low <= number <= high:
            raise ValueError(f"{label} 超出范围 {low:g}-{high:g}，收到 {number:g}")
        return number

    def _case_fault_specs(self, case: dict[str, Any]) -> list[FaultSpec]:
        fault = case.get("fault")
        if fault is None:
            return []
        if not isinstance(fault, dict):
            raise ValueError("fault 必须是映射")

        return [
            FaultSpec(
                fault_type=fault.get("type"),
                location=fault.get("location", LOCATION_BRIDGE),
                times=int(fault.get("times", 1)),
                value=float(fault.get("value", 0.0)),
            )
        ]

    # --- 仪器编排 ---

    def _setup(self, params: dict[str, Any]) -> None:
        self._safe_shutdown()
        self.psu.set_voltage(params["vin"])
        self.psu.set_current(params["current_limit"])
        self.psu.set_output(True)
        self.load.set_mode("CC")
        self.load.set_current(params["load_current"])
        self.load.set_input(params["load_enabled"])
        time.sleep(self.settle_time)

    def _safe_shutdown(self) -> None:
        """关闭负载与电源输出，确保异常退出后不残留输出。"""
        try:
            self.load.set_input(False)
        except Exception:
            pass
        try:
            self.psu.set_output(False)
        except Exception:
            pass

    def _acquire(
        self, params: dict[str, Any], injector: FaultInjector
    ) -> BridgeReading:
        """通过数据连接层读取设定值并计算模型结果（支持有限重试）。"""

        def operation() -> BridgeReading:
            injector.apply(LOCATION_BRIDGE)
            return self.bridge.acquire(enabled=params["output_enabled"])

        return self._with_retry(operation, injector, params["max_retries"])

    @staticmethod
    def _with_retry(
        operation: Callable[[], T], injector: FaultInjector, max_retries: int
    ) -> T:
        """对通信类异常做有限次数重试；其他异常立即抛出。"""
        attempts = 0
        while True:
            try:
                return operation()
            except (InstrumentTimeoutError, InstrumentError):
                if attempts >= max_retries:
                    raise
                attempts += 1
                injector.mark_retry()

    def _fill_measurement(
        self,
        record: dict[str, Any],
        params: dict[str, Any],
        reading: BridgeReading,
        injector: FaultInjector,
    ) -> None:
        """把模型输出、工程指标与 DMM 测量值写入记录。"""
        dut = reading.dut
        samples = self._measure_voltage(dut.vout, injector, params["max_retries"])
        vout_measured = mean_of(samples)
        iout_measured = self._measure_current(
            dut.iout, injector, params["max_retries"]
        )

        vin = reading.vin_setpoint
        if not math.isfinite(vin):
            raise ValueError("输入电压读数无效")

        pin = input_power(vin, dut.iin)
        pout = output_power(dut.vout, dut.iout)
        efficiency = efficiency_percent(vin, dut.iin, dut.vout, dut.iout)
        abs_error = voltage_absolute_error(dut.vout, self.nominal_voltage)
        rel_error = voltage_error_percent(dut.vout, self.nominal_voltage)

        anomalies: list[str] = []
        if not math.isfinite(vout_measured):
            anomalies.append("DMM 输出电压读数非有限")
        elif (
            abs(vout_measured - dut.vout)
            > self.MEASUREMENT_VOLTAGE_TOLERANCE_V
        ):
            anomalies.append(
                f"输出电压测量值 {vout_measured:.6g} V 与模型值 "
                f"{dut.vout:.6g} V 偏差超过 "
                f"{self.MEASUREMENT_VOLTAGE_TOLERANCE_V:g} V"
            )
        if not math.isfinite(iout_measured):
            anomalies.append("DMM 输出电流读数非有限")
        elif (
            abs(iout_measured - dut.iout)
            > self.MEASUREMENT_CURRENT_TOLERANCE_A
        ):
            anomalies.append(
                f"输出电流测量值 {iout_measured:.6g} A 与模型值 "
                f"{dut.iout:.6g} A 偏差超过 "
                f"{self.MEASUREMENT_CURRENT_TOLERANCE_A:g} A"
            )
        anomaly = efficiency_anomaly(efficiency)
        if anomaly is not None:
            anomalies.append(anomaly)

        state_status = (
            "PASS" if dut.state == params["expected_state"] else "FAIL"
        )
        voltage_status = judge_voltage(
            dut.vout, params["voltage_min"], params["voltage_max"]
        )

        record.update(
            {
                "vin": round(vin, 6),
                "iin": round(dut.iin, 6),
                "vout": round(dut.vout, 6),
                "iout": round(dut.iout, 6),
                "pin": round(pin, 6),
                "pout": round(pout, 6),
                "efficiency": None if efficiency is None else round(efficiency, 6),
                "actual_state": dut.state,
                "data_source": dut.source,
                "data_sources": {
                    **reading.sources,
                    "measurement": DMM_SOURCE,
                },
                "voltage_absolute_error_v": round(abs_error, 6),
                "voltage_error_percent": round(rel_error, 6),
                "vout_measured": (
                    round(vout_measured, 6)
                    if math.isfinite(vout_measured)
                    else None
                ),
                "iout_measured": (
                    round(iout_measured, 6)
                    if math.isfinite(iout_measured)
                    else None
                ),
                "dmm_samples": [
                    round(sample, 6) if math.isfinite(sample) else None
                    for sample in samples
                ],
                "data_anomalies": anomalies,
                "state_status": state_status,
                "voltage_status": voltage_status,
                "checks": [
                    {
                        "name": "保护状态",
                        "value": dut.state,
                        "unit": "",
                        "min": None,
                        "max": None,
                        "status": state_status,
                        "passed": state_status == "PASS",
                        "detail": (
                            f"预期 {params['expected_state']}，实际 {dut.state}"
                        ),
                        "source": MODEL_SOURCE,
                    },
                    {
                        "name": "输出电压",
                        "value": round(dut.vout, 6),
                        "unit": "V",
                        "min": params["voltage_min"],
                        "max": params["voltage_max"],
                        "status": voltage_status,
                        "passed": voltage_status == "PASS",
                        "detail": (
                            f"模型输出电压 {dut.vout:.6g} V，"
                            f"限值 {params['voltage_min']:g}-{params['voltage_max']:g} V"
                        ),
                        "source": MODEL_SOURCE,
                    },
                ],
            }
        )

    def _measure_voltage(
        self, true_value: float, injector: FaultInjector, max_retries: int
    ) -> list[float]:
        """把模型输出电压真值送入 DMM 噪声模型，并允许故障注入。"""
        samples: list[float] = []
        for _ in range(self.sample_count):

            def operation() -> float:
                return injector.apply(  # type: ignore[return-value]
                    LOCATION_DMM_VOLTAGE, self.dmm.read_dc_voltage(true_value)
                )

            samples.append(self._with_retry(operation, injector, max_retries))
        return samples

    def _measure_current(
        self, true_value: float, injector: FaultInjector, max_retries: int
    ) -> float:
        """把模型输出电流送入测量层，并允许偏移/NaN 故障注入。"""

        def operation() -> float:
            return injector.apply(  # type: ignore[return-value]
                LOCATION_DMM_CURRENT, float(true_value)
            )

        return self._with_retry(operation, injector, max_retries)

    def _judge(
        self,
        record: dict[str, Any],
        params: dict[str, Any],
        reading: BridgeReading,
    ) -> None:
        """汇总状态对比、电压限值与数据异常，给出最终状态。"""
        state_status = record["state_status"]
        voltage_status = record["voltage_status"]
        dut = reading.dut

        if voltage_status == "ERROR":
            status = "ERROR"
            message = "输出电压判定错误：限值非法或读数非有限"
        elif state_status == "FAIL":
            status = "FAIL"
            message = (
                f"预期状态 {params['expected_state']}，"
                f"实际状态 {dut.state}"
            )
        elif voltage_status == "FAIL":
            status = "FAIL"
            message = (
                f"输出电压 {dut.vout:.6g} V 超出 "
                f"{params['voltage_min']:g}-{params['voltage_max']:g} V"
            )
        else:
            status = "PASS"
            message = None

        anomalies = record.get("data_anomalies") or []
        if anomalies:
            status = "ERROR"
            message = "数据异常：" + "；".join(anomalies)

        record["status"] = status
        record["error_message"] = message

    def _detect_missing(self, record: dict[str, Any]) -> None:
        """检测记录缺失数据；缺失时把非 SKIP 记录标记为 ERROR。"""
        if record["status"] == "SKIP":
            record["missing_fields"] = []
            return

        allow_none = ["error_message"]
        # 空载/保护状态没有输出电流时，效率无定义，不视为数据缺失
        if not (
            record["actual_state"] == "NORMAL"
            and float(record["iout"] or 0.0) > 0.0
        ):
            allow_none.append("efficiency")

        missing = missing_fields(
            record, REQUIRED_RECORD_FIELDS, allow_none=allow_none
        )
        record["missing_fields"] = missing

        if missing:
            suffix = "数据缺失: " + ", ".join(missing)
            record["error_message"] = (
                suffix
                if not record["error_message"]
                else f"{record['error_message']}；{suffix}"
            )
            if record["status"] != "ERROR":
                record["status"] = "ERROR"


# ---------------------------------------------------------------------------
# 阶段七：自动化测试执行引擎（TestCase / TestResult 结构化接口）
# ---------------------------------------------------------------------------


class SetpointMismatchError(RuntimeError):
    """下发参数与仪器回读不一致。"""


class TestRunner:
    """单用例自动化执行器：设置工况 -> 读取模型 -> 数据质量 -> 判定 -> 清理。

    与阶段四~六的 :class:`ScenarioTestRunner` 相比，本类：

    - 接收结构化 :class:`TestCase`，输出 :class:`TestResult`；
    - 校验“下发设定值”与“仪器回读值”一致，不一致直接判 ERROR；
    - 数据质量 ERROR 优先于状态/限值判定；
    - 清理失败会把结果标为 ERROR 并置 ``cleanup_failed``，供上层强制停止；
    - 未启用用例直接 SKIP，**不访问任何仪器**。

    本类只支持串行执行，不声明线程安全。
    """

    #: 阻止 pytest 把本类当作测试用例收集
    __test__ = False

    def __init__(
        self,
        manager: Any,
        bench: Any,
        analyzer: Any,
        *,
        setpoint_tolerance: float = 1e-6,
        fault_scenarios: Sequence[FaultScenario] | None = None,
        retry_policy: RetryPolicy | None = None,
        fault_logger: Any | None = None,
    ) -> None:
        self.manager = manager
        self.bench = bench
        self.analyzer = analyzer
        self.setpoint_tolerance = setpoint_tolerance
        # 故障注入默认关闭：只有显式传入场景才会创建注入器
        self._fault_scenarios: list[FaultScenario] = list(fault_scenarios or [])
        self.retry_policy = retry_policy
        self.fault_logger = fault_logger
        self.logger_errors: list[str] = []

    # --- 可靠性配置 ---

    def configure_reliability(
        self,
        scenarios: Sequence[FaultScenario],
        *,
        retry_policy: RetryPolicy | None = None,
        fault_logger: Any | None = None,
    ) -> None:
        """显式启用故障注入与有限重试。

        未调用本方法（或传入空场景且不传策略）时，执行路径与阶段七完全
        一致：不创建注入器、不附加重试执行器。
        """
        self._fault_scenarios = list(scenarios or [])
        self.retry_policy = retry_policy
        self.fault_logger = fault_logger

    # --- 对外入口 ---

    def run_case(
        self, case: TestCase, run_id: str, execution_index: int = 0
    ) -> TestResult:
        """执行单个用例并返回完整结果；异常不会向外抛出。"""
        started_at = datetime.now(timezone.utc)
        start_counter = time.perf_counter()
        result = TestResult(
            run_id=run_id,
            case_id=case.case_id,
            case_name=case.name,
            started_at=started_at.isoformat(timespec="milliseconds"),
            finished_at="",
            duration_ms=0.0,
            status=TestStatus.ERROR,
            expected_state=case.expected_state,
            execution_index=execution_index,
        )

        psu = None
        load = None
        injector: ReliabilityFaultInjector | None = None
        retry_executor: RetryExecutor | None = None

        try:
            if not case.enabled:
                # 未启用用例不得触碰仪器
                result.status = TestStatus.SKIP
                result.error_message = "用例未启用（enabled: false），未访问仪器"
                return result

            psu = self.manager.get_power_supply()
            load = self.manager.get_electronic_load()

            injector, retry_executor = self._attach_reliability(
                psu, load, run_id, case.case_id
            )

            self._apply_setpoints(psu, load, case)
            self._verify_setpoints(psu, load, case)

            dut_result = self.bench.read_state()
            original_state = str(getattr(dut_result.state, "value", dut_result.state))
            original_payload = asdict(dut_result)
            original_payload["state"] = original_state
            result.original_model_data = original_payload
            result.original_data_source = getattr(dut_result, "source", None)

            # 测量故障只生成独立视图，原始 DUTResult 保持不变
            observed = apply_measurement_faults(dut_result, injector)
            observed_state = str(getattr(observed.state, "value", observed.state))

            result.actual_state = observed_state
            result.data_source = observed.source
            result.observed_data_source = getattr(observed, "source", None)

            raw_data = asdict(observed)
            raw_data["state"] = observed_state
            result.raw_data = raw_data
            if observed is not dut_result:
                result.observed_data = dict(raw_data)

            analysis = self._analyze(observed)
            result.metrics = analysis.get("metrics")
            result.quality_issues = list(analysis.get("quality_issues") or [])

            # 第一层：数据质量。ERROR 级问题直接结束，不进入限值判定
            if analysis.get("quality_status") != "VALID":
                messages = [
                    str(issue.get("message", issue))
                    for issue in result.quality_issues
                ]
                result.status = TestStatus.ERROR
                result.error_category = ErrorCategory.INVALID_DATA.value
                result.error_message = "数据质量检查未通过: " + "；".join(messages)
                return result

            # 第二层：DUT 状态
            checks = [judge_state(observed_state, case.expected_state)]

            # 第三层：工程性能限值（只判定配置中明确列出的指标）
            for name, limits in case.limits.items():
                checks.append(
                    judge_range(
                        name=name,
                        actual=self._resolve_metric(name, raw_data, result.metrics),
                        lower=limits["min"],
                        upper=limits["max"],
                    )
                )

            result.checks = checks
            result.status = aggregate_status(checks)
            if result.status is TestStatus.FAIL:
                result.error_message = "；".join(
                    f"{check.name}: {check.message}"
                    for check in checks
                    if check.status is TestStatus.FAIL
                )
            elif result.status is TestStatus.ERROR:
                result.error_message = "；".join(
                    f"{check.name}: {check.message}"
                    for check in checks
                    if check.status is TestStatus.ERROR
                )

        except Exception as exc:  # 执行引擎必须记录异常而不是崩溃
            result.status = TestStatus.ERROR
            result.error_category = classify_error(exc).value
            result.error_message = f"{type(exc).__name__}: {exc}"

        finally:
            cleanup_status, cleanup_errors, cleanup_events = self._cleanup(
                load,
                psu,
                injector,
                run_id=run_id,
                case_id=case.case_id,
            )
            result.cleanup_status = cleanup_status.value
            result.cleanup_errors = list(cleanup_errors)
            if cleanup_errors:
                result.status = TestStatus.ERROR
                result.cleanup_failed = True
                if result.error_category is None:
                    result.error_category = ErrorCategory.SHUTDOWN_ERROR.value
                previous = result.error_message or ""
                result.error_message = (
                    f"{previous}；清理失败: {'; '.join(cleanup_errors)}".strip("；")
                )

            self._collect_reliability(
                result, injector, retry_executor, cleanup_events
            )
            self._detach_reliability(psu, load)

            result.finished_at = datetime.now(timezone.utc).isoformat(
                timespec="milliseconds"
            )
            result.duration_ms = (
                time.perf_counter() - start_counter
            ) * 1000.0

        return result

    # --- 内部实现 ---

    @staticmethod
    def _apply_setpoints(psu: Any, load: Any, case: TestCase) -> None:
        """先回到安全状态，再下发新工况。"""
        load.set_input(False)
        psu.set_output(False)
        psu.set_voltage(case.vin)
        psu.set_current(case.input_current_limit)
        load.set_mode("CC")
        load.set_current(case.load_current)
        psu.set_output(case.output_enabled)
        load.set_input(case.load_enabled)

    def _attach_reliability(
        self,
        psu: Any,
        load: Any,
        run_id: str,
        case_id: str,
    ) -> tuple[ReliabilityFaultInjector | None, RetryExecutor | None]:
        """按配置创建注入器与重试执行器，并挂到当前仪器实例上。"""
        injector: ReliabilityFaultInjector | None = None
        if self._fault_scenarios:
            injector = ReliabilityFaultInjector(
                self._fault_scenarios,
                enabled=True,
                run_id=run_id,
                case_id=case_id,
                event_sink=self._log_event,
            )
            psu.fault_injector = injector
            load.fault_injector = injector

        policy = self.retry_policy
        if policy is None and not self._fault_scenarios:
            return injector, None
        if policy is None:
            policy = RetryPolicy()
        executor = RetryExecutor(
            policy,
            event_callback=self._log_event,
            run_id=run_id,
            case_id=case_id,
        )
        psu.retry_executor = executor
        load.retry_executor = executor
        return injector, executor

    @staticmethod
    def _detach_reliability(psu: Any, load: Any) -> None:
        for device in (psu, load):
            if device is None:
                continue
            try:
                device.fault_injector = None
                device.retry_executor = None
            except Exception:
                # 假仪器/只读对象没有可写属性时忽略即可
                pass

    def _log_event(self, event: dict[str, Any]) -> None:
        if self.fault_logger is None:
            return
        try:
            emit = getattr(self.fault_logger, "emit", None)
            if callable(emit):
                emit(event)
            elif callable(self.fault_logger):
                self.fault_logger(event)
        except Exception as exc:
            # 事件日志失败不得阻断清理或掩盖原始测试异常
            self.logger_errors.append(
                f"事件日志写入失败: {type(exc).__name__}: {exc}"
            )

    def _analyze(self, observed: Any) -> dict[str, Any]:
        """调用分析器；兼容只接受单个参数的旧分析器实现。"""
        method = self.analyzer.analyze
        try:
            parameters = inspect.signature(method).parameters
        except (TypeError, ValueError):
            parameters = {}
        accepts_kwargs = any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD
            for parameter in parameters.values()
        )
        if "expected_source" in parameters or accepts_kwargs:
            return method(
                observed,
                expected_source=getattr(observed, "source", None),
            )
        return method(observed)

    @staticmethod
    def _collect_reliability(
        result: TestResult,
        injector: ReliabilityFaultInjector | None,
        retry_executor: RetryExecutor | None,
        extra_events: Sequence[dict[str, Any]] = (),
    ) -> None:
        events: list[dict[str, Any]] = []
        if injector is not None:
            events.extend(injector.events)
        if retry_executor is not None:
            events.extend(retry_executor.events)
        events.extend(extra_events)
        events.sort(
            key=lambda event: (
                str(event.get("timestamp") or ""),
                str(event.get("event_id") or ""),
            )
        )
        result.fault_events = events

        scenario_ids: list[str] = []
        for event in events:
            if str(event.get("event_type")) != EventType.FAULT_INJECTED.value:
                continue
            scenario_id = event.get("scenario_id")
            if scenario_id and scenario_id not in scenario_ids:
                scenario_ids.append(scenario_id)
        result.fault_scenario_ids = scenario_ids
        result.fault_injected = bool(scenario_ids)

        if retry_executor is not None:
            result.retry_count = int(retry_executor.retries)
            result.recovered = retry_executor.recovered_operations > 0
            result.retry_exhausted = (
                retry_executor.exhausted_operations > 0
                or any(
                    str(event.get("event_type"))
                    == EventType.RETRY_EXHAUSTED.value
                    for event in events
                )
            )

    @staticmethod
    def _resolve_metric(
        name: str,
        raw_data: dict[str, Any] | None,
        metrics: dict[str, Any] | None,
    ) -> Any:
        """按显式字段映射取指标值，避免两个来源互相覆盖。

        原始模型字段优先取 ``raw_data``，派生指标取 ``metrics``；
        两边都没有时返回 ``None``，由判定层给出 ERROR。
        """
        if raw_data and name in raw_data:
            return raw_data[name]
        if metrics and name in metrics:
            return metrics[name]
        return None

    def _verify_setpoints(self, psu: Any, load: Any, case: TestCase) -> None:
        """核对下发设定值与回读值，避免“设置失败但继续测量”。"""
        checks = (
            ("输入电压", psu.get_voltage(), case.vin),
            ("输入限流", psu.get_current(), case.input_current_limit),
            ("负载电流", load.get_current(), case.load_current),
        )
        for label, actual, expected in checks:
            if abs(float(actual) - float(expected)) > self.setpoint_tolerance:
                raise SetpointMismatchError(
                    f"{label}回读 {float(actual):g} 与设定 {float(expected):g} 不一致"
                )

        if case.load_enabled and load.get_mode() != "CC":
            raise SetpointMismatchError(
                f"电子负载模式回读 {load.get_mode()!r}，期望 'CC'"
            )

        if psu.get_output() != case.output_enabled:
            raise SetpointMismatchError(
                f"电源输出状态回读 {psu.get_output()}，期望 {case.output_enabled}"
            )

        if load.get_input() != case.load_enabled:
            raise SetpointMismatchError(
                f"负载输入状态回读 {load.get_input()}，期望 {case.load_enabled}"
            )

    def _cleanup(
        self,
        load: Any,
        psu: Any,
        injector: ReliabilityFaultInjector | None = None,
        *,
        run_id: str = "",
        case_id: str | None = None,
    ) -> tuple[CleanupStatus, list[str], list[dict[str, Any]]]:
        """独立尝试关闭负载与电源输出，并回读验证。

        - 任一步失败仍继续尝试其他独立步骤；
        - 只承诺 ``VERIFIED_OFF`` / ``NOT_VERIFIED``，不推断硬件实际状态；
        - 故障注入只在 cleanup 目标上生效（F009 的 ``OUTP 0``）；
        - 清理失败记录不会被后续资源释放改写为成功。
        """
        errors: list[str] = []
        step_records: list[dict[str, Any]] = []
        cleanup_events: list[dict[str, Any]] = []
        last_error: BaseException | None = None

        def record(event: dict[str, Any]) -> None:
            cleanup_events.append(event)
            self._log_event(event)

        record(
            new_event(
                EventType.CLEANUP_STARTED,
                run_id=run_id,
                case_id=case_id,
            )
        )

        if load is None and psu is None:
            record(
                new_event(
                    EventType.CLEANUP_COMPLETED,
                    run_id=run_id,
                    case_id=case_id,
                    cleanup_status=CleanupStatus.NOT_APPLICABLE.value,
                    details={"steps": []},
                )
            )
            return CleanupStatus.NOT_APPLICABLE, [], cleanup_events

        steps: list[tuple[str, str, Any, Callable[[], Any], Callable[[], bool]]] = []
        if load is not None:
            steps.append(
                (
                    "负载输入",
                    "INP 0",
                    load,
                    lambda: load.set_input(False),
                    lambda: load.get_input(),
                )
            )
        if psu is not None:
            steps.append(
                (
                    "电源输出",
                    "OUTP 0",
                    psu,
                    lambda: psu.set_output(False),
                    lambda: psu.get_output(),
                )
            )

        for label, operation, device, action, readback in steps:
            try:
                if injector is not None:
                    injector.before_cleanup(
                        operation, device=getattr(device, "device_id", None)
                    )
                action()
                if readback():
                    raise RuntimeError(f"{label}关闭未生效")
                step_records.append(
                    {
                        "step": label,
                        "operation": operation,
                        "status": CleanupStatus.VERIFIED_OFF.value,
                    }
                )
            except Exception as exc:
                last_error = exc
                errors.append(f"{label}关闭失败: {type(exc).__name__}: {exc}")
                step_records.append(
                    {
                        "step": label,
                        "operation": operation,
                        "status": CleanupStatus.NOT_VERIFIED.value,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

        if errors:
            status = CleanupStatus.NOT_VERIFIED
            record(
                new_event(
                    EventType.CLEANUP_FAILED,
                    run_id=run_id,
                    case_id=case_id,
                    cleanup_status=status.value,
                    message="; ".join(errors),
                    exception_type=(
                        type(last_error).__name__ if last_error is not None else None
                    ),
                    error_category=(
                        classify_error(last_error).value
                        if last_error is not None
                        else None
                    ),
                    details={"steps": step_records},
                )
            )
        else:
            status = CleanupStatus.VERIFIED_OFF
            record(
                new_event(
                    EventType.CLEANUP_COMPLETED,
                    run_id=run_id,
                    case_id=case_id,
                    cleanup_status=status.value,
                    details={"steps": step_records},
                )
            )

        return status, errors, cleanup_events


#: 兼容旧代码的别名（阶段四~六脚本与测试使用字典用例执行器）
LegacyTestRunner = ScenarioTestRunner
