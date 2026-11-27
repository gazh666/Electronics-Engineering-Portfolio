"""长时充电包络：3S ECM + 准静态 CC-CV + 第五阶段真实保护联锁。

为什么不把 73 Hz 电压环直接放进秒级长时仿真：
开关级 PI 的带宽约 73–95 Hz，用 0.5–1 s 的步长离散会直接失稳；长时模型因此采用
**准静态恒压策略**：

```text
I_cv = (V_target - OCV_pack - Vp_pack) / R0_pack,  0 <= I_cv <= I_cc
```

这与网表内 PI 的物理目标一致（把端电压调节到目标），但动态过程不同：
网表 PI 有软启动、抗饱和与开关纹波，长时模型把这些视为已由前级验证的快速内环。
两者不得互相替代，文档与结果元数据必须标注层次。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

from battery_models.battery_pack import SeriesBatteryPack
from charging.battery_adapter import (
    build_series_pack,
    load_identified_battery_bundle,
    soc_validity,
    to_ecm_current,
)
from charging.charge_termination import TerminationTracker
from charging.protection_adapter import create_protection_controller
from analysis.charging_energy import integrate_zoh
from analysis.cc_cv_transition import detect_cc_to_cv_transition

DEFAULT_MODEL_ID = "calce_sp2_25c_inr18650_20r_first_order_v1"


class LongChargeError(ValueError):
    """长时充电输入非法。"""


@dataclass(frozen=True)
class LongChargeParameters:
    initial_socs: tuple[float, ...]
    current_limit_a: float
    voltage_target_v: float
    termination_current_a: float
    termination_hold_s: float
    maximum_charge_time_s: float
    step_s: float = 0.5
    temperature_c: float = 25.0
    voltage_regulation_enabled: bool = True
    model_id: str = DEFAULT_MODEL_ID
    capacities_ah: tuple[float, ...] | None = None
    r0_ohm: tuple[float, ...] | None = None

    def validate(self) -> "LongChargeParameters":
        if len(self.initial_socs) < 1:
            raise LongChargeError("至少需要一节电芯")
        for soc in self.initial_socs:
            if not 0.0 < float(soc) < 1.0:
                raise LongChargeError("初始 SOC 必须位于 (0, 1)")
        for name in (
            "current_limit_a",
            "voltage_target_v",
            "termination_current_a",
            "termination_hold_s",
            "maximum_charge_time_s",
            "step_s",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0.0:
                raise LongChargeError(f"{name} 必须为正")
        if self.termination_current_a >= self.current_limit_a:
            raise LongChargeError("终止电流必须低于恒流限值")
        if self.step_s > 2.0:
            raise LongChargeError("长时步长过大，无法分辨 18 s 极化时间常数")
        if self.capacities_ah is not None and len(self.capacities_ah) != len(self.initial_socs):
            raise LongChargeError("容量列表长度不一致")
        if self.r0_ohm is not None and len(self.r0_ohm) != len(self.initial_socs):
            raise LongChargeError("内阻列表长度不一致")
        return self

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass
class LongChargeResult:
    time_s: np.ndarray
    pack_voltage_v: np.ndarray
    charging_current_a: np.ndarray
    cell_voltages_v: np.ndarray
    soc: np.ndarray
    state: str
    termination_reason: str
    events: list[dict[str, Any]]
    summary: dict[str, Any]

    def to_columns(self) -> dict[str, np.ndarray]:
        payload = {
            "time_s": self.time_s,
            "battery_pack_voltage_v": self.pack_voltage_v,
            "charging_current_a": self.charging_current_a,
            "mean_soc": self.soc.mean(axis=1),
        }
        for index in range(self.cell_voltages_v.shape[1]):
            payload[f"cell{index + 1}_voltage_v"] = self.cell_voltages_v[:, index]
            payload[f"cell{index + 1}_soc"] = self.soc[:, index]
        return payload


def _pack(bundle: dict[str, Any], parameters: LongChargeParameters) -> SeriesBatteryPack:
    return build_series_pack(
        bundle,
        parameters.initial_socs,
        capacities_ah=parameters.capacities_ah,
        r0_ohm=parameters.r0_ohm,
    )


def quasi_static_current_a(
    pack: SeriesBatteryPack,
    parameters: LongChargeParameters,
) -> float:
    """准静态 CC-CV 电流：先限流，再按端电压目标回算。"""
    ocv_pack = float(sum(cell.ocv_v() for cell in pack.cells))
    polarization = float(sum(sum(cell.state.polarization_voltages_v) for cell in pack.cells))
    resistance = float(sum(cell.parameters.r0_ohm for cell in pack.cells))
    if not parameters.voltage_regulation_enabled:
        return float(parameters.current_limit_a)
    desired = (parameters.voltage_target_v - ocv_pack - polarization) / resistance
    return float(min(max(desired, 0.0), parameters.current_limit_a))


def simulate_long_charge(
    parameters: LongChargeParameters,
    *,
    collect_cells: bool = True,
) -> LongChargeResult:
    parameters.validate()
    bundle = load_identified_battery_bundle(parameters.model_id)
    pack = _pack(bundle, parameters)
    cell_count = len(pack.cells)
    protection = create_protection_controller([f"cell{index + 1}" for index in range(cell_count)])
    protection.arm(0.0)
    termination = TerminationTracker(
        current_limit_a=parameters.termination_current_a,
        hold_time_s=parameters.termination_hold_s,
    )

    times: list[float] = []
    pack_voltages: list[float] = []
    currents: list[float] = []
    cell_voltages: list[list[float]] = []
    socs: list[list[float]] = []
    events: list[dict[str, Any]] = []
    energy_battery_j = 0.0
    energy_ocv_j = 0.0
    energy_ohmic_j = 0.0
    energy_polarization_j = 0.0
    stored_energy_initial_j = float(sum(cell.stored_energy_j() for cell in pack.cells))
    charge_ah = 0.0

    state = "CC"
    termination_reason = "MAXIMUM_CHARGE_TIME"
    total_steps = int(math.ceil(parameters.maximum_charge_time_s / parameters.step_s))
    first_cv_time: float | None = None

    for index in range(total_steps + 1):
        elapsed = index * parameters.step_s
        current = quasi_static_current_a(pack, parameters)
        pack_voltage = float(pack.pack_voltage(to_ecm_current(current)))
        voltages = tuple(float(value) for value in pack.cell_voltages(to_ecm_current(current)))

        times.append(elapsed)
        pack_voltages.append(pack_voltage)
        currents.append(current)
        cell_voltages.append(list(voltages))
        socs.append(list(pack.socs))

        if index == total_steps:
            termination_reason = "MAXIMUM_CHARGE_TIME"
            state = "TIMEOUT"
            events.append({"time_s": elapsed, "event": "TIMEOUT"})
            break

        snapshot = protection.update(
            elapsed,
            voltages,
            -current,
            parameters.temperature_c,
        )
        if not snapshot.charge_allowed:
            state = "FAULT"
            termination_reason = snapshot.latched_faults[0] if snapshot.latched_faults else snapshot.active_faults[0] if snapshot.active_faults else "BMS_CHARGE_INHIBITED"
            events.append(
                {
                    "time_s": elapsed,
                    "event": "FAULT",
                    "reason": termination_reason,
                    "pack_voltage_v": pack_voltage,
                    "max_cell_voltage_v": float(max(voltages)),
                }
            )
            break

        near_target = abs(pack_voltage - parameters.voltage_target_v) <= 0.02
        if parameters.voltage_regulation_enabled and near_target and current < parameters.current_limit_a * 0.999:
            if first_cv_time is None:
                first_cv_time = elapsed
                events.append({"time_s": elapsed, "event": "ENTER_CV", "current_a": current})
            state = "CV"
        else:
            state = "CC"

        if termination.update(elapsed, current, near_target) and state == "CV":
            state = "COMPLETE"
            termination_reason = "TERMINATION_CURRENT"
            events.append(
                {
                    "time_s": elapsed,
                    "event": "COMPLETE",
                    "current_a": current,
                    "held_s": termination.held_time_s,
                }
            )
            break

        if min(pack.socs) >= 0.999:
            state = "COMPLETE"
            termination_reason = "SOC_UPPER_LIMIT"
            events.append({"time_s": elapsed, "event": "SOC_UPPER_LIMIT"})
            break

        dt = parameters.step_s
        energy_battery_j += pack_voltage * current * dt
        energy_ocv_j += float(sum(cell.ocv_v() for cell in pack.cells)) * current * dt
        energy_ohmic_j += current**2 * float(sum(cell.parameters.r0_ohm for cell in pack.cells)) * dt
        energy_polarization_j += float(
            sum(cell.polarization_loss_w() for cell in pack.cells)
        ) * dt
        charge_ah += current * dt / 3600.0
        pack.step(to_ecm_current(current), dt)

    time_array = np.asarray(times, dtype=float)
    pack_array = np.asarray(pack_voltages, dtype=float)
    current_array = np.asarray(currents, dtype=float)
    cell_array = np.asarray(cell_voltages, dtype=float)
    soc_array = np.asarray(socs, dtype=float)

    transition = detect_cc_to_cv_transition(
        time_array, pack_array, parameters.voltage_target_v, 0.02, hold_time_s=parameters.step_s
    )
    soc_min = float(bundle["identified_soc_min"])
    soc_max = float(bundle["identified_soc_max"])
    capacity_throughput = charge_ah
    stored_energy_final_j = float(sum(cell.stored_energy_j() for cell in pack.cells))
    stored_delta_j = stored_energy_final_j - stored_energy_initial_j
    soc_consistency = float(
        abs(capacity_throughput - float(np.mean(soc_array[-1]) - np.mean(soc_array[0])) * float(np.mean([cell.parameters.capacity_ah for cell in pack.cells])))
    )
    summary = {
        "method": "ecm_charge_envelope",
        "model_id": bundle["model_id"],
        "controller": "quasi_static_cc_cv",
        "voltage_regulation_enabled": parameters.voltage_regulation_enabled,
        "initial_socs": list(parameters.initial_socs),
        "final_socs": [float(value) for value in soc_array[-1]],
        "final_soc_spread": float(soc_array[-1].max() - soc_array[-1].min()),
        "final_soc_mean": float(soc_array[-1].mean()),
        "soc_validity": [
            soc_validity(float(value), soc_min, soc_max) for value in soc_array[-1]
        ],
        "identified_soc_range": [soc_min, soc_max],
        "final_pack_voltage_v": float(pack_array[-1]),
        "final_charging_current_a": float(current_array[-1]),
        "charge_ah": float(capacity_throughput),
        "cc_to_cv_time_s": transition,
        "first_cv_event_s": first_cv_time,
        "final_max_cell_voltage_v": float(cell_array[-1].max()),
        "final_min_cell_voltage_v": float(cell_array[-1].min()),
        "max_cell_voltage_v": float(cell_array.max()),
        "max_cell_voltage_time_s": float(time_array[int(np.argmax(cell_array.max(axis=1)))]),
        "max_cell_voltage_at_pack_v": float(
            pack_array[int(np.argmax(cell_array.max(axis=1)))]
        ),
        "energy": {
            "battery_energy_wh": energy_battery_j / 3600.0,
            "ocv_energy_wh": energy_ocv_j / 3600.0,
            "ohmic_loss_wh": energy_ohmic_j / 3600.0,
            "polarization_loss_wh": energy_polarization_j / 3600.0,
            "stored_energy_change_wh": stored_delta_j / 3600.0,
            "closure_residual_fraction": (
                (energy_battery_j - energy_ocv_j - energy_ohmic_j - energy_polarization_j - stored_delta_j)
                / energy_battery_j
                if energy_battery_j > 0.0
                else None
            ),
        },
        "soc_consistency_ah": soc_consistency,
        "protection": {
            "charge_allowed": bool(protection.history[-1].charge_allowed) if protection.history else None,
            "latched_faults": list(protection.history[-1].latched_faults) if protection.history else [],
            "updates": len(protection.history),
        },
        "termination_reason": termination_reason,
        "state": state,
        "duration_s": float(time_array[-1]),
        "events": events,
    }
    if not collect_cells:
        summary.pop("final_socs", None)
    return LongChargeResult(
        time_s=time_array,
        pack_voltage_v=pack_array,
        charging_current_a=current_array,
        cell_voltages_v=cell_array,
        soc=soc_array,
        state=state,
        termination_reason=termination_reason,
        events=events,
        summary=summary,
    )


def simulate_termination_interruption(
    *,
    low_current_a: float = 0.05,
    hold_s: float = 60.0,
    dip_s: float = 30.0,
    step_s: float = 1.0,
) -> dict[str, Any]:
    """C15：低电流持续时间不足保持时间，随后恢复大电流，不得误判 COMPLETE。"""
    termination = TerminationTracker(current_limit_a=0.1, hold_time_s=hold_s)
    time = 0.0
    completed_during_dip = False
    for _ in range(int(dip_s / step_s)):
        time += step_s
        if termination.update(time, low_current_a, True):
            completed_during_dip = True
            break
    dip_end_held_s = termination.held_time_s
    time += step_s
    termination.update(time, 0.5, True)
    held_after_recovery = termination.held_time_s
    completed_after_recovery = False
    for _ in range(int(dip_s / step_s)):
        time += step_s
        if termination.update(time, low_current_a, True):
            completed_after_recovery = True
            break
    return {
        "case": "C15",
        "completed_during_short_dip": completed_during_dip,
        "held_time_before_recovery_s": dip_end_held_s,
        "held_time_after_recovery_s": held_after_recovery,
        "completed_after_second_dip": completed_after_recovery,
        "status": "PASS"
        if not completed_during_dip and held_after_recovery == 0.0 and not completed_after_recovery
        else "FAIL",
    }


def temperature_gate_test(temperature_c: float = 50.0) -> dict[str, Any]:
    """C12：通过真实保护控制器验证温度越界撤销充电许可。"""
    controller = create_protection_controller(("cell1", "cell2", "cell3"))
    snapshot = None
    for step in range(1, 400):
        snapshot = controller.update(step * 0.01, (3.9, 3.9, 3.9), -0.5, temperature_c)
    return {
        "case": "C12",
        "temperature_c": temperature_c,
        "charge_allowed": bool(snapshot.charge_allowed),
        "active_faults": list(snapshot.active_faults),
        "latched_faults": list(snapshot.latched_faults),
        "status": "PASS" if snapshot is not None and not snapshot.charge_allowed else "FAIL",
    }


def measurement_invalid_test() -> dict[str, Any]:
    """C13：测量失效时不得允许充电。"""
    controller = create_protection_controller(("cell1", "cell2", "cell3"))
    snapshot = controller.update(0.0, (float("nan"), 3.9, 3.9), -0.5, 25.0, measurement_valid=True)
    return {
        "case": "C13",
        "measurement_valid": bool(snapshot.measurement_valid),
        "charge_allowed": bool(snapshot.charge_allowed),
        "active_faults": list(snapshot.active_faults),
        "status": "PASS" if not snapshot.charge_allowed and not snapshot.measurement_valid else "FAIL",
    }


def latched_restart_test() -> dict[str, Any]:
    """C17：保护锁存后不允许自动重启。"""
    controller = create_protection_controller(("cell1", "cell2", "cell3"))
    for step in range(1, 40):
        snapshot = controller.update(step * 0.01, (4.30, 3.95, 3.94), 0.0, 25.0)
    latched = snapshot
    for step in range(40, 600):
        snapshot = controller.update(step * 0.01, (4.10, 3.95, 3.94), 0.0, 25.0)
    return {
        "case": "C17",
        "latched_faults_at_trip": list(latched.latched_faults),
        "charge_allowed_after_recovery_window": bool(snapshot.charge_allowed),
        "automatic_restart": bool(snapshot.charge_allowed),
        "status": "PASS" if latched.latched_faults and not snapshot.charge_allowed else "FAIL",
    }
