"""参数灵敏度分析：电压对参数的归一化灵敏度与局部可辨识性。"""

from __future__ import annotations

from typing import Any, Callable, Mapping

import numpy as np
import pandas as pd


class SensitivityError(ValueError):
    """灵敏度输入非法。"""


def normalized_sensitivity(
    predict: Callable[[Mapping[str, float]], np.ndarray],
    parameters: Mapping[str, float],
    *,
    relative_step: float = 0.01,
    names: list[str] | None = None,
) -> pd.DataFrame:
    """计算 dV/dln(p) 的 RMS，反映参数变化对电压预测的影响。

    ``predict`` 接收参数映射并返回与测量等长的预测电压数组。
    """
    base = predict(parameters)
    if not np.isfinite(base).all():
        raise SensitivityError("基准预测包含非有限数值")
    selected = names or list(parameters.keys())
    rows: list[dict[str, Any]] = []
    for name in selected:
        value = float(parameters[name])
        if value <= 0:
            continue
        step = max(1e-6, relative_step)
        perturbed = dict(parameters)
        perturbed[name] = value * (1.0 + step)
        shifted = predict(perturbed)
        delta = shifted - base
        if not np.isfinite(delta).all():
            rows.append({"parameter": name, "rms_sensitivity_v": None, "status": "INVALID"})
            continue
        rows.append(
            {
                "parameter": name,
                "relative_step": step,
                "rms_sensitivity_v": float(np.sqrt(np.mean(delta**2))),
                "max_abs_sensitivity_v": float(np.max(np.abs(delta))),
                "status": "IDENTIFIED",
            }
        )
    return pd.DataFrame(rows)


def parameter_correlation(jacobian: np.ndarray, names: list[str]) -> pd.DataFrame:
    matrix = np.asarray(jacobian, dtype=float)
    if matrix.ndim != 2 or matrix.shape[1] != len(names):
        raise SensitivityError("Jacobian 形状与参数名不一致")
    norms = np.linalg.norm(matrix, axis=0)
    norms[norms == 0] = 1.0
    correlation = np.corrcoef((matrix / norms).T)
    return pd.DataFrame(correlation, index=names, columns=names)


def identifiability_summary(
    sensitivity: pd.DataFrame,
    *,
    ratio_threshold: float = 10.0,
) -> dict[str, Any]:
    """灵敏度差异超过阈值时提示弱可辨识参数。"""
    valid = sensitivity.dropna(subset=["rms_sensitivity_v"])
    if valid.empty:
        return {"status": "NOT_VERIFIED", "weak_parameters": []}
    values = valid["rms_sensitivity_v"].to_numpy(dtype=float)
    strongest = float(values.max())
    weakest = float(values[valid["rms_sensitivity_v"] == values.min()]["rms_sensitivity_v"].iloc[0])
    ratio = strongest / weakest if weakest > 0 else float("inf")
    weak = list(valid.loc[valid["rms_sensitivity_v"] * ratio_threshold < strongest, "parameter"])
    return {
        "strongest_parameter": str(valid.loc[valid["rms_sensitivity_v"].idxmax(), "parameter"]),
        "strongest_rms_v": strongest,
        "weakest_rms_v": weakest,
        "ratio": ratio,
        "weak_parameters": weak,
        "status": "WEAKLY_IDENTIFIABLE" if weak else "IDENTIFIED",
    }
