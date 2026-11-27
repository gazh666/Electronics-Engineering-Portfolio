"""BatteryLab 第四阶段采集信号统一数据结构与状态定义。

所有未知量使用 ``None``，禁止用 0 冒充未知数据。状态字符串只使用本模块
定义的常量，便于下游统计与限值检查。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

# 采集状态（Task 24）
STATUS_VALID = "VALID"
STATUS_SATURATED = "SATURATED"
STATUS_COMMON_MODE_OUT_OF_RANGE = "COMMON_MODE_OUT_OF_RANGE"
STATUS_INVALID_INPUT = "INVALID_INPUT"
STATUS_SENSOR_OPEN = "SENSOR_OPEN"
STATUS_SENSOR_SHORT = "SENSOR_SHORT"
STATUS_STALE_DATA = "STALE_DATA"
STATUS_NOT_VERIFIED = "NOT_VERIFIED"

ALLOWED_STATUSES = frozenset(
    {
        STATUS_VALID,
        STATUS_SATURATED,
        STATUS_COMMON_MODE_OUT_OF_RANGE,
        STATUS_INVALID_INPUT,
        STATUS_SENSOR_OPEN,
        STATUS_SENSOR_SHORT,
        STATUS_STALE_DATA,
        STATUS_NOT_VERIFIED,
    }
)

# 数据来源类型
DATA_SOURCE_CHOICES = frozenset(
    {
        "spice_simulation",
        "adc_behavioral_model",
        "analytical_theory",
        "educational_assumption",
        "identified_parameters",
        "datasheet_specification",
        "public_experimental_data",
        "synthetic_test_data",
    }
)


class MeasurementModelError(ValueError):
    """采集数据结构输入非法。"""


@dataclass(frozen=True)
class MeasurementResult:
    """一次采集通道结果。

    必填字段对应任务书最小结构；其余为工程扩展字段。
    """

    channel_name: str
    physical_input: float | None
    analog_output_v: float | None
    adc_code: int | None
    estimated_value: float | None
    unit: str
    status: str
    data_source: str
    time_s: float | None = None
    measurement_timestamp_s: float | None = None
    run_id: str | None = None
    circuit_model: str | None = None
    calibration_id: str | None = None
    raw_signal: float | None = None
    filtered_signal: float | None = None
    measurement_error: float | None = None
    parameter_source: str | None = None
    note: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.channel_name, str) or not self.channel_name:
            raise MeasurementModelError("channel_name 必须是非空字符串")
        if not isinstance(self.unit, str) or not self.unit:
            raise MeasurementModelError("unit 必须是非空字符串")
        if self.status not in ALLOWED_STATUSES:
            raise MeasurementModelError(f"未知状态: {self.status!r}")
        if self.data_source not in DATA_SOURCE_CHOICES:
            raise MeasurementModelError(f"未知数据来源: {self.data_source!r}")
        if self.status == STATUS_VALID and self.estimated_value is None:
            raise MeasurementModelError("VALID 状态必须提供 estimated_value")

    @property
    def is_valid(self) -> bool:
        return self.status == STATUS_VALID

    @property
    def measurement_error_or_none(self) -> float | None:
        if self.estimated_value is None or self.physical_input is None:
            return None
        return float(self.estimated_value) - float(self.physical_input)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def make_result(**kwargs: Any) -> MeasurementResult:
    """构造结果并自动补齐 measurement_error。"""
    result = MeasurementResult(**kwargs)
    if result.measurement_error is None:
        error = result.measurement_error_or_none
        if error is not None:
            object.__setattr__(result, "measurement_error", error)
    return result
