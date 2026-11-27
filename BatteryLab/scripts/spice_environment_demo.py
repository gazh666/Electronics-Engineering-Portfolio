"""Task 11：验证 BatteryLab 的 PySpice / ngspice 电路仿真后端。

5V 经 10kΩ / 10kΩ 分压，理论输出 2.5V。只有真实 ngspice 求解成功才标记 PASS，
不返回理论值冒充仿真结果。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySpice.Spice.NgSpice.Shared import NgSpiceShared
from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import u_V, u_kOhm

from storage.result_store import RunDirectory

THEORY_V = 2.5


def build_circuit() -> Circuit:
    circuit = Circuit("BatteryLab voltage divider")
    circuit.V("input", "vin", circuit.gnd, 5 @ u_V)
    circuit.R(1, "vin", "out", 10 @ u_kOhm)
    circuit.R(2, "out", circuit.gnd, 10 @ u_kOhm)
    return circuit


def main() -> int:
    run = RunDirectory("spice")
    backend_info: dict[str, object] = {}
    try:
        shared = NgSpiceShared.new_instance()
        backend_info = {
            "interface": "PySpice NgSpice.Shared (CFFI dlopen)",
            "ngspice_version": int(shared.ngspice_version),
            "ngspice_library": str(shared.library_path),
        }
    except Exception as exc:  # noqa: BLE001
        backend_info = {"interface": "unavailable", "error": f"{type(exc).__name__}: {exc}"}

    circuit = build_circuit()
    netlist = str(circuit)
    (run.path / "circuit.cir").write_text(netlist, encoding="utf-8")

    status = "PASS"
    summary: dict[str, object] = {
        "data_source": "spice_simulation",
        "circuit": "5V resistive divider, 10k/10k",
        "theory_output_v": THEORY_V,
        "backend": backend_info,
    }
    try:
        simulator = circuit.simulator(temperature=25, nominal_temperature=25)
        analysis = simulator.operating_point()
        vout = float(analysis["out"][0])
        vin = float(analysis["vin"][0])
        summary.update(
            {
                "status": status,
                "input_node_voltage_v": vin,
                "output_node_voltage_v": vout,
                "absolute_error_v": abs(vout - THEORY_V),
                "relative_error_pct": abs(vout - THEORY_V) / THEORY_V * 100.0,
                "netlist_path": str(run.path / "circuit.cir"),
            }
        )
        run.log(f"ngspice 求解成功: vin={vin:.9f}V, out={vout:.9f}V")
    except Exception as exc:  # noqa: BLE001
        status = "NOT_VERIFIED"
        summary.update(
            {
                "status": status,
                "error": f"{type(exc).__name__}: {exc}",
                "netlist_path": str(run.path / "circuit.cir"),
                "output_node_voltage_v": None,
            }
        )
        run.log(f"ngspice 求解失败: {exc}")

    summary["status"] = status
    run.write_metadata({"script": "scripts/spice_environment_demo.py", **summary})
    run.write_summary(summary)
    run.flush_log()
    print(json.dumps({"run_id": run.run_id, "run_path": str(run.path), **summary}, ensure_ascii=False, indent=2))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
