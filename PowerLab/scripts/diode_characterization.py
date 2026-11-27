"""第四阶段：续流二极管真实正/反向特性扫描。

模型为低储存电荷教学二极管（D 模型 + CJO/RS），不是经标定的肖特基模型。
"""

from __future__ import annotations

from analysis.device_characteristics import extract_diode_forward, extract_diode_reverse
from circuits.nonideal_config import load_device_models
from simulations.device_runner import diode_data, run_diode_forward, run_diode_reverse
from scripts.nonideal_common import DEVICE_RESULTS_ROOT
from storage.result_store import ResultStore
from visualization.plots import plot_diode_curves


def main() -> int:
    models = load_device_models()
    diode = models["diode"]
    tests = models["diode_tests"]
    temperature = float(models["raw"]["temperature_tests"]["temperature_c"][0])

    store = ResultStore(root=DEVICE_RESULTS_ROOT)

    forward_result = run_diode_forward(
        diode,
        vd_start_v=float(tests["forward_start_v"]),
        vd_stop_v=float(tests["forward_stop_v"]),
        vd_step_v=float(tests["forward_step_v"]),
        temperature_c=temperature,
    )
    forward = extract_diode_forward(forward_result, tests["reference_currents_a"])

    reverse_result = run_diode_reverse(
        diode,
        vd_start_v=float(tests["reverse_start_v"]),
        vd_stop_v=float(tests["reverse_stop_v"]),
        vd_step_v=float(tests["reverse_step_v"]),
        temperature_c=temperature,
    )
    reverse = extract_diode_reverse(reverse_result)

    forward_data = diode_data(forward_result)
    reverse_data = diode_data(reverse_result)

    run_id, run_dir = store.create_run_dir()
    figure = plot_diode_curves(
        forward_data["vd_v"],
        forward_data["id_a"],
        reverse_data["vd_v"],
        reverse_data["id_a"],
        run_dir / "diode_characteristics.png",
        title="Freewheeling Diode Characteristics",
    )
    store.save_result(
        forward_result,
        run_dir=run_dir,
        figures={"diode_characteristics.png": figure},
        summary={"forward": forward, "reverse": reverse},
        extra_json={"forward.json": forward, "reverse.json": reverse},
    )
    print(f"[diode] run={run_id}")
    print(
        f"  forward max current {forward['forward_current_max_a']:.4f} A at "
        f"{forward['forward_voltage_at_max_current_v']:.4f} V"
    )
    for key, item in forward["voltage_drops"].items():
        print(
            f"  VF @ {item['current_a']:.2f} A = {item['forward_voltage_v']} V "
            f"({item['status']})"
        )
    print(
        f"  reverse leakage at {reverse['reverse_voltage_min_v']:.2f} V = "
        f"{reverse['leakage_at_min_voltage_a']:.6e} A"
    )

    sensitivity = float(tests["transit_time_sensitivity"])
    print(
        f"  configured transit time TT = {diode.transit_time_s:.3e} s; "
        f"configured sensitivity reference = {sensitivity:.3e} s"
    )
    print(
        "  note: reverse recovery is not calibrated against a real part; "
        "the TT sensitivity value is a teaching comparison setting."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
