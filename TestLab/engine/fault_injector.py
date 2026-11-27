"""故障注入：在模型参数层与仪器读取层制造可重复的异常场景。

设计原则
--------
- 只修改本项目的 DUT 行为模型参数，或在**业务层**包装仪器读数；
  不修改 PyVISA-sim、上游驱动或 YAML 中的 SCPI 响应。
- 注入由明确的 :class:`FaultSpec` 配置驱动，触发顺序确定，不使用随机数，
  因此同一配置可以完全复现。
- 注入的故障不是真实硬件故障，不能用于证明真实设备的保护特性。

故障类型
--------
``communication_timeout`` / ``instrument_disconnect`` / ``invalid_response`` /
``nan_data`` / ``voltage_offset`` / ``current_offset`` / ``test_interruption``
"""

from __future__ import annotations

import math
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Sequence

from instruments.base import (
    InstrumentError,
    InstrumentNotConnectedError,
    InstrumentTimeoutError,
)
from models.virtual_dut import VirtualDUT

# --- 故障类型 ---
FAULT_TIMEOUT = "communication_timeout"
FAULT_DISCONNECT = "instrument_disconnect"
FAULT_INVALID_RESPONSE = "invalid_response"
FAULT_NAN = "nan_data"
FAULT_VOLTAGE_OFFSET = "voltage_offset"
FAULT_CURRENT_OFFSET = "current_offset"
FAULT_INTERRUPT = "test_interruption"

FAULT_TYPES = frozenset(
    {
        FAULT_TIMEOUT,
        FAULT_DISCONNECT,
        FAULT_INVALID_RESPONSE,
        FAULT_NAN,
        FAULT_VOLTAGE_OFFSET,
        FAULT_CURRENT_OFFSET,
        FAULT_INTERRUPT,
    }
)

# --- 注入位置 ---
LOCATION_BRIDGE = "dut_bridge.acquire"
LOCATION_PSU_VOLTAGE = "psu.get_voltage"
LOCATION_LOAD_CURRENT = "load.get_current"
LOCATION_DMM_VOLTAGE = "dmm.read_dc_voltage"
LOCATION_DMM_CURRENT = "dmm.read_dc_current"

#: ``times=0`` 表示每次匹配都注入（用于“重试后仍失败”场景）
UNLIMITED = 0


class TestInterrupted(RuntimeError):
    """模拟测试中断。

    继承 ``RuntimeError`` 而不是 ``KeyboardInterrupt``，让执行引擎可以按
    普通异常记录 ERROR，并在 ``finally`` 中关闭输出、释放资源。
    """

    #: 阻止 pytest 把本类当作测试用例收集
    __test__ = False


@dataclass(frozen=True)
class FaultSpec:
    """一条可复现的故障注入配置。

    Parameters
    ----------
    fault_type
        故障类型，必须是 :data:`FAULT_TYPES` 之一。
    location
        注入位置，例如 ``dut_bridge.acquire``、``dmm.read_dc_voltage``。
    times
        最多注入次数；``0`` 表示无限次（每次都失败）。
    value
        仅偏移类故障使用：给读数叠加的偏移量（V 或 A）。
    """

    fault_type: str
    location: str
    times: int = 1
    value: float = 0.0

    def __post_init__(self) -> None:
        if self.fault_type not in FAULT_TYPES:
            raise ValueError(f"未知故障类型: {self.fault_type!r}")
        if not isinstance(self.location, str) or not self.location.strip():
            raise ValueError("故障注入位置不能为空")
        if self.times < 0:
            raise ValueError("注入次数不能为负")
        if not math.isfinite(self.value):
            raise ValueError("偏移量必须是有限数值")


@dataclass
class FaultRecord:
    """一条故障配置的运行记录。"""

    fault_type: str
    location: str
    occurrences: int = 0
    retries: int = 0
    final_status: str = "NOT_TRIGGERED"

    def to_dict(self) -> dict[str, object]:
        return {
            "fault_type": self.fault_type,
            "location": self.location,
            "occurrences": self.occurrences,
            "retries": self.retries,
            "final_status": self.final_status,
        }


class FaultInjector:
    """按 :class:`FaultSpec` 序列注入故障，并记录每次注入的元数据。

    同一个实例在单个用例内使用；``finalize(status)`` 会把最终处理状态
    （PASS/FAIL/ERROR/SKIP）写入已触发的故障记录。
    """

    def __init__(
        self,
        dut: VirtualDUT | None = None,
        specs: Sequence[FaultSpec] = (),
    ) -> None:
        self.dut = dut
        self.specs = list(specs)
        self._used = [0] * len(self.specs)
        self.records = [FaultRecord(spec.fault_type, spec.location) for spec in self.specs]
        self._last_record: FaultRecord | None = None

    # --- 读数/命令注入 ---

    def apply(self, location: str, value: float | None = None) -> float | None:
        """在一次仪器读取或命令前注入故障。

        Parameters
        ----------
        location
            当前操作位置，必须与 :class:`FaultSpec.location` 完全一致。
        value
            原始读数；命令型操作传 ``None``（此时不能使用 NaN/偏移故障）。

        Returns
        -------
        float | None
            未被修改的 ``value``，或叠加偏移/替换为 NaN 后的值。

        Raises
        ------
        InstrumentTimeoutError / InstrumentNotConnectedError / InstrumentError
            ``communication_timeout`` / ``instrument_disconnect`` /
            ``invalid_response`` 故障。
        TestInterrupted
            ``test_interruption`` 故障。
        """
        spec, record = self._next(location)
        if spec is None:
            return value

        record.occurrences += 1
        self._last_record = record

        if spec.fault_type == FAULT_TIMEOUT:
            record.final_status = "RAISED"
            raise InstrumentTimeoutError(f"注入通信超时 @ {location}")

        if spec.fault_type == FAULT_DISCONNECT:
            record.final_status = "RAISED"
            raise InstrumentNotConnectedError(f"注入仪器断开 @ {location}")

        if spec.fault_type == FAULT_INVALID_RESPONSE:
            record.final_status = "RAISED"
            raise InstrumentError(f"注入非法字符串响应 @ {location}")

        if spec.fault_type == FAULT_INTERRUPT:
            record.final_status = "RAISED"
            raise TestInterrupted(f"注入测试中断 @ {location}")

        if spec.fault_type == FAULT_NAN:
            if value is None:
                raise ValueError(f"NaN 故障只能注入到读数 @ {location}")
            record.final_status = "MUTATED"
            return float("nan")

        if spec.fault_type in (FAULT_VOLTAGE_OFFSET, FAULT_CURRENT_OFFSET):
            if value is None:
                raise ValueError(f"偏移故障只能注入到读数 @ {location}")
            record.final_status = "MUTATED"
            return float(value) + spec.value

        return value

    def _next(self, location: str) -> tuple[FaultSpec | None, FaultRecord | None]:
        for index, spec in enumerate(self.specs):
            if spec.location != location:
                continue
            if spec.times != UNLIMITED and self._used[index] >= spec.times:
                continue
            self._used[index] += 1
            return spec, self.records[index]
        return None, None

    # --- 记录 ---

    def mark_retry(self) -> None:
        """记录一次重试（归属于最近一次触发的故障）。"""
        if self._last_record is not None:
            self._last_record.retries += 1

    @property
    def total_retries(self) -> int:
        return sum(record.retries for record in self.records)

    @property
    def triggered(self) -> bool:
        return any(record.occurrences > 0 for record in self.records)

    def finalize(self, status: str) -> None:
        """写入最终处理状态（PASS/FAIL/ERROR/SKIP）。"""
        for record in self.records:
            if record.occurrences > 0:
                record.final_status = status

    def to_dicts(self) -> list[dict[str, object]]:
        return [record.to_dict() for record in self.records]

    # --- DUT 模型参数故障 ---

    @contextmanager
    def extra_dropout(self, volts: float) -> Iterator[None]:
        """降低标称输出电压，模拟功率通路劣化导致的额外压降。"""
        if volts < 0:
            raise ValueError("附加压降不能为负")
        if volts >= self.dut.nominal_voltage:
            raise ValueError("附加压降必须小于标称输出电压")
        previous = self.dut.nominal_voltage
        self.dut.nominal_voltage = previous - volts
        try:
            yield
        finally:
            self.dut.nominal_voltage = previous

    @contextmanager
    def disable_ocp(self) -> Iterator[None]:
        """把最大输出电流临时设为无限大，使过流保护失效。"""
        previous = self.dut.max_current
        self.dut.max_current = float("inf")
        try:
            yield
        finally:
            self.dut.max_current = previous

    @contextmanager
    def efficiency_override(self, efficiency: float) -> Iterator[None]:
        """覆盖模型效率参数。

        设置为大于 1 的值可构造“效率超过 100%”的数据异常场景，
        用于验证执行引擎会标记异常而不是截断。
        """
        if not math.isfinite(efficiency) or efficiency < 0:
            raise ValueError("效率必须是有限非负数")
        previous = self.dut.nominal_efficiency
        self.dut.nominal_efficiency = efficiency
        try:
            yield
        finally:
            self.dut.nominal_efficiency = previous
