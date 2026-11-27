"""长期运行时间与不一致性指标。"""

from __future__ import annotations

from typing import Any


def runtime_summary(result: dict[str, Any]) -> dict[str, Any]:
    records = result.get("records", [])
    if not records:
        return {
            "runtime_s": result.get("duration_s"),
            "status": result.get("status"),
            "sample_count": 0,
        }
    currents = [item["battery_current_a"] for item in records]
    voltages = [item["battery_terminal_voltage_v"] for item in records]
    cells = [item["minimum_cell_voltage_v"] for item in records]
    return {
        "runtime_s": result["duration_s"],
        "runtime_h": result["duration_s"] / 3600.0,
        "status": result.get("status"),
        "sample_count": len(records),
        "mean_current_a": sum(currents) / len(currents),
        "max_current_a": max(currents),
        "min_battery_voltage_v": min(voltages),
        "min_cell_voltage_v": min(cells),
        "initial_socs": result.get("initial_socs"),
        "final_socs": result.get("final_socs"),
        "energy": result.get("energy"),
        "soc_window_warning": result.get("soc_window_warning"),
        "protection_time_resolution_s": result.get("protection_time_resolution_s"),
    }


def first_limiting_cell(cell_voltages: list[float], cell_ids: list[str]) -> dict[str, Any]:
    index = min(range(len(cell_voltages)), key=lambda position: cell_voltages[position])
    return {
        "cell_id": cell_ids[index],
        "voltage_v": cell_voltages[index],
        "index": index,
    }


def inconsistency_metrics(final_socs: list[float], capacities_ah: list[float]) -> dict[str, Any]:
    if len(final_socs) != len(capacities_ah):
        raise ValueError("SOC 与容量数量不一致")
    remaining_ah = [soc * capacity for soc, capacity in zip(final_socs, capacities_ah)]
    spread = max(final_socs) - min(final_socs)
    return {
        "final_soc_spread": spread,
        "remaining_charge_ah": remaining_ah,
        "unused_charge_ah": sum(remaining_ah) - min(remaining_ah) * len(remaining_ah),
        "note": "未使用电荷按各节比例估算，不代表实际可转移电量",
    }


__all__ = ["first_limiting_cell", "inconsistency_metrics", "runtime_summary"]
