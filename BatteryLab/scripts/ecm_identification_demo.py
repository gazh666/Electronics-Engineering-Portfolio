"""Task 16-20/30：DST 动态辨识、多初值、参数冻结与训练评价。

运行：
  conda run -n kaifa_battery python -m scripts.ecm_identification_demo
  conda run -n kaifa_battery python -m scripts.ecm_identification_demo --refit
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import yaml

from analysis.fitting_metrics import calculate_voltage_errors, to_millivolts
from battery_models.ocv_model import IdentifiedOcvModel
from identification.ecm_fitter import multi_start_fit, ocv_callable, simulate_voltage
from identification.models import IdentifiedECMParameters
from identification.parameter_store import freeze_model, load_frozen_model
from identification.parameter_validator import identifiability_report, validate_parameters
from scripts.stage3_common import IDENTIFIED_DIR, capacity_bundle, configs, ocv_bundle
from storage.result_store import RESULTS_ROOT, RunDirectory, write_json
from validation.dataset_split import build_experiment
from visualization.plots import plot_dual_axis, plot_multi_series, plot_xy

MODEL_NAMES = {0: "rint", 1: "first_order_rc", 2: "second_order_rc"}
MODEL_IDS = {
    0: "calce_sp2_25c_inr18650_20r_rint_v1",
    1: "calce_sp2_25c_inr18650_20r_first_order_v1",
    2: "calce_sp2_25c_inr18650_20r_second_order_v1",
}
BASE_GUESS = {"r0_ohm": 0.050, "r1_ohm": 0.012, "tau1_s": 100.0, "r2_ohm": 0.018, "tau2_s": 2000.0}


def latest_run(category: str) -> Path | None:
    base = RESULTS_ROOT / category
    if not base.exists():
        return None
    runs = sorted([path for path in base.iterdir() if path.is_dir()])
    return runs[-1] if runs else None


def bounds_from_config(config: dict) -> dict[str, tuple[float, float]]:
    return {
        "r0_ohm": (float(config["r0_ohm"]["minimum"]), float(config["r0_ohm"]["maximum"])),
        "r1_ohm": (float(config["r1_ohm"]["minimum"]), float(config["r1_ohm"]["maximum"])),
        "tau1_s": (float(config["tau1_s"]["minimum"]), float(config["tau1_s"]["maximum"])),
        "r2_ohm": (float(config["r2_ohm"]["minimum"]), float(config["r2_ohm"]["maximum"])),
        "tau2_s": (float(config["tau2_s"]["minimum"]), float(config["tau2_s"]["maximum"])),
    }


def initial_guesses(order: int, count: int, seed: int) -> list[dict[str, float]]:
    guesses = [dict(BASE_GUESS)]
    rng = np.random.default_rng(seed)
    while len(guesses) < count:
        guesses.append(
            {
                "r0_ohm": float(BASE_GUESS["r0_ohm"] * np.exp(rng.normal(0, 0.35))),
                "r1_ohm": float(BASE_GUESS["r1_ohm"] * np.exp(rng.normal(0, 0.6))),
                "tau1_s": float(BASE_GUESS["tau1_s"] * np.exp(rng.normal(0, 0.6))),
                "r2_ohm": float(BASE_GUESS["r2_ohm"] * np.exp(rng.normal(0, 0.6))),
                "tau2_s": float(BASE_GUESS["tau2_s"] * np.exp(rng.normal(0, 0.4))),
            }
        )
    return guesses


def evaluate_open_loop(experiment, parameters: IdentifiedECMParameters, ocv_model, order: int) -> dict:
    frame = experiment.frame
    result = simulate_voltage(
        frame["time_s"].to_numpy(dtype=float),
        frame["current_a"].to_numpy(dtype=float),
        order=order,
        capacity_ah=parameters.capacity_ah,
        soc0=float(experiment.soc0),
        parameters={
            "r0_ohm": parameters.r0_ohm,
            **({"r1_ohm": parameters.r1_ohm, "tau1_s": parameters.tau1_s} if order >= 1 else {}),
            **({"r2_ohm": parameters.r2_ohm, "tau2_s": parameters.tau2_s} if order >= 2 else {}),
        },
        ocv=ocv_callable(ocv_model),
        soc_penalty_v=0.5,
    )
    metrics = to_millivolts(
        calculate_voltage_errors(frame["voltage_v"].to_numpy(dtype=float), result["voltage_v"])
    )
    metrics.update({"soc_min": result["soc_min"], "soc_max": result["soc_max"]})
    return metrics


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refit", action="store_true", help="忽略已冻结模型并重新拟合")
    args = parser.parse_args()

    run = RunDirectory("identification")
    total_started = time.perf_counter()
    settings = configs()
    identification = settings["identification"]
    budgets = identification["budget"]
    profile_name = "standard"
    inits = int(budgets["profiles"][profile_name]["initializations_per_model"])
    max_nfev = int(identification["dynamic_identification"]["maximum_function_evaluations"])
    refine_nfev = int(identification["dynamic_identification"]["refinement_function_evaluations"])
    bounds = bounds_from_config(settings["bounds"])
    capacities = capacity_bundle()
    capacity_ah = capacities["sp2"].integrated_capacity_ah
    ocv = ocv_bundle()
    ocv_model: IdentifiedOcvModel = ocv["model"]

    train = build_experiment("dst_50", settings["split"]["datasets"]["dst_50"], capacity_ah=capacity_ah)
    development = build_experiment("dst_80", settings["split"]["datasets"]["dst_80"], capacity_ah=capacity_ah)

    run.write_metadata(
        {
            "script": "scripts.ecm_identification_demo.py",
            "data_source": "public_experimental_data",
            "profile": profile_name,
            "initializations_per_model": inits,
            "capacity_ah": capacity_ah,
            "ocv_model": ocv_model.metadata(),
            "training": train.summary(),
            "development": development.summary(),
            "refit": bool(args.refit),
        }
    )

    all_trials = []
    runtime_by_model: dict[str, float | None] = {}
    training_metrics: dict[str, dict] = {}
    development_metrics: dict[str, dict] = {}
    quality: dict[str, str] = {}
    frozen_bundles: dict[str, dict] = {}
    parameter_rows = []

    for order in (0, 1, 2):
        name = MODEL_NAMES[order]
        model_id = MODEL_IDS[order]
        frozen_path = IDENTIFIED_DIR / f"model_{model_id}"
        if frozen_path.exists() and not args.refit:
            bundle = load_frozen_model(model_id)
            parameters = bundle["parameters"]
            quality_payload = bundle.get("quality", {})
            best_summary = quality_payload.get("fitting_summary", {})
            training_metrics[name] = {
                "model_order": order,
                "training_rmse_v": best_summary.get("training_rmse_v"),
                "training_mae_v": best_summary.get("training_mae_v"),
                "reused_frozen_model": True,
            }
            frozen_bundles[name] = bundle
            quality[name] = parameters.quality_status
            runtime_by_model[name] = None
            parameter_rows.append(parameters.to_dict())
            print(f"{name}: 复用冻结模型 {model_id}")
            continue

        started = time.perf_counter()
        result = multi_start_fit(
            train.frame,
            order=order,
            ocv=ocv_model,
            capacity_ah=capacity_ah,
            soc0=float(train.soc0),
            initial_guesses=initial_guesses(order, inits, int(identification["dynamic_identification"]["random_seed"])),
            bounds=bounds,
            max_nfev=max_nfev,
            dataset_id=train.dataset_id,
            run_id_prefix=f"{name}_{run.run_id}",
        )
        best = result["best"]
        refinement = None
        if refine_nfev > max_nfev:
            refinement = __import__("identification.ecm_fitter", fromlist=["fit_single_start"]).fit_single_start(
                train.frame,
                order=order,
                ocv=ocv_model,
                capacity_ah=capacity_ah,
                soc0=float(train.soc0),
                initial_guess=best.parameter_values,
                bounds=bounds,
                max_nfev=refine_nfev,
                dataset_id=train.dataset_id,
                run_id=f"{name}_refined",
            )
            if refinement.training_rmse_v < best.training_rmse_v:
                best = refinement
        elapsed = time.perf_counter() - started
        runtime_by_model[name] = elapsed
        trials = result["trials"].copy()
        trials["model"] = name
        all_trials.append(trials)

        parameters = IdentifiedECMParameters.from_time_constants(
            model_order=order,
            capacity_ah=capacity_ah,
            r0_ohm=best.parameter_values["r0_ohm"],
            time_constants_s=tuple(best.parameter_values[key] for key in ("tau1_s", "tau2_s")[:order]),
            resistances_ohm=tuple(best.parameter_values[key] for key in ("r1_ohm", "r2_ohm")[:order]),
            temperature_c=25.0,
            cell_model="INR18650-20R",
            cell_id="SP2",
            soc_min=float(train.frame["soc_reference"].min()),
            soc_max=float(train.frame["soc_reference"].max()),
            parameter_source="identified_parameters",
            quality_status=best.parameter_quality,
        )
        validation = validate_parameters(parameters, bounds)
        sensitivity = identifiability_report(
            None, [key for key in ("r0_ohm", "r1_ohm", "tau1_s", "r2_ohm", "tau2_s")[: 1 + 2 * order]]
        )
        quality_payload = {
            "model": name,
            "parameters": parameters.to_dict(),
            "validation": validation,
            "multi_start_spread": result["spread"],
            "jacobian_condition_number": best.jacobian_condition_number,
            "identifiability": sensitivity,
            "fitting_summary": best.summary(),
            "budget": {
                "initializations_per_model": inits,
                "maximum_function_evaluations": max_nfev,
                "refinement_function_evaluations": refine_nfev,
                "wall_time_s": elapsed,
            },
        }
        quality[name] = validation["status"]
        training_metrics[name] = {
            "model_order": order,
            "training_rmse_v": best.training_rmse_v,
            "training_mae_v": best.training_mae_v,
            "maximum_error_v": best.maximum_error_v,
            "points": best.points,
            "soc_range": list(best.soc_range),
            "condition_number": best.jacobian_condition_number,
            "function_evaluations": best.function_evaluations,
        }
        frozen = freeze_model(
            model_id,
            parameters,
            ocv_model,
            training_manifest={
                **train.summary(),
                "initial_soc_method": train.soc0_method,
                "initial_polarization_v": identification["dynamic_identification"]["initial_polarization_v"],
                "dataset_sha256": settings["split"]["datasets"]["dst_50"]["sha256"],
                "development_dataset": development.summary(),
            },
            fitting_config={
                "profile": profile_name,
                "bounds": {key: list(value) for key, value in bounds.items()},
                "initial_guesses": inits,
                "loss": "linear",
                "budget": quality_payload["budget"],
            },
            parameter_quality=quality_payload,
        )
        frozen_bundles[name] = load_frozen_model(model_id)
        parameter_rows.append(parameters.to_dict())
        development_metrics[name] = evaluate_open_loop(development, parameters, ocv_model, order)
        print(
            f"{name}: quality={quality[name]}, training RMSE={best.training_rmse_v * 1000:.2f} mV, "
            f"dev RMSE={development_metrics[name]['rmse_mv']:.2f} mV, dir={frozen['directory']}"
        )

    # 复用冻结模型时仍需计算开发段误差
    for order in (0, 1, 2):
        name = MODEL_NAMES[order]
        if name not in development_metrics:
            development_metrics[name] = evaluate_open_loop(
                development, frozen_bundles[name]["parameters"], ocv_model, order
            )
        if name not in training_metrics or training_metrics[name].get("training_rmse_v") is None:
            stored = frozen_bundles[name].get("quality", {}).get("fitting_summary", {})
            training_metrics[name] = {
                "model_order": order,
                "training_rmse_v": stored.get("training_rmse_v"),
                "training_mae_v": stored.get("training_mae_v"),
                "reused_frozen_model": True,
            }

    if all_trials:
        trials_frame = pd.concat(all_trials, ignore_index=True)
        trials_frame.to_csv(run.path / "optimization_trials.csv", index=False)
    else:
        pd.DataFrame(
            [
                {
                    "model": name,
                    "status": "REUSED_FROZEN_MODEL",
                    "note": "本次未运行优化器，参数来自已冻结模型；优化过程记录见冻结目录 parameter_quality.json",
                }
                for name in frozen_bundles
            ]
        ).to_csv(run.path / "optimization_trials.csv", index=False)
    pd.DataFrame(parameter_rows).to_csv(run.path / "identified_parameters.csv", index=False)
    pd.DataFrame(parameter_rows).to_csv(IDENTIFIED_DIR / "identified_parameters_all_models.csv", index=False)

    # 训练波形（二阶模型；若二阶失败则用一阶）
    plot_model = "second_order_rc" if "second_order_rc" in frozen_bundles else "first_order_rc"
    chosen = frozen_bundles[plot_model]
    simulate = simulate_voltage(
        train.frame["time_s"].to_numpy(dtype=float) - train.frame["time_s"].iloc[0],
        train.frame["current_a"].to_numpy(dtype=float),
        order=chosen["parameters"].model_order,
        capacity_ah=capacity_ah,
        soc0=float(train.soc0),
        parameters={
            "r0_ohm": chosen["parameters"].r0_ohm,
            **({"r1_ohm": chosen["parameters"].r1_ohm, "tau1_s": chosen["parameters"].tau1_s}
               if chosen["parameters"].model_order >= 1 else {}),
            **({"r2_ohm": chosen["parameters"].r2_ohm, "tau2_s": chosen["parameters"].tau2_s}
               if chosen["parameters"].model_order >= 2 else {}),
        },
        ocv=ocv_callable(ocv_model),
    )
    time_values = train.frame["time_s"].to_numpy(dtype=float)
    measured = train.frame["voltage_v"].to_numpy(dtype=float)
    residual = simulate["voltage_v"] - measured
    waveform = pd.DataFrame(
        {
            "time_s": time_values,
            "current_a": train.frame["current_a"].to_numpy(dtype=float),
            "measured_voltage_v": measured,
            "predicted_voltage_v": simulate["voltage_v"],
            "residual_v": residual,
            "soc_reference": train.frame["soc_reference"].to_numpy(dtype=float),
            "soc_model": simulate["soc"],
            "polarization_1_v": simulate["polarization_1_v"],
            "polarization_2_v": simulate["polarization_2_v"],
        }
    )
    waveform.to_csv(run.path / "training_waveform.csv.gz", index=False, compression="gzip")
    plot_multi_series(
        [
            ("实测端电压", time_values, measured),
            (f"{plot_model} 预测", time_values, simulate["voltage_v"]),
        ],
        path=run.path / "plots" / "15_dst_training_voltage.png",
        xlabel="时间 (s)",
        ylabel="端电压 (V)",
        title="DST 训练段：实测与辨识模型开环电压",
        annotation=f"数据来源: public_experimental_data | 训练集 DST 50% SOC | Run: {run.run_id}",
    )
    plot_xy(
        time_values,
        residual * 1000.0,
        path=run.path / "plots" / "16_dst_training_residual.png",
        xlabel="时间 (s)",
        ylabel="残差 (mV)",
        title="DST 训练段电压残差",
        annotation=f"RMSE {np.sqrt(np.mean(residual**2)) * 1000:.2f} mV | Run: {run.run_id}",
    )
    plot_multi_series(
        [
            ("快速极化 V1", time_values, simulate["polarization_1_v"]),
            ("慢速极化 V2", time_values, simulate["polarization_2_v"]),
        ],
        path=run.path / "plots" / "14_polarization_components.png",
        xlabel="时间 (s)",
        ylabel="极化电压 (V)",
        title=f"{plot_model}: 快慢极化分量（DST 训练段）",
        annotation=f"来源: custom_ecm_simulation | Run: {run.run_id}",
    )
    plot_multi_series(
        [
            ("Rint", [0], [training_metrics["rint"]["training_rmse_v"] * 1000]),
            ("一阶 RC", [0], [training_metrics["first_order_rc"]["training_rmse_v"] * 1000]),
            ("二阶 RC", [0], [training_metrics["second_order_rc"]["training_rmse_v"] * 1000]),
        ],
        path=run.path / "plots" / "19_training_rmse_comparison.png",
        xlabel="",
        ylabel="训练 RMSE (mV)",
        title="三种 ECM 训练误差对照（DST 50% SOC）",
        annotation=f"数据来源: public_experimental_data | Run: {run.run_id}",
    )

    # Task 30：SOC 参考轨迹与 DST 电流/电压同图
    plot_multi_series(
        [
            ("SOC 参考（容量平衡）", time_values - time_values[0], waveform["soc_reference"]),
            ("SOC 模型（开环积分）", time_values - time_values[0], waveform["soc_model"]),
        ],
        path=run.path / "plots" / "03_soc_reference_trajectory.png",
        xlabel="相对时间 (s)",
        ylabel="SOC (-)",
        title="DST 训练段 SOC 参考轨迹与模型开环轨迹",
        annotation=(
            f"来源: public_experimental_data | 文件: {train.source_file} | 条件: 25℃, DST 50% SOC"
            f" | 初始 SOC {float(train.soc0):.4f} | 角色: training | Run: {run.run_id} | 单位: 1"
        ),
    )
    plot_dual_axis(
        pd.DataFrame(
            {
                "time_s": time_values - time_values[0],
                "current_a": train.frame["current_a"].to_numpy(dtype=float),
                "voltage_v": measured,
            }
        ),
        path=run.path / "plots" / "15b_dst_training_current_voltage.png",
        x="time_s",
        y_left="voltage_v",
        y_right="current_a",
        xlabel="相对时间 (s)",
        left_label="实测端电压 (V)",
        right_label="电流 (A)",
        title="DST 训练段：实测电流与端电压",
        annotation=(
            f"来源: public_experimental_data | 文件: {train.source_file} | 条件: 25℃, DST 50% SOC"
            f" | 角色: training | Run: {run.run_id} | 单位: V / A"
        ),
    )

    # Task 31：结果存储（identification/run_<id>/ 规定文件）
    write_json(
        run.path / "dataset_manifest.json",
        {
            "cell_model": settings["split"]["cell_model"],
            "primary_temperature_c": settings["split"]["primary_temperature_c"],
            "datasets": settings["split"]["datasets"],
            "training_dataset": "dst_50",
            "development_dataset": "dst_80",
            "role_rule": "DST 50% 训练，DST 80% 仅用于开发对照，FUDS 仅用于最终独立验证",
        },
    )
    (run.path / "identification_config.yaml").write_text(
        yaml.safe_dump(
            {"identification": identification, "bounds": settings["bounds"]},
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    write_json(run.path / "capacity_results.json", {key: value.to_dict() for key, value in capacities.items()})
    ocv_points = pd.concat(
        [
            curves.assign(direction=direction)
            for direction, curves in (("charge", ocv["curves"]["charge"]), ("discharge", ocv["curves"]["discharge"]))
        ],
        ignore_index=True,
    )
    ocv_points.to_csv(run.path / "ocv_points.csv", index=False)
    pd.DataFrame({"soc": ocv["soc_table"], "ocv_v": ocv["ocv_table"]}).to_csv(run.path / "ocv_soc.csv", index=False)
    (run.path / "identified_parameters.yaml").write_text(
        yaml.safe_dump(
            {name: bundle["parameters"].to_dict() for name, bundle in frozen_bundles.items()},
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    pulse_run = latest_run("pulse_identification")
    if pulse_run is not None:
        event_files = sorted(pulse_run.glob("detected_events_*.csv"))
        if event_files:
            pd.concat([pd.read_csv(path).assign(experiment=path.stem.replace("detected_events_", "")) for path in event_files]).to_csv(
                run.path / "detected_pulses.csv", index=False
            )
        for source_name in ("resistance_results.csv", "relaxation_fits.csv"):
            source_path = pulse_run / source_name
            if source_path.exists():
                pd.read_csv(source_path).to_csv(run.path / source_name, index=False)

    total_elapsed = time.perf_counter() - total_started

    summary = {
        "script": "scripts.ecm_identification_demo.py",
        "run_id": run.run_id,
        "capacity_ah": capacity_ah,
        "training_experiment": train.summary(),
        "development_experiment": development.summary(),
        "training_metrics": training_metrics,
        "development_metrics": development_metrics,
        "parameter_quality": quality,
        "runtime_s": {"total": total_elapsed, "by_model": runtime_by_model},
        "frozen_models": {name: bundle["paths"] for name, bundle in frozen_bundles.items()},
        "note": (
            "参数来自 CALCE 公开 DST 数据的自主最小二乘辨识；OCV 来自 SP1，"
            "动态数据来自 SP2，属于同型号跨样品参考模型。训练 success 不代表参数唯一可靠。"
        ),
    }
    write_json(run.path / "training_metrics.json", summary)
    write_json(run.path / "parameter_quality.json", {
        name: bundle.get("quality", {}) for name, bundle in frozen_bundles.items()
    })
    run.write_config_snapshot({"identification": identification, "bounds": settings["bounds"]})
    run.write_summary(summary)
    run.log(f"models={list(frozen_bundles)}, quality={quality}")
    run.flush_log()
    print(f"identification run_id={run.run_id}")
    print("training:", {name: round(item["training_rmse_v"] * 1000, 3) for name, item in training_metrics.items() if item.get("training_rmse_v")})
    print("development:", {name: round(item["rmse_mv"], 3) for name, item in development_metrics.items()})
    print("quality:", quality)
    for name, bundle in frozen_bundles.items():
        print(name, bundle["parameters"].to_dict())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
