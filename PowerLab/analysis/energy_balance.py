"""能量平衡核算。

稳态窗口内（忽略电感、电容储能变化）：

    E_in + E_drv = E_out + E_mosfet + E_diode + E_dcr + E_esr + E_RG + E_RGS + E_residual

残差不是被"塞给"某个器件，而是作为独立字段保留并参与数据质量判定。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from circuits.validators import finite_number, positive_number

from .power_metrics import PowerAccounting


@dataclass(frozen=True)
class EnergyBalance:
    """一段窗口内的能量平衡结果（焦耳）。"""

    window_start_s: float
    window_end_s: float
    duration_s: float
    input_energy_j: float
    driver_energy_j: float
    output_energy_j: float
    mosfet_energy_j: float
    diode_energy_j: float
    dcr_energy_j: float
    esr_energy_j: float
    gate_resistor_energy_j: float
    pulldown_energy_j: float
    loss_energy_j: float
    residual_energy_j: float
    residual_ratio: float
    status: str
    data_source: str = "spice_simulation"

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_start_s": self.window_start_s,
            "window_end_s": self.window_end_s,
            "duration_s": self.duration_s,
            "input_energy_j": self.input_energy_j,
            "driver_energy_j": self.driver_energy_j,
            "output_energy_j": self.output_energy_j,
            "mosfet_energy_j": self.mosfet_energy_j,
            "diode_energy_j": self.diode_energy_j,
            "dcr_energy_j": self.dcr_energy_j,
            "esr_energy_j": self.esr_energy_j,
            "gate_resistor_energy_j": self.gate_resistor_energy_j,
            "pulldown_energy_j": self.pulldown_energy_j,
            "loss_energy_j": self.loss_energy_j,
            "residual_energy_j": self.residual_energy_j,
            "residual_ratio": self.residual_ratio,
            "status": self.status,
            "method": "average_power_times_window_duration",
            "data_source": self.data_source,
        }


def energy_balance(
    accounting: PowerAccounting,
    *,
    warning_ratio: float = 0.05,
    failure_ratio: float = 0.20,
) -> EnergyBalance:
    """由功率核算结果构造能量平衡。"""
    if not isinstance(accounting, PowerAccounting):
        raise ValueError("accounting must be PowerAccounting")
    warning = positive_number(warning_ratio, "warning_ratio")
    failure = positive_number(failure_ratio, "failure_ratio")
    if warning >= failure:
        raise ValueError("warning_ratio must be smaller than failure_ratio")
    duration = positive_number(accounting.duration_s, "duration_s")

    input_energy = accounting.input_average_power_w * duration
    driver_energy = accounting.driver_average_power_w * duration
    output_energy = accounting.output_average_power_w * duration
    mosfet_energy = accounting.mosfet_network_average_power_w * duration
    diode_energy = accounting.diode_average_power_w * duration
    dcr_energy = accounting.dcr_loss_w * duration
    esr_energy = accounting.esr_loss_w * duration
    gate_energy = accounting.gate_resistor_loss_w * duration
    pulldown_energy = accounting.pulldown_loss_w * duration
    loss_energy = accounting.total_loss_w * duration
    residual = accounting.residual_w * duration

    supplied = input_energy + driver_energy
    ratio = 0.0 if supplied <= 0 else residual / supplied
    magnitude = abs(ratio)
    if magnitude <= warning:
        status = "ok"
    elif magnitude <= failure:
        status = "warning"
    else:
        status = "excessive"

    return EnergyBalance(
        window_start_s=accounting.window_start_s,
        window_end_s=accounting.window_end_s,
        duration_s=duration,
        input_energy_j=float(input_energy),
        driver_energy_j=float(driver_energy),
        output_energy_j=float(output_energy),
        mosfet_energy_j=float(mosfet_energy),
        diode_energy_j=float(diode_energy),
        dcr_energy_j=float(dcr_energy),
        esr_energy_j=float(esr_energy),
        gate_resistor_energy_j=float(gate_energy),
        pulldown_energy_j=float(pulldown_energy),
        loss_energy_j=float(loss_energy),
        residual_energy_j=float(residual),
        residual_ratio=float(ratio),
        status=status,
    )


def energy_balance_sum(accounting: PowerAccounting) -> EnergyBalance:
    """使用默认 5% / 20% 判据构造能量平衡。"""
    return energy_balance(accounting)


def check_energy_balance(balance: EnergyBalance, *, tolerance: float = 0.05) -> dict[str, Any]:
    """按相对残差给出通过/失败结论。"""
    if not isinstance(balance, EnergyBalance):
        raise ValueError("balance must be EnergyBalance")
    limit = positive_number(tolerance, "tolerance")
    passed = abs(balance.residual_ratio) <= limit
    return {
        "passed": bool(passed),
        "residual_ratio": balance.residual_ratio,
        "tolerance": limit,
        "status": balance.status,
        "explanation": (
            "residual is kept as an independent term; it is never assigned to a device"
        ),
    }


def residual_power(balance: EnergyBalance) -> float:
    """把能量残差换回平均功率，便于与功率表核对。"""
    if not isinstance(balance, EnergyBalance):
        raise ValueError("balance must be EnergyBalance")
    duration = positive_number(balance.duration_s, "duration_s")
    return finite_number(balance.residual_energy_j, "residual_energy_j") / duration
