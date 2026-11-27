"""第七阶段控制器统一数据模型（SI 单位）。

只做参数定义与校验，不构建电路、不执行仿真。
所有数值来自 ``configs/closed_loop_config.yaml`` / ``configs/controller_config.yaml``。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from circuits.validators import finite_number, positive_number

ANTI_WINDUP_METHODS = ("none", "conditional", "back_calculation")
CARRIER_TYPES = ("sine", "sawtooth")


@dataclass(frozen=True)
class ControllerConfig:
    """电压模式 PI 控制器参数。

    ``kp`` 单位 duty/V，``ki`` 单位 duty/(V·s)。
    """

    kp: float
    ki: float
    duty_min: float = 0.0
    duty_max: float = 0.9
    feedforward_enabled: bool = True
    anti_windup: str = "back_calculation"
    tracking_gain: float = 2000.0
    vin_min_for_feedforward_v: float = 2.0

    def __post_init__(self) -> None:
        kp = finite_number(self.kp, "controller.kp")
        ki = finite_number(self.ki, "controller.ki")
        if kp < 0 or ki < 0:
            raise ValueError("controller gains must be nonnegative")
        if not (0.0 <= self.duty_min < self.duty_max <= 1.0):
            raise ValueError("controller duty limits must satisfy 0 <= min < max <= 1")
        if self.anti_windup not in ANTI_WINDUP_METHODS:
            raise ValueError(
                f"controller.anti_windup must be one of {ANTI_WINDUP_METHODS}"
            )
        positive_number(self.tracking_gain, "controller.tracking_gain")
        positive_number(
            self.vin_min_for_feedforward_v, "controller.vin_min_for_feedforward_v"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kp": self.kp,
            "ki": self.ki,
            "duty_min": self.duty_min,
            "duty_max": self.duty_max,
            "feedforward_enabled": self.feedforward_enabled,
            "anti_windup": self.anti_windup,
            "tracking_gain": self.tracking_gain,
            "vin_min_for_feedforward_v": self.vin_min_for_feedforward_v,
            "units": {"kp": "duty/V", "ki": "duty/(V*s)", "tracking_gain": "1/s"},
            "model_source": "educational_assumption",
        }


@dataclass(frozen=True)
class SoftStartConfig:
    """参考电压软启动参数。"""

    enabled: bool = True
    duration_s: float = 0.002
    initial_reference_v: float = 0.0

    def __post_init__(self) -> None:
        finite_number(self.duration_s, "soft_start.duration_s")
        if self.duration_s < 0:
            raise ValueError("soft_start.duration_s must be nonnegative")
        initial = finite_number(
            self.initial_reference_v, "soft_start.initial_reference_v"
        )
        if initial < 0:
            raise ValueError("soft_start.initial_reference_v must be nonnegative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "duration_s": self.duration_s,
            "initial_reference_v": self.initial_reference_v,
        }


@dataclass(frozen=True)
class CarrierConfig:
    """PWM 载波参数。

    ``sine`` 载波在 0—1 之间正弦变化，比较器输出经有限过渡带平滑；
    其平均占空比与阈值之间为反正弦关系（见 ``control.pwm_modulator``）。
    """

    carrier_type: str = "sine"
    frequency_hz: float = 100_000.0
    smoothing_width: float = 0.02
    threshold: float = 0.5

    def __post_init__(self) -> None:
        if self.carrier_type not in CARRIER_TYPES:
            raise ValueError(f"carrier.type must be one of {CARRIER_TYPES}")
        positive_number(self.frequency_hz, "carrier.frequency_hz")
        width = positive_number(self.smoothing_width, "carrier.smoothing_width")
        if width >= 0.5:
            raise ValueError("carrier.smoothing_width must be < 0.5")
        finite_number(self.threshold, "carrier.threshold")
        if not 0.0 < self.threshold < 1.0:
            raise ValueError("carrier.threshold must be in (0, 1)")

    @property
    def period_s(self) -> float:
        return 1.0 / self.frequency_hz

    def to_dict(self) -> dict[str, Any]:
        return {
            "carrier_type": self.carrier_type,
            "frequency_hz": self.frequency_hz,
            "period_s": self.period_s,
            "smoothing_width": self.smoothing_width,
            "threshold": self.threshold,
        }


@dataclass(frozen=True)
class ControlSample:
    """控制器单次采样记录（真实波形或平均模型求解结果）。"""

    time_s: float
    reference_v: float
    feedback_v: float
    error_v: float
    feedforward_duty: float
    proportional_term: float
    integral_state: float
    raw_duty: float
    limited_duty: float


@dataclass
class ControllerDiagnostics:
    """控制器运行诊断累计量（只做记录，不修改控制量）。"""

    samples: int = 0
    saturated_high_samples: int = 0
    saturated_low_samples: int = 0
    maximum_abs_raw_duty: float = 0.0
    maximum_abs_integral: float = 0.0
    last_correction: float = 0.0
    reset_count: int = 0
    history: list[ControlSample] = field(default_factory=list)

    def record(self, sample: ControlSample, correction: float = 0.0) -> None:
        self.samples += 1
        if sample.raw_duty > sample.limited_duty + 1e-12:
            self.saturated_high_samples += 1
        if sample.raw_duty < sample.limited_duty - 1e-12:
            self.saturated_low_samples += 1
        self.maximum_abs_raw_duty = max(
            self.maximum_abs_raw_duty, abs(sample.raw_duty)
        )
        self.maximum_abs_integral = max(
            self.maximum_abs_integral, abs(sample.integral_state)
        )
        self.last_correction = correction
        self.history.append(sample)

    def to_dict(self) -> dict[str, Any]:
        return {
            "samples": self.samples,
            "saturated_high_samples": self.saturated_high_samples,
            "saturated_low_samples": self.saturated_low_samples,
            "maximum_abs_raw_duty": self.maximum_abs_raw_duty,
            "maximum_abs_integral": self.maximum_abs_integral,
            "last_correction": self.last_correction,
            "reset_count": self.reset_count,
        }
