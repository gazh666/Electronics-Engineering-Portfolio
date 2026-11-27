"""控制器整定：由穿越频率/零点位置设计 PI，并在 3×3 参数矩阵上评估。"""

from __future__ import annotations

import math
from typing import Any, Iterable

import numpy as np
import pandas as pd

from circuits.validators import positive_number

from .loop_analysis import (
    bandwidth_hz,
    classify_poles,
    closed_loop_poles,
    closed_loop_transfer,
    loop_gain,
    analyze_loop,
)
from .transfer_functions import TransferFunction, frequency_grid


def design_pi(
    plant: TransferFunction,
    crossover_hz: float,
    zero_hz: float,
    *,
    pwm_gain: float = 1.0,
    sensor_gain: float = 1.0,
) -> dict[str, float]:
    """按目标穿越频率与 PI 零点设计增益。

    Kp = 1 / (|Gp(jωc)|·Gpwm·H·sqrt(1+(fz/fc)²))，Ki = 2π fz Kp。
    """
    fc = positive_number(crossover_hz, "crossover_hz")
    fz = positive_number(zero_hz, "zero_hz")
    modulator = positive_number(pwm_gain, "pwm_gain")
    sensor = positive_number(sensor_gain, "sensor_gain")
    magnitude = float(abs(plant.evaluate(1j * 2.0 * math.pi * fc)))
    if magnitude <= 0:
        raise ValueError("plant magnitude at crossover must be positive")
    boost = math.sqrt(1.0 + (fz / fc) ** 2)
    kp = 1.0 / (magnitude * modulator * sensor * boost)
    ki = 2.0 * math.pi * fz * kp
    return {"kp": kp, "ki": ki, "crossover_hz": fc, "zero_hz": fz}


def _step_metrics(
    plant: TransferFunction,
    kp: float,
    ki: float,
    pwm_gain: float,
    *,
    duration_s: float = 0.05,
    points: int = 6000,
) -> dict[str, float]:
    """线性闭环阶跃响应指标（不包含饱和/限幅）。"""
    closed = closed_loop_transfer(plant, kp, ki, pwm_gain=pwm_gain)
    try:
        from scipy.signal import lti

        system = lti(closed.num, closed.den)
        time, response = system.step(T=np.linspace(0.0, duration_s, points))
    except Exception:  # noqa: BLE001 - 无 scipy 时返回空指标
        return {
            "overshoot_percent": math.nan,
            "settling_time_s": math.nan,
            "iae": math.nan,
            "steady_state_error": math.nan,
        }
    response = np.asarray(response, dtype=float)
    final = float(np.mean(response[-200:]))
    if not math.isfinite(final) or abs(final) < 1e-12:
        return {
            "overshoot_percent": math.nan,
            "settling_time_s": math.nan,
            "iae": math.nan,
            "steady_state_error": math.nan,
        }
    normalized = response / final
    overshoot = max(0.0, float(np.max(normalized) - 1.0)) * 100.0
    outside = np.where(np.abs(normalized - 1.0) > 0.02)[0]
    settling = float(time[outside[-1]]) if outside.size else 0.0
    iae = float(np.trapz(np.abs(1.0 - normalized), time))
    return {
        "overshoot_percent": overshoot,
        "settling_time_s": settling,
        "iae": iae,
        "steady_state_error": float(1.0 - final),
    }


def evaluate_candidate(
    plant: TransferFunction,
    kp: float,
    ki: float,
    *,
    pwm_gain: float = 1.0,
    frequencies_hz: Iterable[float] | None = None,
) -> dict[str, Any]:
    """评估单个 PI 参数组合（线性化平均模型）。"""
    frequencies = (
        frequency_grid(1.0, 1e6, 60)
        if frequencies_hz is None
        else np.asarray(list(frequencies_hz), dtype=float)
    )
    response = loop_gain(frequencies, plant, kp, ki, pwm_gain=pwm_gain)
    margins = analyze_loop(frequencies, response)
    poles = classify_poles(closed_loop_poles(plant, kp, ki, pwm_gain=pwm_gain))
    step = _step_metrics(plant, kp, ki, pwm_gain)
    if margins["status"] in ("UNSTABLE", "NO_CROSSOVER"):
        classification = "unstable" if margins["status"] == "UNSTABLE" else "not_resolved"
    elif poles["status"] == "UNSTABLE":
        classification = "unstable"
    elif margins["status"] == "LOW_MARGIN" or poles["status"] == "MARGINAL":
        classification = "low_margin"
    else:
        classification = "stable"
    return {
        "kp": float(kp),
        "ki": float(ki),
        "phase_margin_deg": margins["phase_margin_deg"],
        "gain_margin_db": margins["gain_margin_db"],
        "bandwidth_hz": bandwidth_hz(plant, kp, ki, pwm_gain=pwm_gain),
        "pole_status": poles["status"],
        "minimum_decay_rate": poles["minimum_decay_rate"],
        "crossings": len(margins["magnitude_crossings"]),
        "loop_status": margins["status"],
        "classification": classification,
        "overshoot_percent": step["overshoot_percent"],
        "settling_time_s": step["settling_time_s"],
        "iae": step["iae"],
        "messages": margins["messages"],
    }


def _score(row: dict[str, Any]) -> float:
    """评分：越小越好（裕度不足、超调大、慢、误差大均扣分）。"""
    penalty = 0.0
    if not math.isfinite(row["phase_margin_deg"]):
        penalty += 1e3
    else:
        penalty += max(0.0, 60.0 - row["phase_margin_deg"])
    if math.isfinite(row["overshoot_percent"]):
        penalty += row["overshoot_percent"] * 0.5
    if math.isfinite(row["settling_time_s"]):
        penalty += row["settling_time_s"] * 1000.0
    if math.isfinite(row["iae"]):
        penalty += row["iae"] * 1e3
    return penalty


def tuning_matrix(
    plant: TransferFunction,
    base_kp: float,
    base_ki: float,
    *,
    pwm_gain: float = 1.0,
    factors: tuple[float, ...] = (0.5, 1.0, 2.0),
) -> pd.DataFrame:
    """3×3 参数矩阵：Kp/Ki 各自按系数缩放。"""
    kp0 = positive_number(base_kp, "base_kp")
    ki0 = positive_number(base_ki, "base_ki")
    if not factors:
        raise ValueError("factors must not be empty")
    rows: list[dict[str, Any]] = []
    for kp_factor in factors:
        for ki_factor in factors:
            row = evaluate_candidate(
                plant, kp0 * kp_factor, ki0 * ki_factor, pwm_gain=pwm_gain
            )
            row["kp_factor"] = kp_factor
            row["ki_factor"] = ki_factor
            row["score"] = _score(row)
            rows.append(row)
    frame = pd.DataFrame(rows)
    return frame.sort_values("score", kind="stable").reset_index(drop=True)


def select_candidates(frame: pd.DataFrame, count: int = 3) -> list[dict[str, Any]]:
    """从矩阵中选择最多 ``count`` 个可用候选（稳定优先，其余不足时用低裕度）。"""
    if count <= 0:
        raise ValueError("count must be positive")
    stable = frame[frame["classification"] == "stable"]
    marginal = frame[frame["classification"] == "low_margin"]
    chosen = pd.concat([stable, marginal]).head(count)
    if chosen.empty:
        return []
    return chosen.to_dict(orient="records")
