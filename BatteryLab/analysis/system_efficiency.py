"""效率与损耗对比。"""

from __future__ import annotations

from typing import Any

from validation.system_result_judge import judge


def efficiency_from_metrics(metrics: dict[str, Any]) -> float | None:
    pin = metrics.get("input_power_w")
    pout = metrics.get("output_power_w")
    if not pin or pin <= 0 or pout is None:
        return None
    return float(pout) / float(pin) * 100.0


def compare_baseline_candidate(historical: dict[str, Any]) -> dict[str, Any]:
    """从 PowerLab 历史真实 Run 汇总中提取基准/候选并重算效率差。"""

    def pick(entry: dict[str, Any] | None) -> dict[str, Any] | None:
        if not entry:
            return None
        metrics = entry.get("metrics") or {}
        return {
            "name": entry.get("name"),
            "efficiency_percent": metrics.get("efficiency_percent"),
            "ripple_vpp": metrics.get("output_ripple_vpp"),
            "peak_current_a": metrics.get("inductor_peak_current_a"),
            "run_id": entry.get("run_id"),
            "values": entry.get("values"),
        }

    baseline = pick(historical.get("baseline"))
    candidates = [pick(item) for item in historical.get("candidates", [])]
    candidate = candidates[0] if candidates else None
    delta = None
    if baseline and candidate and baseline["efficiency_percent"] is not None and candidate["efficiency_percent"] is not None:
        delta = candidate["efficiency_percent"] - baseline["efficiency_percent"]
    return {
        "source": historical.get("source"),
        "baseline": baseline,
        "candidate": candidate,
        "efficiency_delta_percent": delta,
        "candidate_requires_revalidation": True,
        "note": "优化候选 LC 只来自历史 Run；必须在闭环下重新验证振铃、峰值电流与相位裕量",
    }


def efficiency_check(value: float | None, *, minimum: float | None = None, maximum: float | None = None) -> dict[str, Any]:
    result = judge("efficiency_percent", value, minimum=minimum, maximum=maximum, unit="%")
    return result.to_dict()


__all__ = ["compare_baseline_candidate", "efficiency_check", "efficiency_from_metrics"]
