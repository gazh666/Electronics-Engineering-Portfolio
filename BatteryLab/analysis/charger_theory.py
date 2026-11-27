"""Buck 充电功率级理论设计：占空比、电感纹波、峰值/谷值与电容纹波。

公式适用于连续导通（CCM）与适当负载近似。连接低阻抗电池后，实际纹波与动态
必须由真实开关级仿真确定；DCM 条件下本模块只用于识别模型适用性。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence


@dataclass(frozen=True)
class BuckDesignResult:
    duty: float
    inductor_ripple_a: float
    inductor_peak_a: float
    inductor_valley_a: float
    capacitor_ripple_v: float
    esr_ripple_v: float
    conduction_mode_estimate: str
    boundary_current_a: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "duty": self.duty,
            "inductor_ripple_a": self.inductor_ripple_a,
            "inductor_peak_a": self.inductor_peak_a,
            "inductor_valley_a": self.inductor_valley_a,
            "capacitor_ripple_v": self.capacitor_ripple_v,
            "esr_ripple_v": self.esr_ripple_v,
            "conduction_mode_estimate": self.conduction_mode_estimate,
            "boundary_current_a": self.boundary_current_a,
        }


def calculate_buck_design(
    vin_v: float,
    vout_v: float,
    output_current_a: float,
    inductance_h: float,
    capacitance_f: float,
    switching_frequency_hz: float,
    capacitor_esr_ohm: float,
) -> BuckDesignResult:
    values = [
        vin_v,
        vout_v,
        output_current_a,
        inductance_h,
        capacitance_f,
        switching_frequency_hz,
        capacitor_esr_ohm,
    ]
    if not all(math.isfinite(v) for v in values):
        raise ValueError("Non-finite parameter")
    if not 0 < vout_v < vin_v:
        raise ValueError("Invalid buck voltage")
    if min(inductance_h, capacitance_f, switching_frequency_hz) <= 0:
        raise ValueError("Invalid LC or frequency")
    if output_current_a < 0:
        raise ValueError("Invalid output current")
    if capacitor_esr_ohm < 0:
        raise ValueError("Invalid ESR")

    duty = vout_v / vin_v
    ripple = (vin_v - vout_v) * duty / (inductance_h * switching_frequency_hz)
    peak = output_current_a + ripple / 2
    valley = output_current_a - ripple / 2
    capacitor_ripple = ripple / (8 * switching_frequency_hz * capacitance_f)
    esr_ripple = ripple * capacitor_esr_ohm
    mode = "CCM_ESTIMATE" if valley > 0 else "DCM_OR_BOUNDARY"

    return BuckDesignResult(
        duty=duty,
        inductor_ripple_a=ripple,
        inductor_peak_a=peak,
        inductor_valley_a=valley,
        capacitor_ripple_v=capacitor_ripple,
        esr_ripple_v=esr_ripple,
        conduction_mode_estimate=mode,
        boundary_current_a=ripple / 2,
    )


def sweep_buck_designs(
    vin_v: float,
    output_voltages_v: Sequence[float],
    output_currents_a: Sequence[float],
    inductances_h: Sequence[float],
    capacitances_f: Sequence[float],
    switching_frequency_hz: float,
    capacitor_esr_ohm: float,
) -> list[dict[str, Any]]:
    """执行 Task 5 要求的设计矩阵，返回带输入参数的扁平行。"""
    rows: list[dict[str, Any]] = []
    for vout in output_voltages_v:
        for current in output_currents_a:
            for inductance in inductances_h:
                for capacitance in capacitances_f:
                    result = calculate_buck_design(
                        vin_v,
                        float(vout),
                        float(current),
                        float(inductance),
                        float(capacitance),
                        switching_frequency_hz,
                        capacitor_esr_ohm,
                    )
                    row = {
                        "vin_v": float(vin_v),
                        "vout_v": float(vout),
                        "output_current_a": float(current),
                        "inductance_h": float(inductance),
                        "capacitance_f": float(capacitance),
                    }
                    row.update(result.to_dict())
                    rows.append(row)
    return rows
