"""第四阶段：MOSFET 教学模型真实特性扫描（转移 / 输出 / 截止）。

全部数值来自 ngspice 直流扫描；模型为 Level 1 教学假设模型，
不是经过验证的商业功率器件 SPICE 模型。
"""

from __future__ import annotations

from analysis.device_characteristics import (
    extract_off_state,
    extract_output_characteristics,
    extract_transfer_characteristics,
    rds_on_at_current,
)
from circuits.nonideal_config import load_device_models
from simulations.device_runner import (
    mosfet_output_data,
    mosfet_transfer_data,
    run_mosfet_off_state,
    run_mosfet_output,
    run_mosfet_transfer,
)
from scripts.nonideal_common import DEVICE_RESULTS_ROOT
from storage.result_store import ResultStore
from visualization.plots import plot_mosfet_output, plot_mosfet_transfer


def main() -> int:
    models = load_device_models()
    mosfet = models["mosfet"]
    tests = models["mosfet_tests"]
    temperature = float(models["raw"]["temperature_tests"]["temperature_c"][0])

    store = ResultStore(root=DEVICE_RESULTS_ROOT)

    # ---------------------------------------------------------- transfer
    transfer_result = run_mosfet_transfer(
        mosfet,
        vds_v=float(tests["transfer"]["vds_v"]),
        vgs_start_v=float(tests["transfer"]["vgs_start_v"]),
        vgs_stop_v=float(tests["transfer"]["vgs_stop_v"]),
        vgs_step_v=float(tests["transfer"]["vgs_step_v"]),
        temperature_c=temperature,
    )
    transfer = extract_transfer_characteristics(transfer_result)
    transfer_data = mosfet_transfer_data(transfer_result)

    run_id, run_dir = store.create_run_dir()
    figure = plot_mosfet_transfer(
        transfer_data["vgs_v"],
        transfer_data["id_a"],
        run_dir / "mosfet_transfer.png",
        threshold_v=transfer["threshold_estimate_v"],
        title="NMOS Transfer Characteristic (Level 1 teaching model)",
    )
    store.save_result(
        transfer_result,
        run_dir=run_dir,
        figures={"mosfet_transfer.png": figure},
        summary={"characteristics": transfer},
        extra_json={"characteristics.json": transfer},
        log_lines=[f"threshold_estimate_v={transfer['threshold_estimate_v']}"],
    )
    print(f"[transfer] run={run_id}")
    print(
        f"  VGS {transfer['vgs_min_v']:.2f}..{transfer['vgs_max_v']:.2f} V, "
        f"ID max {transfer['drain_current_max_a']:.4f} A, "
        f"VTH fit {transfer['threshold_estimate_v']} V ({transfer['threshold_status']})"
    )

    # ------------------------------------------------------------ output
    output_runs = []
    for vgs in tests["output"]["vgs_values_v"]:
        result = run_mosfet_output(
            mosfet,
            vgs_v=float(vgs),
            vds_start_v=float(tests["output"]["vds_start_v"]),
            vds_stop_v=float(tests["output"]["vds_stop_v"]),
            vds_step_v=float(tests["output"]["vds_step_v"]),
            temperature_c=temperature,
        )
        output_runs.append((float(vgs), result, extract_output_characteristics(result)))

    figure_dir = DEVICE_RESULTS_ROOT / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    output_figure = plot_mosfet_output(
        {
            f"VGS = {vgs:.0f} V": (
                mosfet_output_data(result)["vds_v"],
                mosfet_output_data(result)["id_a"],
            )
            for vgs, result, _ in output_runs
        },
        figure_dir / "mosfet_output.png",
        title="NMOS Output Characteristic (Level 1 teaching model)",
    )
    for vgs, result, characteristics in output_runs:
        run_id, run_dir = store.create_run_dir()
        store.save_result(
            result,
            run_dir=run_dir,
            figures={"mosfet_output.png": output_figure},
            summary={"characteristics": characteristics},
            extra_json={"characteristics.json": characteristics},
        )
        print(f"[output] run={run_id} VGS={vgs:.1f} V")
        print(
            f"  ID max {characteristics['drain_current_max_a']:.4f} A, "
            f"RDS(low VDS) {characteristics['rds_on_low_vds_ohm']} ohm"
        )

    # ------------------------------------------------------------- rds_on
    rds_target = float(tests["rds_point"]["target_current_a"])
    reference = max(output_runs, key=lambda item: item[0])[1]
    rds = rds_on_at_current(reference, rds_target)
    print("[rds_on]")
    print(
        f"  target {rds['target_current_a']:.3f} A -> VDS {rds['vds_v']} V, "
        f"RDS {rds['rds_on_ohm']} ohm ({rds['status']})"
    )

    # ---------------------------------------------------------- off state
    off_result = run_mosfet_off_state(
        mosfet,
        vgs_v=float(tests["off_state"]["vgs_v"]),
        vds_start_v=0.0,
        vds_stop_v=float(tests["off_state"]["vds_v"]),
        vds_step_v=0.1,
        temperature_c=temperature,
    )
    off_state = extract_off_state(off_result)
    run_id, run_dir = store.create_run_dir()
    store.save_result(
        off_result,
        run_dir=run_dir,
        summary={"off_state": off_state},
        extra_json={"off_state.json": off_state},
    )
    print(f"[off_state] run={run_id}")
    print(
        f"  leakage at {off_state['vds_at_measurement_v']:.2f} V = "
        f"{off_state['drain_leakage_at_max_vds_a']:.6e} A"
    )
    print(
        "  note: Level 1 square-law model; RDS(on) is a teaching-model "
        "operating-point value, not a datasheet maximum."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
