"""固定占空比 PWM 激励参数。

本模块只负责生成 ngspice ``PULSE`` 激励所需的参数，不生成理想波形。
实际 PWM 波形必须由 SPICE 求解器输出，再由 :mod:`analysis.buck_waveforms`
从真实 gate 波形中提取周期与占空比。

SPICE ``PULSE(V1 V2 TD TR TF PW PER)`` 中的 ``PW`` 是高电平平台持续时间，
不包含上升 / 下降边沿。当控制阈值位于高低电平中点、且上升下降时间相等时，
平台宽度由目标占空比反推::

    PW = D * T - (TR + TF) / 2

该近似只用于激励参数设计；实际有效占空比仍以阈值交点测量为准。
"""

from __future__ import annotations

from dataclasses import dataclass

from .validators import finite_number, nonnegative_number, positive_number

#: 一个开关周期内至少需要的时间步数（用于最大步长校验）。
MIN_STEPS_PER_PERIOD = 20


@dataclass(frozen=True)
class PWMParameters:
    """固定频率、固定占空比的 SPICE PULSE 激励参数。"""

    frequency_hz: float = 100_000.0
    duty_cycle: float = 5.0 / 12.0
    low_voltage_v: float = 0.0
    high_voltage_v: float = 5.0
    rise_time_s: float = 20e-9
    fall_time_s: float = 20e-9
    delay_s: float = 10e-6

    def __post_init__(self) -> None:
        positive_number(self.frequency_hz, "pwm.frequency_hz")
        finite_number(self.duty_cycle, "pwm.duty_cycle")
        low = finite_number(self.low_voltage_v, "pwm.low_voltage_v")
        high = finite_number(self.high_voltage_v, "pwm.high_voltage_v")
        positive_number(self.rise_time_s, "pwm.rise_time_s")
        positive_number(self.fall_time_s, "pwm.fall_time_s")
        nonnegative_number(self.delay_s, "pwm.delay_s")

        if not 0 < self.duty_cycle < 1:
            raise ValueError(f"pwm.duty_cycle must be in (0, 1), got {self.duty_cycle!r}")
        if high <= low:
            raise ValueError(
                f"pwm.high_voltage_v must exceed low_voltage_v, got {high!r} <= {low!r}"
            )
        if self.rise_time_s + self.fall_time_s >= self.period_s:
            raise ValueError("pwm rise + fall time must be shorter than one period")
        if self.pulse_width_s <= 0:
            raise ValueError(
                "pwm pulse width is not positive; duty cycle is too small for the selected edges: "
                f"{self.pulse_width_s!r} s"
            )
        full_pulse = self.rise_time_s + self.pulse_width_s + self.fall_time_s
        if full_pulse > self.period_s:
            raise ValueError(
                f"pwm full pulse {full_pulse!r} s exceeds period {self.period_s!r} s"
            )

    @property
    def period_s(self) -> float:
        """开关周期 ``T = 1 / f``（秒）。"""
        return 1.0 / self.frequency_hz

    @property
    def target_on_time_s(self) -> float:
        """目标导通时间 ``Ton = D * T``（秒）。"""
        return self.duty_cycle * self.period_s

    @property
    def threshold_voltage_v(self) -> float:
        """PWM 阈值交点电压 ``(Vhigh + Vlow) / 2``（伏）。"""
        return 0.5 * (self.high_voltage_v + self.low_voltage_v)

    @property
    def pulse_width_s(self) -> float:
        """SPICE PULSE 平台宽度 ``PW``（秒）。"""
        return self.target_on_time_s - 0.5 * (self.rise_time_s + self.fall_time_s)

    def to_dict(self) -> dict[str, float]:
        return {
            "frequency_hz": self.frequency_hz,
            "duty_cycle": self.duty_cycle,
            "low_voltage_v": self.low_voltage_v,
            "high_voltage_v": self.high_voltage_v,
            "rise_time_s": self.rise_time_s,
            "fall_time_s": self.fall_time_s,
            "delay_s": self.delay_s,
            "period_s": self.period_s,
            "target_on_time_s": self.target_on_time_s,
            "pulse_width_s": self.pulse_width_s,
            "threshold_voltage_v": self.threshold_voltage_v,
        }


def validate_timing_resolution(frequency_hz: float, max_step_time_s: float) -> float:
    """校验最大时间步长足以解析开关周期，返回每周期最大步数。

    要求 ``max_step_time_s <= T / MIN_STEPS_PER_PERIOD``。
    """
    frequency = positive_number(frequency_hz, "switching_frequency_hz")
    max_step = positive_number(max_step_time_s, "simulation.max_step_time_s")
    period = 1.0 / frequency
    steps = period / max_step
    if steps < MIN_STEPS_PER_PERIOD:
        raise ValueError(
            "simulation.max_step_time_s is too large for the switching period: "
            f"{steps:.3f} steps per period < {MIN_STEPS_PER_PERIOD}"
        )
    return steps
