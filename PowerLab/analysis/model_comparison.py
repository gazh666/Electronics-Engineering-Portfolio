"""五种对照模型的统一汇总与差异对比。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd

from circuits.validators import finite_number

from .power_metrics import PowerAccounting, time_average
from .device_stress import DeviceStress


@dataclass(frozen=True)
class ModelSummary:
    """单个模型在稳态窗口内的关键指标。"""

    variant: str
    label: str
    steady_state_achieved: bool
    steady_state_start_s: float
    steady_state_end_s: float
    output_voltage_mean_v: float
    output_voltage_ripple_v: float
    inductor_current_mean_a: float
    inductor_current_ripple_a: float
    input_power_w: float
    driver_power_w: float
    output_power_w: float
    mosfet_loss_w: float
    diode_loss_w: float
    dcr_loss_w: float
    esr_loss_w: float
    gate_loss_w: float
    total_loss_w: float
    residual_w: float
    efficiency_power_stage_percent: float | None
    efficiency_system_percent: float | None
    vds_max_v: float
    drain_current_peak_a: float
    diode_current_peak_a: float
    gate_voltage_max_v: float
    sample_count: int
    data_source: str = "spice_simulation"

    def to_dict(self) -> dict[str, Any]:
        return {
            "variant": self.variant,
            "label": self.label,
            "steady_state_achieved": self.steady_state_achieved,
            "steady_state_start_s": self.steady_state_start_s,
            "steady_state_end_s": self.steady_state_end_s,
            "output_voltage_mean_v": self.output_voltage_mean_v,
            "output_voltage_ripple_v": self.output_voltage_ripple_v,
            "output_voltage_ripple_mv": self.output_voltage_ripple_v * 1e3,
            "inductor_current_mean_a": self.inductor_current_mean_a,
            "inductor_current_ripple_a": self.inductor_current_ripple_a,
            "input_power_w": self.input_power_w,
            "driver_power_w": self.driver_power_w,
            "output_power_w": self.output_power_w,
            "mosfet_loss_w": self.mosfet_loss_w,
            "diode_loss_w": self.diode_loss_w,
            "dcr_loss_w": self.dcr_loss_w,
            "esr_loss_w": self.esr_loss_w,
            "gate_loss_w": self.gate_loss_w,
            "total_loss_w": self.total_loss_w,
            "residual_w": self.residual_w,
            "efficiency_power_stage_percent": self.efficiency_power_stage_percent,
            "efficiency_system_percent": self.efficiency_system_percent,
            "vds_max_v": self.vds_max_v,
            "drain_current_peak_a": self.drain_current_peak_a,
            "diode_current_peak_a": self.diode_current_peak_a,
            "gate_voltage_max_v": self.gate_voltage_max_v,
            "sample_count": self.sample_count,
            "data_source": self.data_source,
        }


def summarize_model(
    *,
    variant: str,
    label: str,
    frame: pd.DataFrame,
    accounting: PowerAccounting,
    stress: DeviceStress,
    steady_state_achieved: bool,
    steady_state_start_s: float,
    steady_state_end_s: float,
    sample_count: int,
) -> ModelSummary:
    """把单个模型的稳态窗口结果压缩成一行指标。"""
    if not isinstance(frame, pd.DataFrame):
        raise ValueError("frame must be a pandas.DataFrame")
    for name in (
        "time_s",
        "vout_v",
        "inductor_current_a",
        "mosfet_vds_v",
        "mosfet_drain_terminal_current_a",
        "diode_current_a",
        "mosfet_vgs_v",
    ):
        if name not in frame.columns:
            raise ValueError(f"frame missing column: {name}")

    time = frame["time_s"].to_numpy(dtype=float)
    vout = frame["vout_v"].to_numpy(dtype=float)
    il = frame["inductor_current_a"].to_numpy(dtype=float)

    vout_mean = time_average(time, vout)
    il_mean = time_average(time, il)

    return ModelSummary(
        variant=str(variant),
        label=str(label),
        steady_state_achieved=bool(steady_state_achieved),
        steady_state_start_s=float(steady_state_start_s),
        steady_state_end_s=float(steady_state_end_s),
        output_voltage_mean_v=float(vout_mean),
        output_voltage_ripple_v=float(np.max(vout) - np.min(vout)),
        inductor_current_mean_a=float(il_mean),
        inductor_current_ripple_a=float(np.max(il) - np.min(il)),
        input_power_w=accounting.input_average_power_w,
        driver_power_w=accounting.driver_average_power_w,
        output_power_w=accounting.output_average_power_w,
        mosfet_loss_w=accounting.mosfet_network_average_power_w,
        diode_loss_w=accounting.diode_average_power_w,
        dcr_loss_w=accounting.dcr_loss_w,
        esr_loss_w=accounting.esr_loss_w,
        gate_loss_w=accounting.gate_resistor_loss_w + accounting.pulldown_loss_w,
        total_loss_w=accounting.total_loss_w,
        residual_w=accounting.residual_w,
        efficiency_power_stage_percent=accounting.efficiency_power_stage_percent,
        efficiency_system_percent=accounting.efficiency_system_percent,
        vds_max_v=stress.mosfet_vds_max_v,
        drain_current_peak_a=stress.drain_current_peak_a,
        diode_current_peak_a=stress.diode_forward_current_peak_a,
        gate_voltage_max_v=stress.gate_source_voltage_max_v,
        sample_count=int(sample_count),
    )


def compare_models(
    summaries: Iterable[ModelSummary],
    *,
    reference: str = "A",
) -> pd.DataFrame:
    """生成模型对照表，并给出相对参考模型的差值。"""
    items = list(summaries)
    if not items:
        raise ValueError("summaries must not be empty")
    variants = [item.variant for item in items]
    if len(set(variants)) != len(variants):
        raise ValueError("duplicate variant in summaries")
    reference_item = next((item for item in items if item.variant == reference), None)
    if reference_item is None:
        raise ValueError(f"reference model {reference!r} not found in summaries")

    rows: list[dict[str, Any]] = []
    for item in items:
        efficiency = item.efficiency_power_stage_percent
        reference_efficiency = reference_item.efficiency_power_stage_percent
        rows.append(
            {
                **item.to_dict(),
                "delta_output_voltage_mv_vs_reference": (
                    item.output_voltage_mean_v - reference_item.output_voltage_mean_v
                )
                * 1e3,
                "delta_total_loss_mw_vs_reference": (
                    item.total_loss_w - reference_item.total_loss_w
                )
                * 1e3,
                "delta_efficiency_pp_vs_reference": (
                    None
                    if efficiency is None or reference_efficiency is None
                    else efficiency - reference_efficiency
                ),
                "output_voltage_change_percent_vs_reference": _percent_change(
                    item.output_voltage_mean_v, reference_item.output_voltage_mean_v
                ),
                "total_loss_change_percent_vs_reference": _percent_change(
                    item.total_loss_w, reference_item.total_loss_w
                ),
            }
        )
    return pd.DataFrame(rows)


def _percent_change(value: float, reference: float) -> float | None:
    if reference == 0:
        return None
    return 100.0 * (value - reference) / abs(reference)


def dominant_loss(summary: ModelSummary) -> str:
    """返回该模型占比最大的损耗项名称。"""
    if not isinstance(summary, ModelSummary):
        raise ValueError("summary must be ModelSummary")
    items = {
        "mosfet_network": summary.mosfet_loss_w,
        "diode": summary.diode_loss_w,
        "inductor_dcr": summary.dcr_loss_w,
        "capacitor_esr": summary.esr_loss_w,
        "gate_network": summary.gate_loss_w,
    }
    return max(items, key=items.get)


def difference_notes(summaries: Iterable[ModelSummary]) -> list[str]:
    """生成可供文档引用的模型差异说明（纯数值，不含结论性夸大）。"""
    items = {item.variant: item for item in summaries}
    notes: list[str] = []
    if "A" in items and "B" in items:
        delta = items["B"].total_loss_w - items["A"].total_loss_w
        notes.append(
            f"Model B minus Model A total loss = {delta * 1e3:.3f} mW "
            "(added inductor DCR and capacitor ESR)."
        )
    if "B" in items and "C" in items:
        delta = items["C"].total_loss_w - items["B"].total_loss_w
        notes.append(
            f"Model C minus Model B total loss = {delta * 1e3:.3f} mW "
            "(replaced the ideal teaching diode with the nonideal diode)."
        )
    if "C" in items and "D" in items:
        delta = items["D"].total_loss_w - items["C"].total_loss_w
        notes.append(
            f"Model D minus Model C total loss = {delta * 1e3:.3f} mW "
            "(replaced the voltage-controlled switch with a Level 1 NMOS and floating drive)."
        )
    if "D" in items and "E" in items:
        delta = items["E"].total_loss_w - items["D"].total_loss_w
        notes.append(
            f"Model E minus Model D total loss = {delta * 1e3:.3f} mW "
            "(added external Cgs/Cgd/Cds)."
        )
    return notes


def loss_share_table(summaries: Iterable[ModelSummary]) -> pd.DataFrame:
    """各模型损耗占比表（分母为该模型总损耗）。"""
    rows: list[dict[str, Any]] = []
    for item in summaries:
        total = item.total_loss_w
        if total <= 0:
            share = {key: None for key in ("mosfet", "diode", "dcr", "esr", "gate")}
        else:
            share = {
                "mosfet": item.mosfet_loss_w / total,
                "diode": item.diode_loss_w / total,
                "dcr": item.dcr_loss_w / total,
                "esr": item.esr_loss_w / total,
                "gate": item.gate_loss_w / total,
            }
        rows.append({"variant": item.variant, "total_loss_w": total, **share})
    return pd.DataFrame(rows)


def output_voltage_regulation(summary: ModelSummary, target_v: float) -> dict[str, float]:
    """相对目标输出电压的偏差（不修改数据以凑 5 V）。"""
    target = finite_number(target_v, "target_v")
    if target <= 0:
        raise ValueError("target_v must be positive")
    return {
        "target_v": target,
        "measured_v": summary.output_voltage_mean_v,
        "absolute_error_v": summary.output_voltage_mean_v - target,
        "relative_error_percent": 100.0
        * (summary.output_voltage_mean_v - target)
        / target,
    }
