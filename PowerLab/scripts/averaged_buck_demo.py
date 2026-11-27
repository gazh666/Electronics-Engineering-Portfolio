"""平均模型演示：闭环与固定占空比开环（非开关级）。"""

from __future__ import annotations

from circuits.closed_loop_config import load_closed_loop_config
from simulations.averaged_model_runner import averaged_metrics, run_averaged_closed_loop

from .stage7_common import save_csv, save_json


def main() -> int:
    config = load_closed_loop_config()
    payload: dict[str, object] = {"data_source": "averaged_model", "runs": {}}
    for mode in ("closed_loop", "open_loop"):
        result = run_averaged_closed_loop(config, mode=mode)
        metrics = averaged_metrics(result)
        save_csv(f"averaged_{mode}.csv", result.data)
        payload["runs"][mode] = {
            "run_id": result.run_id,
            "point_count": result.point_count,
            "duration_ms": result.duration_ms,
            "metrics": metrics,
            "metadata": result.metadata,
        }
        print(
            f"{mode}: run_id={result.run_id} points={result.point_count} "
            f"wall={result.duration_ms/1000:.2f}s tail={metrics['tail_mean_v']:.4f} V "
            f"peak_iL={metrics['peak_inductor_current_a']:.3f} A "
            f"duty={metrics['final_duty_cmd']:.4f}->{metrics['final_effective_duty']:.4f} "
            f"ccm={metrics['ccm_fraction']:.3f}"
        )
    payload["note"] = "averaged model only; no switching ripple or gate drive"
    print("saved:", save_json("averaged_buck_demo.json", payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
