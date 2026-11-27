"""内阻健康指标演示（Task 27 / Task 40）。

真实数据只有 25℃、同一电芯、非老化条件，无法给出真实内阻增长率。因此：

- 从真实 US06 电流阶跃估计一次表观 DCIR（同条件单点，不是老化趋势）；
- 用合成序列演示增长率数学与可比性判据（``synthetic_truth``）；
- 真实内阻增长率标记 ``NOT_VERIFIED``。
"""

from __future__ import annotations

import numpy as np

from analysis.health_metrics import summarize_resistance_series
from experiments.common import measurement_bundle
from health.resistance_health import (
    ResistanceCondition,
    compare_resistance_conditions,
    pulse_resistance_ohm,
    resistance_growth_percent,
)
from scripts.stage7_common import (
    finish,
    open_run,
    plot_series,
    write_metadata,
    write_payload,
    write_rows,
)

DATASET = "us06_50"


def _find_step(current_a: np.ndarray, minimum_delta_a: float = 0.8) -> int:
    deltas = np.abs(np.diff(current_a))
    candidates = np.where(deltas >= minimum_delta_a)[0]
    if candidates.size == 0:
        raise RuntimeError("未找到足够大的电流阶跃")
    return int(candidates[np.argmax(deltas[candidates])])


def main() -> None:
    run = open_run("battery_health")
    measurement = measurement_bundle(DATASET)
    time_s = measurement["time_s"]
    current_a = measurement["current_a"]
    voltage_v = measurement["voltage_v"]
    reference_soc = measurement["reference_soc"]

    index = _find_step(current_a)
    resistance = pulse_resistance_ohm(
        float(voltage_v[index]), float(voltage_v[index + 1]),
        float(current_a[index]), float(current_a[index + 1]),
    )
    condition = ResistanceCondition(
        cell_id=str(measurement["cell_id"]),
        soc=float(reference_soc[index]),
        temperature_c=float(measurement["temperature_c"]),
        current_direction="discharge" if (current_a[index + 1] - current_a[index]) > 0 else "charge",
        pulse_amplitude_a=float(abs(current_a[index + 1] - current_a[index])),
        window_s=float(time_s[index + 1] - time_s[index]),
        method="dcir",
    )
    comparable_same = compare_resistance_conditions(condition, condition)
    mismatched = compare_resistance_conditions(
        condition,
        ResistanceCondition(
            cell_id=condition.cell_id,
            soc=condition.soc,
            temperature_c=condition.temperature_c + 10.0,
            current_direction=condition.current_direction,
            pulse_amplitude_a=condition.pulse_amplitude_a,
            window_s=condition.window_s,
            method=condition.method,
        ),
    )

    # 合成内阻增长序列：仅用于验证增长率数学与绘图（不是真实老化）。
    cycles = list(range(1, 101))
    reference_resistance = float(resistance)
    synthetic = [
        {
            "cycle_index": cycle,
            "resistance_ohm": reference_resistance * (1.0 + 0.004 * (cycle - 1)),
            "growth_percent": resistance_growth_percent(
                reference_resistance * (1.0 + 0.004 * (cycle - 1)), reference_resistance
            ),
        }
        for cycle in cycles
    ]
    synthetic_summary = summarize_resistance_series(
        [row["cycle_index"] for row in synthetic],
        [row["resistance_ohm"] for row in synthetic],
        reference_resistance,
    )

    write_metadata(
        run,
        script="resistance_health_demo",
        description="真实阶跃表观 DCIR 单点估计 + 合成内阻增长序列与可比性判据",
        extra={"dataset": DATASET, "real_aging_available": False},
    )
    write_rows(
        run,
        "resistance_health.csv",
        [
            {
                "cell_id": condition.cell_id,
                "time_s": float(time_s[index]),
                "soc": condition.soc,
                "temperature_c": condition.temperature_c,
                "current_direction": condition.current_direction,
                "pulse_amplitude_a": condition.pulse_amplitude_a,
                "window_s": condition.window_s,
                "method": condition.method,
                "apparent_resistance_ohm": resistance,
                "real_growth_status": "NOT_VERIFIED",
                "comparable_self": comparable_same["status"],
                "comparable_temperature_offset": mismatched["status"],
                "source_type": "public_experimental_data",
            }
        ],
    )
    write_rows(
        run,
        "synthetic_resistance_growth.csv",
        synthetic,
        header=["cycle_index", "resistance_ohm", "growth_percent"],
    )
    write_payload(
        run,
        "resistance_summary.json",
        {
            "real_point": {
                "cell_id": condition.cell_id,
                "soc": condition.soc,
                "temperature_c": condition.temperature_c,
                "current_direction": condition.current_direction,
                "pulse_amplitude_a": condition.pulse_amplitude_a,
                "window_s": condition.window_s,
                "apparent_resistance_ohm": resistance,
                "metric": "dcir",
            },
            "comparability": {
                "same_condition": comparable_same,
                "temperature_mismatch_example": mismatched,
            },
            "synthetic_growth": synthetic_summary,
            "real_growth_status": "NOT_VERIFIED",
            "note": "真实数据无老化循环；合成增长序列不得称为实测内阻老化。",
        },
    )
    plot_series(
        run,
        "19_resistance_growth.png",
        {"synthetic DCIR growth (teaching)": (cycles, [row["growth_percent"] for row in synthetic])},
        title=f"Resistance growth — synthetic series (run {run.run_id})",
        xlabel="cycle index",
        ylabel="growth (%)",
    )
    finish(run, "resistance health demo done")
    print(
        f"[resistance_health_demo] run={run.run_id} apparent_DCIR={resistance:.6f} ohm "
        f"at SOC={condition.soc:.3f}, dI={condition.pulse_amplitude_a:.3f} A, window={condition.window_s:.1f} s"
    )
    print(f"  same-condition -> {comparable_same['status']}; +10C -> {mismatched['status']} {mismatched['reasons']}")
    print(f"  synthetic growth final={synthetic_summary['final_growth_percent']:.3f} %; real growth NOT_VERIFIED")


if __name__ == "__main__":
    main()
