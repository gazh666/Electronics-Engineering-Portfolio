"""第五阶段实验 3：故障状态机、锁存、独立充放电许可与合法恢复。

运行：conda run -n kaifa_battery python -m scripts.protection_state_machine_demo
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from protection.protection_controller import ProtectionController
from protection.state_machine import FaultCode
from scripts.stage5_common import (
    check_at_most,
    check_true,
    stage5_limits,
    summarize_checks,
)
from storage.result_store import RunDirectory, write_csv, write_json

CELL_IDS = ("cell1", "cell2", "cell3")


def _controller() -> ProtectionController:
    controller = ProtectionController.create(stage5_limits(), CELL_IDS)
    controller.arm(0.0)
    return controller


def _drive(
    controller: ProtectionController,
    *,
    duration_s: float,
    step_s: float,
    voltages: Callable[[float], Sequence[float]],
    current: Callable[[float], float] | float = 0.0,
    temperature: Callable[[float], float] | float = 25.0,
    valid: Callable[[float], bool] | bool = True,
    recovery_times: Sequence[float] = (),
    rearm_times: Sequence[float] = (),
) -> dict[str, Any]:
    snapshots = []
    steps = int(round(duration_s / step_s))
    for index in range(steps + 1):
        now = index * step_s
        for moment in recovery_times:
            if abs(now - moment) < 0.5 * step_s:
                controller.request_recovery(now)
        for moment in rearm_times:
            if abs(now - moment) < 0.5 * step_s and not controller.state_machine.latched:
                controller.arm(now)
        current_value = current(now) if callable(current) else float(current)
        temperature_value = temperature(now) if callable(temperature) else float(temperature)
        valid_value = valid(now) if callable(valid) else bool(valid)
        snap = controller.update(now, voltages(now), current_value, temperature_value, measurement_valid=valid_value)
        snapshots.append(snap)
    return {"snapshots": snapshots, "events": controller.state_machine.events}


def _first_latch(snapshots: Sequence[Any], code: str) -> float | None:
    for snap in snapshots:
        if code in snap.latched_faults:
            return snap.time_s
    return None


def _last(snapshots: Sequence[Any]):
    return snapshots[-1]


def run(root: Path | None = None) -> dict:
    limits = stage5_limits()
    run_dir = RunDirectory("protection", root=root)
    run_dir.write_metadata(
        {
            "stage": "stage5",
            "experiment": "fault_state_machine",
            "note": "状态机为离散事件模型，不是硬件实测",
        }
    )
    rows: list[dict[str, Any]] = []
    event_rows: list[dict[str, Any]] = []
    verdicts = []

    # 1) 过压：充电禁止、放电允许；恢复需要全部清零保持 5 s 并显式重新使能。
    ov = _controller()
    ov_run = _drive(
        ov,
        duration_s=6.2,
        step_s=0.002,
        voltages=lambda t: (4.30 if 0.1 <= t < 0.4 else 4.10, 4.0, 4.0),
        recovery_times=(0.60, 5.60),
        rearm_times=(5.70,),
    )
    ov_snaps = ov_run["snapshots"]
    ov_latch = _first_latch(ov_snaps, FaultCode.CELL_OVERVOLTAGE.value)
    at_latch = next((snap for snap in ov_snaps if snap.time_s >= (ov_latch or 0.0)), ov_snaps[0])
    before_recovery = next((snap for snap in ov_snaps if abs(snap.time_s - 5.0) < 0.003), ov_snaps[-1])
    after_recovery = next((snap for snap in ov_snaps if abs(snap.time_s - 5.66) < 0.003), ov_snaps[-1])
    after_rearm = _last(ov_snaps)
    verdicts.extend(
        [
            check_at_most("过压锁存延时", (ov_latch or 9.0) - 0.10, 0.20, "s"),
            check_true(
                "过压后充电禁止且放电允许",
                (not at_latch.charge_allowed) and at_latch.discharge_allowed,
                f"charge={at_latch.charge_allowed} discharge={at_latch.discharge_allowed}",
            ),
            check_true(
                "过压未清除时拒绝恢复",
                bool(before_recovery.latched_faults),
                f"latched={before_recovery.latched_faults}",
            ),
            check_true(
                "全部清零保持 5 s 后允许恢复但需重新使能",
                (not after_recovery.latched_faults)
                and (not after_recovery.charge_allowed)
                and (not after_recovery.discharge_allowed),
                f"latched={after_recovery.latched_faults}",
            ),
            check_true(
                "重新使能后恢复充放电",
                after_rearm.charge_allowed and after_rearm.discharge_allowed,
                f"charge={after_rearm.charge_allowed}",
            ),
        ]
    )
    rows.extend(snapshot.to_dict() | {"scenario": "OVERVOLTAGE"} for snapshot in ov_snaps)
    event_rows.extend({"scenario": "OVERVOLTAGE", **event} for event in ov_run["events"])

    # 2) 欠压：放电禁止、充电允许。
    uv = _controller()
    uv_run = _drive(
        uv,
        duration_s=0.35,
        step_s=0.002,
        voltages=lambda t: (4.0, 4.0, 2.70 if t >= 0.05 else 3.6),
    )
    uv_snaps = uv_run["snapshots"]
    uv_latch = _first_latch(uv_snaps, FaultCode.CELL_UNDERVOLTAGE.value)
    uv_latched = next((snap for snap in uv_snaps if FaultCode.CELL_UNDERVOLTAGE.value in snap.latched_faults), uv_snaps[-1])
    verdicts.extend(
        [
            check_at_most("欠压锁存延时", (uv_latch or 9.0) - 0.05, 0.15, "s"),
            check_true(
                "欠压后放电禁止且充电允许",
                (not uv_latched.discharge_allowed) and uv_latched.charge_allowed,
                f"charge={uv_latched.charge_allowed} discharge={uv_latched.discharge_allowed}",
            ),
        ]
    )
    rows.extend(snapshot.to_dict() | {"scenario": "UNDERVOLTAGE"} for snapshot in uv_snaps)
    event_rows.extend({"scenario": "UNDERVOLTAGE", **event} for event in uv_run["events"])

    # 3) 充电过流 2 A。
    coc = _controller()
    coc_run = _drive(
        coc,
        duration_s=0.8,
        step_s=0.002,
        voltages=lambda t: (3.9, 3.9, 3.9),
        current=-2.0,
    )
    coc_snaps = coc_run["snapshots"]
    coc_latch = _first_latch(coc_snaps, FaultCode.CHARGE_OVERCURRENT.value)
    verdicts.append(check_at_most("充电过流锁存延时", (coc_latch or 9.0) - 0.0, 0.60, "s"))
    rows.extend(snapshot.to_dict() | {"scenario": "CHARGE_OCD"} for snapshot in coc_snaps)
    event_rows.extend({"scenario": "CHARGE_OCD", **event} for event in coc_run["events"])

    # 4) 放电过流 5 A。
    doc = _controller()
    doc_run = _drive(
        doc,
        duration_s=0.35,
        step_s=0.002,
        voltages=lambda t: (3.9, 3.9, 3.9),
        current=5.0,
    )
    doc_snaps = doc_run["snapshots"]
    doc_latch = _first_latch(doc_snaps, FaultCode.DISCHARGE_OVERCURRENT.value)
    verdicts.append(check_at_most("放电过流锁存延时", (doc_latch or 9.0) - 0.0, 0.30, "s"))
    rows.extend(snapshot.to_dict() | {"scenario": "DISCHARGE_OCD"} for snapshot in doc_snaps)
    event_rows.extend({"scenario": "DISCHARGE_OCD", **event} for event in doc_run["events"])

    # 5) 短路 9 A：两方向同时禁止。
    sc = _controller()
    sc_run = _drive(
        sc,
        duration_s=0.05,
        step_s=0.0005,
        voltages=lambda t: (3.9, 3.9, 3.9),
        current=9.0,
    )
    sc_snaps = sc_run["snapshots"]
    sc_latch = _first_latch(sc_snaps, FaultCode.SHORT_CIRCUIT.value)
    sc_latched = _last(sc_snaps)
    verdicts.extend(
        [
            check_at_most("短路锁存延时", (sc_latch or 9.0), 0.010, "s"),
            check_true(
                "短路后双向禁止",
                (not sc_latched.charge_allowed) and (not sc_latched.discharge_allowed),
                "",
            ),
        ]
    )
    rows.extend(snapshot.to_dict() | {"scenario": "SHORT_CIRCUIT"} for snapshot in sc_snaps)
    event_rows.extend({"scenario": "SHORT_CIRCUIT", **event} for event in sc_run["events"])

    # 6) 过温 70 ℃。
    ot = _controller()
    ot_run = _drive(
        ot,
        duration_s=2.4,
        step_s=0.005,
        voltages=lambda t: (3.9, 3.9, 3.9),
        temperature=70.0,
    )
    ot_snaps = ot_run["snapshots"]
    ot_latch = _first_latch(ot_snaps, FaultCode.OVER_TEMPERATURE.value)
    ot_latched = _last(ot_snaps)
    verdicts.extend(
        [
            check_at_most("过温锁存延时", (ot_latch or 9.0), 2.20, "s"),
            check_true("过温后双向禁止", (not ot_latched.charge_allowed) and (not ot_latched.discharge_allowed), ""),
        ]
    )
    rows.extend(snapshot.to_dict() | {"scenario": "OVER_TEMPERATURE"} for snapshot in ot_snaps)
    event_rows.extend({"scenario": "OVER_TEMPERATURE", **event} for event in ot_run["events"])

    # 7) 低温禁止充电：−5 ℃。
    ut = _controller()
    ut_run = _drive(
        ut,
        duration_s=2.4,
        step_s=0.005,
        voltages=lambda t: (3.9, 3.9, 3.9),
        temperature=-5.0,
    )
    ut_latched = _last(ut_run["snapshots"])
    verdicts.append(
        check_true(
            "低温下禁止充电且允许放电",
            (not ut_latched.charge_allowed) and ut_latched.discharge_allowed,
            f"charge={ut_latched.charge_allowed}",
        )
    )
    rows.extend(snapshot.to_dict() | {"scenario": "UNDER_TEMPERATURE"} for snapshot in ut_run["snapshots"])
    event_rows.extend({"scenario": "UNDER_TEMPERATURE", **event} for event in ut_run["events"])

    # 8) 测量失效：立即双向禁止。
    inv = _controller()
    inv_run = _drive(
        inv,
        duration_s=0.05,
        step_s=0.001,
        voltages=lambda t: (3.9, 3.9, 3.9),
        valid=False,
    )
    inv_latched = _last(inv_run["snapshots"])
    verdicts.append(
        check_true(
            "测量失效立即双向禁止",
            (not inv_latched.charge_allowed) and (not inv_latched.discharge_allowed),
            "",
        )
    )
    rows.extend(snapshot.to_dict() | {"scenario": "MEASUREMENT_INVALID"} for snapshot in inv_run["snapshots"])
    event_rows.extend({"scenario": "MEASUREMENT_INVALID", **event} for event in inv_run["events"])

    # 不允许自动重启：任意锁存场景中，未经重新使能就恢复许可的次数必须为 0。
    auto_restart = 0
    for snap in ov_snaps:
        if 5.60 <= snap.time_s < 5.70 and (snap.charge_allowed or snap.discharge_allowed):
            auto_restart += 1
    verdicts.append(check_at_most("恢复后未重新使能即自动重启次数", float(auto_restart), 0.0, "次"))

    header = [
        "scenario",
        "time_s",
        "cell_voltages_v",
        "pack_current_a",
        "temperature_c",
        "state",
        "charge_allowed",
        "discharge_allowed",
        "active_faults",
        "latched_faults",
        "balancing_summary",
    ]
    write_csv(
        run_dir.path / "protection_timeline.csv",
        header,
        [
            (
                row["scenario"],
                row["time_s"],
                "|".join(f"{value:.4f}" for value in row["cell_voltages_v"]),
                row["pack_current_a"],
                row["temperature_c"],
                row["state"],
                row["charge_allowed"],
                row["discharge_allowed"],
                "|".join(row["active_faults"]),
                "|".join(row["latched_faults"]),
                "".join("1" if channel["enabled"] else "0" for channel in row["balancing"]),
            )
            for row in rows
        ],
    )
    write_csv(
        run_dir.path / "state_machine_events.csv",
        ["scenario", "time_s", "event", "code", "note", "reason", "cleared", "requires_rearm"],
        [
            (
                event.get("scenario"),
                event.get("time_s"),
                event.get("event"),
                event.get("code"),
                event.get("note"),
                event.get("reason"),
                "|".join(event.get("cleared", [])),
                event.get("requires_rearm"),
            )
            for event in event_rows
        ],
    )

    verdict = summarize_checks(verdicts)
    summary = {
        "run_id": run_dir.run_id,
        "real_spice_solves": 0,
        "note": "本实验是状态机离散仿真，不消耗 SPICE 求解",
        "checks": verdict["checks"],
        "passed": verdict["passed"],
        "failed": verdict["failed"],
        "total": verdict["total"],
        "status": verdict["status"],
        "verdict": verdict,
        "stage": "stage5",
        "key_times": {
            "overvoltage_latch_s": ov_latch,
            "undervoltage_latch_s": uv_latch,
            "charge_overcurrent_latch_s": coc_latch,
            "discharge_overcurrent_latch_s": doc_latch,
            "short_circuit_latch_s": sc_latch,
            "over_temperature_latch_s": ot_latch,
        },
    }
    run_dir.write_summary(summary)
    write_json(run_dir.path / "thresholds.json", limits.to_dict())
    run_dir.flush_log()
    return {"run_id": run_dir.run_id, "summary": summary, "checks": verdicts, "path": str(run_dir.path)}


def main() -> int:
    result = run()
    verdict = summarize_checks(result["checks"])
    print(f"run_id={result['run_id']}")
    for check in verdict["checks"]:
        print(f"{check['status']:4s} {check['name']:34s} measured={check['measured']} limit={check['limit']}")
    print(f"total PASS={verdict['passed']} FAIL={verdict['failed']}")
    return 0 if verdict["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
