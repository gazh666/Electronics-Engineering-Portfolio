"""带迟滞、确认延时与传输延时的模拟比较器行为模型。

保护阈值本身只是"什么时候开始计数"，真正跳闸还需要连续满足条件达到确认延时。
迟滞决定释放点，传输延时决定逻辑输出相对判决的滞后。三者分开记录，便于
与真实 SPICE 比较器网表逐项对照。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


class ComparatorError(ValueError):
    """比较器参数或输入非法。"""


def _finite(value: float, name: str) -> float:
    if isinstance(value, bool):
        raise ComparatorError(f"{name} 不允许使用布尔值")
    number = float(value)
    if not math.isfinite(number):
        raise ComparatorError(f"{name} 必须是有限数值")
    return number


@dataclass(frozen=True)
class ComparatorConfig:
    """单个保护通道的比较器配置。

    ``direction="high"``：输入升高越过 ``threshold`` 触发（过压/过流/过温）。
    ``direction="low"``：输入降低越过 ``threshold`` 触发（欠压/欠温）。
    """

    name: str
    threshold: float
    hysteresis: float
    confirmation_delay_s: float
    propagation_delay_s: float = 0.0
    direction: str = "high"

    def __post_init__(self) -> None:
        if self.direction not in ("high", "low"):
            raise ComparatorError("direction 只能是 high 或 low")
        if not isinstance(self.name, str) or not self.name:
            raise ComparatorError("比较器名称必须是非空字符串")
        threshold = _finite(self.threshold, "threshold")
        hysteresis = _finite(self.hysteresis, "hysteresis")
        delay = _finite(self.confirmation_delay_s, "confirmation_delay_s")
        propagation = _finite(self.propagation_delay_s, "propagation_delay_s")
        if hysteresis < 0.0:
            raise ComparatorError("迟滞不能为负")
        if delay < 0.0:
            raise ComparatorError("确认延时不能为负")
        if propagation < 0.0:
            raise ComparatorError("传输延时不能为负")
        object.__setattr__(self, "threshold", threshold)
        object.__setattr__(self, "hysteresis", hysteresis)
        object.__setattr__(self, "confirmation_delay_s", delay)
        object.__setattr__(self, "propagation_delay_s", propagation)

    @property
    def release_threshold(self) -> float:
        """迟滞定义的释放点。"""
        if self.direction == "high":
            return self.threshold - self.hysteresis
        return self.threshold + self.hysteresis


@dataclass(frozen=True)
class ComparatorReading:
    """一次比较器更新的完整可追溯记录。"""

    name: str
    time_s: float
    value: float
    condition_active: bool
    tripped: bool
    output: bool
    pending_s: float
    trip_time_s: float | None
    release_time_s: float | None


@dataclass
class HysteresisComparator:
    """模拟比较器 + 确认延时 + 传输延时的离散实现。"""

    config: ComparatorConfig
    tripped: bool = False
    output: bool = False
    trip_pending_since_s: float | None = None
    release_pending_since_s: float | None = None
    trip_time_s: float | None = None
    release_time_s: float | None = None
    _pending_output: bool | None = None
    _output_change_time_s: float | None = None
    history: list[ComparatorReading] = field(default_factory=list)

    def reset(self) -> None:
        self.tripped = False
        self.output = False
        self.trip_pending_since_s = None
        self.release_pending_since_s = None
        self.trip_time_s = None
        self.release_time_s = None
        self._pending_output = None
        self._output_change_time_s = None
        self.history.clear()

    def _condition(self, value: float) -> bool:
        cfg = self.config
        if not self.tripped:
            return value >= cfg.threshold if cfg.direction == "high" else value <= cfg.threshold
        return value > cfg.release_threshold if cfg.direction == "high" else value < cfg.release_threshold

    def step(self, value: float, time_s: float) -> ComparatorReading:
        cfg = self.config
        measurement = _finite(value, f"{cfg.name} 输入")
        now = _finite(time_s, f"{cfg.name} 时间")
        if self.history and now < self.history[-1].time_s:
            raise ComparatorError("时间不能倒退")

        active = self._condition(measurement)

        # 触发确认计时与释放确认计时严格分开，避免释放条件把自身计时清零。
        trip_elapsed = 0.0
        release_elapsed = 0.0
        if not self.tripped:
            if active:
                if self.trip_pending_since_s is None:
                    self.trip_pending_since_s = now
                trip_elapsed = now - self.trip_pending_since_s
            else:
                self.trip_pending_since_s = None
            self.release_pending_since_s = None
        else:
            self.trip_pending_since_s = None
            if active:
                self.release_pending_since_s = None
            else:
                if self.release_pending_since_s is None:
                    self.release_pending_since_s = now
                release_elapsed = now - self.release_pending_since_s

        # 判决（尚未考虑传输延时）。
        margin = 1e-12
        if not self.tripped and active and trip_elapsed + margin >= cfg.confirmation_delay_s:
            self.tripped = True
            self.trip_time_s = now
            self.trip_pending_since_s = None
        if self.tripped and not active and release_elapsed + margin >= cfg.confirmation_delay_s:
            self.tripped = False
            self.release_time_s = now
            self.release_pending_since_s = None

        # 逻辑输出跟随锁存状态，但可以带传输延时；延时期间状态回退则取消。
        target_level = self.tripped
        if target_level != self.output:
            if cfg.propagation_delay_s <= 0.0:
                self.output = target_level
                self._pending_output = None
                self._output_change_time_s = now
            else:
                if self._pending_output != target_level:
                    self._pending_output = target_level
                    self._output_change_time_s = now
                assert self._output_change_time_s is not None
                if now - self._output_change_time_s >= cfg.propagation_delay_s:
                    self.output = target_level
                    self._pending_output = None
                    self._output_change_time_s = now
        else:
            self._pending_output = None
            self._output_change_time_s = None

        reading = ComparatorReading(
            name=cfg.name,
            time_s=now,
            value=measurement,
            condition_active=active,
            tripped=self.tripped,
            output=self.output,
            pending_s=trip_elapsed if not self.tripped else release_elapsed,
            trip_time_s=self.trip_time_s,
            release_time_s=self.release_time_s,
        )
        self.history.append(reading)
        return reading


def evaluate_comparator(
    config: ComparatorConfig,
    values: list[float],
    times: list[float],
) -> list[ComparatorReading]:
    """对一段采样序列执行比较器，返回逐步记录。"""
    if len(values) != len(times):
        raise ComparatorError("采样值与时间长度不一致")
    comparator = HysteresisComparator(config)
    return [comparator.step(value, time) for value, time in zip(values, times)]


def first_trip_time(readings: list[ComparatorReading]) -> float | None:
    for reading in readings:
        if reading.trip_time_s is not None:
            return reading.trip_time_s
    return None


def chatter_count(readings: list[ComparatorReading]) -> int:
    """统计输出翻转次数，用于验证迟滞是否抑制抖动。"""
    flips = 0
    previous = readings[0].output if readings else False
    for reading in readings[1:]:
        if reading.output != previous:
            flips += 1
        previous = reading.output
    return flips
