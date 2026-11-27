"""电阻分压电路：真实 ngspice 直流工作点仿真 + 理论对照。

运行::

    python -m scripts.voltage_divider_demo
"""

from __future__ import annotations

import sys
from typing import Any

from analysis.metrics import divider_metrics
from circuits.divider import build_voltage_divider
from simulations.artifacts import create_run_dir, write_json, write_text
from simulations.config import DividerConfig, load_simulation_config
from simulations.environment import collect_environment


def simulate_voltage_divider(config: DividerConfig | None = None) -> dict[str, Any]:
    """执行一次真实工作点分析，返回节点电压与理论对照。

    该函数不写磁盘，供测试直接复用。
    """
    config = config or load_simulation_config().divider
    circuit = build_voltage_divider(config.vin_v, config.r1_ohm, config.r2_ohm)

    simulator = circuit.simulator(temperature=25, nominal_temperature=25)
    operating_point = simulator.operating_point()

    vin = float(operating_point["vin"][0])
    vout = float(operating_point["out"][0])
    metrics = divider_metrics(
        vin,
        vout,
        config.theoretical_output_v,
        config.theoretical_current_a,
    )
    return {
        "vin": vin,
        "vout": vout,
        "theoretical_vout": config.theoretical_output_v,
        "theoretical_current": config.theoretical_current_a,
        "metrics": metrics,
        "netlist": str(circuit),
        "data_source": "spice_simulation",
        "backend": "PySpice 1.5 + ngspice shared DLL",
        "config": config.to_dict(),
    }


def main() -> int:
    config = load_simulation_config().divider
    try:
        result = simulate_voltage_divider(config)
    except Exception as exc:  # noqa: BLE001 - 命令行需要如实上报仿真失败
        print(f"仿真失败: {exc}", file=sys.stderr)
        return 1

    run_dir = create_run_dir("divider")
    write_text(run_dir / "netlist.cir", result["netlist"])
    payload = {
        **result,
        "environment": collect_environment(),
        "simulation": {"analysis": "operating_point", "temperature_c": 25},
    }
    write_json(run_dir / "result.json", payload)

    print("SPICE Netlist:")
    print(result["netlist"])
    print(f"Input voltage:            {result['vin']:.6f} V")
    print(f"Simulated output voltage: {result['vout']:.6f} V")
    print(f"Theoretical output:       {result['theoretical_vout']:.6f} V")
    print(f"Absolute error:           {result['metrics']['absolute_error_v']:.9f} V")
    print(f"Relative error:           {result['metrics']['relative_error_percent']:.6f} %")
    print(f"Theoretical current:      {result['theoretical_current']:.6f} A")
    print(f"Run directory:            {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
