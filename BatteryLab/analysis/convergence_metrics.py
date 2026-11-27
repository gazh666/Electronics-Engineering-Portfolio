"""初始 SOC 偏差与收敛评价（Task 17）。

``find_convergence_time`` 严格按预注册口径：

- 误差绝对值连续 ``hold_time_s`` 秒都 ≤ ``tolerance_pp`` 才算首次收敛；
- 时间缺口超过 ``maximum_gap_s`` 时重新计时（缺口内的"保持"不算证据）；
- 收敛后仍可能再次越界，因此额外报告收敛后的最大误差与终点误差。

"达到一次保持时间"只表示首次满足判据，不代表此后永久收敛。
"""

from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np


class ConvergenceError(ValueError):
    """收敛评价输入非法。"""


def find_convergence_time(
    time_s: Sequence[float],
    error_pp: Sequence[float],
    tolerance_pp: float = 2.0,
    hold_time_s: float = 60.0,
    maximum_gap_s: float = 2.0,
) -> dict[str, Any]:
    t = np.asarray(time_s, dtype=float)
    e = np.asarray(error_pp, dtype=float)
    if t.shape != e.shape:
        raise ConvergenceError("Shape mismatch")
    if t.ndim != 1 or len(t) < 2:
        raise ConvergenceError("Invalid waveform")
    if not (np.isfinite(t).all() and np.isfinite(e).all()):
        raise ConvergenceError("Invalid data")
    if np.any(np.diff(t) <= 0.0):
        raise ConvergenceError("Invalid time axis")
    if min(float(tolerance_pp), float(hold_time_s), float(maximum_gap_s)) <= 0.0:
        raise ConvergenceError("Invalid limits")

    start: float | None = None
    for k in range(len(t)):
        if k > 0 and (t[k] - t[k - 1]) > maximum_gap_s:
            start = None
        if abs(e[k]) <= tolerance_pp:
            if start is None:
                start = float(t[k])
            if t[k] - start >= hold_time_s:
                return {
                    "status": "CONVERGED",
                    "entry_time_s": float(start),
                    "confirmation_time_s": float(t[k]),
                    "elapsed_s": float(t[k] - t[0]),
                    "confirmation_index": int(k),
                }
        else:
            start = None

    return {
        "status": "NOT_CONVERGED",
        "entry_time_s": None,
        "confirmation_time_s": None,
        "elapsed_s": None,
        "confirmation_index": None,
    }


def summarize_convergence(
    time_s: Sequence[float],
    error_pp: Sequence[float],
    *,
    tolerance_pp: float = 2.0,
    hold_time_s: float = 60.0,
    maximum_gap_s: float = 2.0,
) -> dict[str, Any]:
    """在 ``find_convergence_time`` 基础上补齐收敛后与整体误差统计。"""
    result = find_convergence_time(
        time_s,
        error_pp,
        tolerance_pp=tolerance_pp,
        hold_time_s=hold_time_s,
        maximum_gap_s=maximum_gap_s,
    )
    t = np.asarray(time_s, dtype=float)
    e = np.asarray(error_pp, dtype=float)
    result.update(
        {
            "initial_error_pp": float(e[0]),
            "final_error_pp": float(e[-1]),
            "rmse_pp": float(np.sqrt(np.mean(e**2))),
            "max_absolute_error_pp": float(np.max(np.abs(e))),
            "tolerance_pp": float(tolerance_pp),
            "hold_time_s": float(hold_time_s),
        }
    )
    index = result.get("confirmation_index")
    if index is None:
        result["post_convergence_max_absolute_error_pp"] = None
        result["post_convergence_final_error_pp"] = None
    else:
        after = np.abs(e[int(index) :])
        result["post_convergence_max_absolute_error_pp"] = float(np.max(after))
        result["post_convergence_final_error_pp"] = float(e[-1])
    result.pop("confirmation_index", None)
    return result


def initial_soc_experiment_errors(
    initial_soc: float,
    errors_pp: Sequence[float],
) -> list[dict[str, float | str]]:
    """把初始误差（pp）展开为可执行的初始 SOC；超界组合如实标记不可执行。

    初始估计 SOC 不得超出 [0, 1]；如果某组合越界，记录
    ``status=NOT_EXECUTABLE`` 且不改变误差值，禁止静默裁剪。
    """
    if not 0.0 <= float(initial_soc) <= 1.0:
        raise ConvergenceError("初始参考 SOC 必须位于 0 至 1")
    rows: list[dict[str, float | str]] = []
    for error in errors_pp:
        estimate = float(initial_soc) + float(error) / 100.0
        if 0.0 < estimate < 1.0:
            rows.append(
                {
                    "requested_error_pp": float(error),
                    "initial_reference_soc": float(initial_soc),
                    "initial_estimated_soc": float(estimate),
                    "status": "EXECUTABLE",
                }
            )
        else:
            rows.append(
                {
                    "requested_error_pp": float(error),
                    "initial_reference_soc": float(initial_soc),
                    "initial_estimated_soc": None,
                    "status": "NOT_EXECUTABLE",
                    "reason": "initial estimated SOC outside (0, 1)",
                }
            )
    return rows
