"""电池静置检测（Task 10 / Task 11 前置条件）。

静置的物理意义：电流接近零且端电压不再变化，电池内部极化（一阶 RC 的
Vp = I·R1 项）已按 ``exp(-t/tau1)`` 衰减到可忽略。只有此时端电压才近似等于
开路电压 OCV，才能用 OCV-SOC 曲线反推 SOC。

本模块只做**因果**判断：所有电压变化率均来自过去 30 s 的历史窗口，
绝不使用未来样本判断"过去是否已经松弛"。

判据（全部同时满足才返回 True）：

1. 电流绝对值 ≤ ``maximum_current_a``（默认 20 mA）；
2. 采样有效 ``valid``；
3. 温度在适用范围内（提供时）；
4. 均衡支路电流 ≤ ``maximum_balance_current_a``；
5. 无保护异常 ``protection_ok``；
6. 无数据缺口（单步间隔 ≤ ``maximum_gap_s``）；
7. 最近 ``slope_window_s`` 内电压变化率 ≤ ``maximum_voltage_slope_v_per_s``；
8. 持续静置时间 ≥ ``minimum_rest_time_s``。

注意：300 s 不是普适松弛时间。第三阶段辨识的最大时间常数 tau1 ≈ 18 s，
3~5 倍 tau 约 55~90 s 已衰减 95% 以上；对更大时间常数的电芯必须重新评估。
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field


class RestDetectorError(ValueError):
    """静置检测输入非法。"""


@dataclass
class RestDetector:
    """持续低电流 + 电压稳定 + 时间足够的静置判定器。"""

    maximum_current_a: float = 0.02
    minimum_rest_time_s: float = 300.0
    maximum_gap_s: float = 2.0
    maximum_voltage_slope_v_per_s: float = 2.0e-5
    slope_window_s: float = 30.0
    maximum_balance_current_a: float = 0.005
    minimum_temperature_c: float = -20.0
    maximum_temperature_c: float = 60.0

    rest_start_s: float | None = None
    last_time_s: float | None = None

    voltage_slope_v_per_s: float | None = field(default=None, init=False)
    rest_duration_s: float = field(default=0.0, init=False)
    last_reason: str = field(default="NOT_EVALUATED", init=False)
    _voltage_history: deque[tuple[float, float]] = field(default_factory=deque, init=False, repr=False)

    def __post_init__(self) -> None:
        for name in (
            "maximum_current_a",
            "minimum_rest_time_s",
            "maximum_gap_s",
            "maximum_voltage_slope_v_per_s",
            "slope_window_s",
            "maximum_balance_current_a",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value < 0.0:
                raise RestDetectorError(f"{name} 必须为非负有限值")
        if self.minimum_temperature_c >= self.maximum_temperature_c:
            raise RestDetectorError("温度范围非法")
        if self.slope_window_s <= 0.0:
            raise RestDetectorError("斜率窗口必须为正")

    def reset(self) -> None:
        """清除静置状态（不改变判据参数）。"""
        self.rest_start_s = None
        self.last_time_s = None
        self.voltage_slope_v_per_s = None
        self.rest_duration_s = 0.0
        self.last_reason = "RESET"
        self._voltage_history.clear()

    def _update_voltage_slope(self, time_s: float, voltage_v: float | None) -> bool:
        """更新电压历史并计算窗口斜率；返回斜率是否满足阈值。"""
        if voltage_v is None or not math.isfinite(float(voltage_v)):
            self.voltage_slope_v_per_s = None
            return True  # 未提供电压时不以此项否决
        self._voltage_history.append((float(time_s), float(voltage_v)))
        horizon = float(time_s) - self.slope_window_s
        while len(self._voltage_history) > 2 and self._voltage_history[1][0] <= horizon:
            self._voltage_history.popleft()

        oldest_time, oldest_voltage = self._voltage_history[0]
        span = float(time_s) - oldest_time
        # 至少覆盖半个窗口才认为斜率有意义，避免用极短基线放大噪声。
        if span < 0.5 * self.slope_window_s:
            self.voltage_slope_v_per_s = None
            return True
        slope = (float(voltage_v) - oldest_voltage) / span
        self.voltage_slope_v_per_s = float(slope)
        return abs(slope) <= self.maximum_voltage_slope_v_per_s

    def update(
        self,
        time_s: float,
        current_a: float,
        valid: bool = True,
        voltage_v: float | None = None,
        temperature_c: float | None = None,
        balance_current_a: float = 0.0,
        protection_ok: bool = True,
    ) -> bool:
        """推进一个采样点，返回当前是否满足完整静置条件。"""
        if not math.isfinite(float(time_s)) or not math.isfinite(float(current_a)):
            self.reset()
            return False
        if not math.isfinite(float(balance_current_a)):
            self.reset()
            return False

        if self.last_time_s is not None:
            dt = float(time_s) - self.last_time_s
            if dt <= 0.0:
                raise RestDetectorError("时间轴必须严格递增")
            if dt > self.maximum_gap_s:
                # 数据缺口：静置证据链中断，必须重新计时。
                self.rest_start_s = None
                self._voltage_history.clear()

        self.last_time_s = float(time_s)
        slope_ok = self._update_voltage_slope(float(time_s), voltage_v)

        if not valid:
            self.rest_start_s = None
            self.last_reason = "INVALID_SAMPLE"
            self.rest_duration_s = 0.0
            return False
        if abs(float(current_a)) > self.maximum_current_a:
            self.rest_start_s = None
            self.last_reason = "CURRENT_TOO_HIGH"
            self.rest_duration_s = 0.0
            return False
        if abs(float(balance_current_a)) > self.maximum_balance_current_a:
            self.rest_start_s = None
            self.last_reason = "BALANCING_ACTIVE"
            self.rest_duration_s = 0.0
            return False
        if not protection_ok:
            self.rest_start_s = None
            self.last_reason = "PROTECTION_FAULT"
            self.rest_duration_s = 0.0
            return False
        if temperature_c is not None and math.isfinite(float(temperature_c)):
            if not self.minimum_temperature_c <= float(temperature_c) <= self.maximum_temperature_c:
                self.rest_start_s = None
                self.last_reason = "TEMPERATURE_OUT_OF_RANGE"
                self.rest_duration_s = 0.0
                return False

        if self.rest_start_s is None:
            self.rest_start_s = float(time_s)

        self.rest_duration_s = float(time_s) - self.rest_start_s
        if not slope_ok:
            self.last_reason = "VOLTAGE_NOT_STABLE"
            return False
        if self.rest_duration_s < self.minimum_rest_time_s:
            self.last_reason = "REST_TIME_SHORT"
            return False

        self.last_reason = "VALID_REST"
        return True
