"""CC→CV 切换识别与阶段划分。

切换判定不使用"指令区域"标签，而是从真实电压/电流波形判定：
电压进入恒压目标容差并保持一段时间，才认为进入 CV。
开关纹波可能让单点越限，因此默认要求持续确认，并允许先做周期平均。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from analysis.charging_energy import _as_series, _as_time, integrate_zoh


@dataclass(frozen=True)
class TransitionSummary:
    reached_cv: bool
    transition_time_s: float | None
    cc_duration_s: float
    cv_duration_s: float
    voltage_at_transition_v: float | None
    current_at_transition_a: float | None
    voltage_overshoot_v: float
    final_voltage_v: float
    final_current_a: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "reached_cv": self.reached_cv,
            "transition_time_s": self.transition_time_s,
            "cc_duration_s": self.cc_duration_s,
            "cv_duration_s": self.cv_duration_s,
            "voltage_at_transition_v": self.voltage_at_transition_v,
            "current_at_transition_a": self.current_at_transition_a,
            "voltage_overshoot_v": self.voltage_overshoot_v,
            "final_voltage_v": self.final_voltage_v,
            "final_current_a": self.final_current_a,
        }


def _first_sustained_index(t: np.ndarray, mask: np.ndarray, hold_s: float) -> int | None:
    if hold_s < 0.0:
        raise ValueError("确认时间不能为负")
    if not mask.any():
        return None
    start = int(np.argmax(mask))
    while start < mask.size:
        if not mask[start]:
            next_true = np.flatnonzero(mask[start:])
            if next_true.size == 0:
                return None
            start += int(next_true[0])
        if hold_s == 0.0:
            return start
        deadline = t[start] + hold_s
        if deadline > t[-1]:
            return None
        stop = int(np.searchsorted(t, deadline, side="right"))
        if stop > mask.size:
            return None
        if bool(mask[start:stop].all()):
            return start
        start += 1
    return None


def detect_cc_to_cv_transition(
    time_s: Any,
    pack_voltage_v: Any,
    voltage_target_v: float,
    voltage_tolerance_v: float,
    hold_time_s: float = 1.0,
) -> float | None:
    """返回首次进入恒压容差并保持 ``hold_time_s`` 的时间；未进入返回 ``None``。"""
    t = _as_time(time_s)
    voltage = _as_series("pack_voltage_v", pack_voltage_v, t.size)
    if not math.isfinite(voltage_target_v) or not math.isfinite(voltage_tolerance_v):
        raise ValueError("恒压目标/容差非法")
    if voltage_tolerance_v <= 0.0:
        raise ValueError("容差必须为正")
    mask = voltage >= voltage_target_v - voltage_tolerance_v
    index = _first_sustained_index(t, mask, hold_time_s)
    return None if index is None else float(t[index])


def classify_charge_regions(
    time_s: Any,
    pack_voltage_v: Any,
    voltage_target_v: float,
    voltage_tolerance_v: float,
) -> np.ndarray:
    """逐点划分 ``CC`` / ``CV``（仅表示电压是否已到恒压区）。"""
    t = _as_time(time_s)
    voltage = _as_series("pack_voltage_v", pack_voltage_v, t.size)
    if not math.isfinite(voltage_target_v) or voltage_tolerance_v <= 0.0:
        raise ValueError("恒压目标/容差非法")
    return np.where(
        voltage >= voltage_target_v - voltage_tolerance_v,
        "CV",
        "CC",
    ).astype("<U2")


def transition_summary(
    time_s: Any,
    pack_voltage_v: Any,
    charging_current_a: Any,
    voltage_target_v: float,
    voltage_tolerance_v: float,
    hold_time_s: float = 1.0,
) -> TransitionSummary:
    t = _as_time(time_s)
    voltage = _as_series("pack_voltage_v", pack_voltage_v, t.size)
    current = _as_series("charging_current_a", charging_current_a, t.size)
    if voltage_tolerance_v <= 0.0:
        raise ValueError("容差必须为正")

    transition = detect_cc_to_cv_transition(
        t, voltage, voltage_target_v, voltage_tolerance_v, hold_time_s
    )
    overshoot = max(0.0, float(voltage.max() - voltage_target_v))

    if transition is None:
        return TransitionSummary(
            reached_cv=False,
            transition_time_s=None,
            cc_duration_s=float(t[-1] - t[0]),
            cv_duration_s=0.0,
            voltage_at_transition_v=None,
            current_at_transition_a=None,
            voltage_overshoot_v=overshoot,
            final_voltage_v=float(voltage[-1]),
            final_current_a=float(current[-1]),
        )

    index = int(np.searchsorted(t, transition, side="left"))
    index = min(index, t.size - 1)
    # 用切换点之后的数据统计 CV 段时长，避免把切换点本身算两次。
    cv_duration = float(t[-1] - transition)
    return TransitionSummary(
        reached_cv=True,
        transition_time_s=float(transition),
        cc_duration_s=float(transition - t[0]),
        cv_duration_s=cv_duration,
        voltage_at_transition_v=float(voltage[index]),
        current_at_transition_a=float(current[index]),
        voltage_overshoot_v=overshoot,
        final_voltage_v=float(voltage[-1]),
        final_current_a=float(current[-1]),
    )


def phase_charge_totals_ah(
    time_s: Any,
    pack_voltage_v: Any,
    charging_current_a: Any,
    voltage_target_v: float,
    voltage_tolerance_v: float,
) -> dict[str, float]:
    """分别统计 CC 段与 CV 段转入电池的电量（ZOH 积分）。"""
    t = _as_time(time_s)
    voltage = _as_series("pack_voltage_v", pack_voltage_v, t.size)
    current = _as_series("charging_current_a", charging_current_a, t.size)
    labels = classify_charge_regions(t, voltage, voltage_target_v, voltage_tolerance_v)

    def segment_charge(mask: np.ndarray) -> float:
        if mask.sum() < 2:
            return 0.0
        return integrate_zoh(current[mask], t[mask]) / 3600.0

    cc_mask = labels == "CC"
    cv_mask = labels == "CV"
    cc_ah = segment_charge(cc_mask)
    cv_ah = segment_charge(cv_mask)
    return {
        "cc_charge_ah": cc_ah,
        "cv_charge_ah": cv_ah,
        "total_charge_ah": cc_ah + cv_ah,
    }
