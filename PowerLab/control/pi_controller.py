"""离散时间 PI 控制器（与 SPICE 行为控制器同一控制律）。

控制律与 ``control.spice_controller`` 中生成的网表表达式一致：

1. e = Vref − Vout
2. d_ff = Vref / Vin（前馈，可关闭）
3. d_p = Kp × e
4. d_raw = d_ff + d_p + xI
5. d = clamp(d_raw, d_min, d_max)
6. xI += (Ki × e + 抗饱和项) × dt
"""

from __future__ import annotations

from dataclasses import dataclass, field

from circuits.validators import finite_number, positive_number

from .anti_windup import clamp_duty, integral_increment
from .models import ControlSample, ControllerConfig, ControllerDiagnostics


@dataclass
class PIController:
    """电压模式 PI 控制器（带前馈、限幅和抗积分饱和）。"""

    config: ControllerConfig
    integral_state: float = 0.0
    diagnostics: ControllerDiagnostics = field(default_factory=ControllerDiagnostics)

    def reset(self, integral_state: float = 0.0) -> None:
        self.integral_state = finite_number(integral_state, "integral_state")
        self.diagnostics.reset_count += 1

    def feedforward_duty(self, reference_v: float, vin_v: float) -> float:
        if not self.config.feedforward_enabled:
            return 0.0
        reference = finite_number(reference_v, "reference_v")
        vin = finite_number(vin_v, "vin_v")
        if vin <= 0:
            return 0.0
        return reference / max(vin, self.config.vin_min_for_feedforward_v)

    def update(
        self,
        reference_v: float,
        measured_v: float,
        dt_s: float,
        *,
        vin_v: float = 12.0,
    ) -> ControlSample:
        """执行一次控制更新并返回本次采样记录。"""
        dt = positive_number(dt_s, "dt_s")
        reference = finite_number(reference_v, "reference_v")
        measured = finite_number(measured_v, "measured_v")
        error = reference - measured
        feedforward = self.feedforward_duty(reference, vin_v)
        proportional = self.config.kp * error
        raw = feedforward + proportional + self.integral_state
        limited = clamp_duty(raw, self.config.duty_min, self.config.duty_max)
        increment, correction = integral_increment(
            self.config.anti_windup,
            ki=self.config.ki,
            error_v=error,
            dt_s=dt,
            raw_duty=raw,
            limited_duty=limited,
            duty_min=self.config.duty_min,
            duty_max=self.config.duty_max,
            tracking_gain=self.config.tracking_gain,
        )
        sample = ControlSample(
            time_s=0.0,
            reference_v=reference,
            feedback_v=measured,
            error_v=error,
            feedforward_duty=feedforward,
            proportional_term=proportional,
            integral_state=self.integral_state,
            raw_duty=raw,
            limited_duty=limited,
        )
        self.integral_state += increment
        self.diagnostics.record(sample, correction)
        return sample

    def state_dict(self) -> dict[str, float | int | str]:
        payload = self.diagnostics.to_dict()
        payload["integral_state"] = self.integral_state
        payload["anti_windup"] = self.config.anti_windup
        return payload
