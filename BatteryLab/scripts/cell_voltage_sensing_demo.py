"""Task 6/30：3S 单体电压节点模型与差分采集演示。

运行：conda run -n kaifa_battery python -m scripts.cell_voltage_sensing_demo
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from circuits.cell_voltage_sensing import (
    DEFAULT_REFERENCE_CELLS,
    solve_3s_sensing,
    solve_3s_stack,
    wrong_ground_mapping,
)
from scripts.stage4_common import amplifier_config, afe
from simulations.sensing_runner import finalize_run, new_sensing_run, write_frame, write_plots, write_rows
from visualization.plots import plot_multi_series, plot_xy

SOURCE = "真实 ngspice 工作点求解（spice_simulation）"


def main() -> int:
    config = afe()
    amp = amplifier_config(config)
    run = new_sensing_run("sensing")

    stack = solve_3s_stack(DEFAULT_REFERENCE_CELLS)
    channels = solve_3s_sensing(
        DEFAULT_REFERENCE_CELLS,
        amp,
        input_filter_resistance_ohm=float(config["cell_voltage"]["input_filter_resistance_ohm"]),
        differential_capacitance_f=float(config["cell_voltage"]["differential_capacitance_f"]),
    )
    wrong = wrong_ground_mapping(DEFAULT_REFERENCE_CELLS)

    node_frame = pd.DataFrame(
        [
            {"node": "N0", "to_ground_v": stack["n0_v"]},
            {"node": "N1", "to_ground_v": stack["n1_v"]},
            {"node": "N2", "to_ground_v": stack["n2_v"]},
            {"node": "N3", "to_ground_v": stack["n3_v"]},
        ]
    )
    cell_frame = pd.DataFrame(
        [
            {"cell": "cell1", "differential_v": stack["cell1_v"]},
            {"cell": "cell2", "differential_v": stack["cell2_v"]},
            {"cell": "cell3", "differential_v": stack["cell3_v"]},
        ]
    )
    sensing_frame = pd.DataFrame(channels)
    wrong_frame = pd.DataFrame(wrong)

    write_frame(run, "node_voltages.csv", node_frame)
    write_frame(run, "cell_voltages.csv", cell_frame)
    write_frame(run, "cell_sensing_channels.csv", sensing_frame)
    write_frame(run, "wrong_grounding_comparison.csv", wrong_frame)

    plots = write_plots(
        run,
        [
            (
                "01_3s_node_voltages.png",
                plot_xy,
                {
                    "x": [0, 1, 2, 3],
                    "y": [stack["n0_v"], stack["n1_v"], stack["n2_v"], stack["n3_v"]],
                    "xlabel": "节点编号（N0–N3）",
                    "ylabel": "对地电压 (V)",
                    "title": "3S 串联电池对地节点电压（真实 ngspice）",
                    "annotation": f"{SOURCE}；N0 为 0 V 参考。",
                    "color": "#1f77b4",
                },
            ),
            (
                "02_3s_cell_differential_voltages.png",
                plot_xy,
                {
                    "x": [1, 2, 3],
                    "y": [stack["cell1_v"], stack["cell2_v"], stack["cell3_v"]],
                    "xlabel": "单体编号",
                    "ylabel": "差分电压 (V)",
                    "title": "3S 单体差分电压 V(Nk)-V(Nk-1)",
                    "annotation": f"{SOURCE}；对地电压不等于单体电压。",
                    "color": "#d62728",
                },
            ),
            (
                "03_diff_amp_channel_outputs.png",
                plot_multi_series,
                {
                    "series": [
                        ("SPICE 输出", [1, 2, 3], sensing_frame["vout_v"].tolist()),
                        ("理论输出", [1, 2, 3], sensing_frame["theory_v"].tolist()),
                    ],
                    "xlabel": "单体通道",
                    "ylabel": "差分放大器输出 (V)",
                    "title": "三路单体采集 SPICE 与理论对照",
                    "annotation": f"{SOURCE}；增益 0.5，参考 0.2 V。",
                },
            ),
        ],
    )

    summary = {
        "node_voltages": {key: stack[key] for key in ("n0_v", "n1_v", "n2_v", "n3_v")},
        "cell_differential_voltages": {
            "cell1_v": stack["cell1_v"],
            "cell2_v": stack["cell2_v"],
            "cell3_v": stack["cell3_v"],
        },
        "kvl_error_v": stack["kvl_error_v"],
        "wrong_grounding_cell2_error_v": stack["wrong_cell2_error_v"],
        "max_channel_theory_error_v": float(sensing_frame["error_v"].abs().max()),
        "max_filter_loading_error_v": float(sensing_frame["filter_loading_error_v"].abs().max()),
        "channels": channels,
        "plots": plots,
    }
    payload = finalize_run(
        run,
        script="scripts.cell_voltage_sensing_demo.py",
        summary=summary,
        metadata={"config": "configs/afe_config.yaml", "cell_reference_v": list(DEFAULT_REFERENCE_CELLS)},
    )

    print(f"run_id={run.run_id}")
    print("节点电压:", {key: round(stack[key], 6) for key in ("n0_v", "n1_v", "n2_v", "n3_v")})
    print("单体差分:", {key: round(stack[key], 6) for key in ("cell1_v", "cell2_v", "cell3_v")})
    print(f"KVL 误差={stack['kvl_error_v']:.3e} V；错误接地 cell2 偏差={stack['wrong_cell2_error_v']:.3f} V")
    for row in channels:
        print(f"{row['channel']}: Vout={row['vout_v']:.6f} V 含滤波理论={row['theory_v']:.6f} V 误差={row['error_v']*1000:.4f} mV 滤波负载效应={row['filter_loading_error_v']*1000:.4f} mV 引脚共模={row['pin_common_mode_v']:.3f} V")
    print(f"真实 SPICE 求解次数={payload['real_spice_solves']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
