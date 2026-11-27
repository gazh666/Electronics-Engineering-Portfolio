"""开关级闭环/开环 Buck 运行器（真实 ngspice 瞬态）。

与 ``averaged_model_runner`` 的区别：
- 本模块使用第四阶段 MOSFET/SW 开关器件与非理想无源器件；
- 控制器是网表中的行为源，每个时间步真实读取 ``V(out)`` 并改变 PWM；
- 输出包含开关纹波、栅极驱动与逐周期统计，必须标记 ``spice_simulation``。

开环模式使用固定占空比 PULSE 源。开环占空比可由平均模型离线校准得到，
但本模块不会把它描述为实时闭环。
"""

from __future__ import annotations

import gzip
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from analysis.stability_analysis import solve_operating_duty
from circuits.closed_loop_buck import ClosedLoopLayout, build_closed_loop_buck
from circuits.closed_loop_config import ClosedLoopConfig
from circuits.validators import positive_number
from control.pwm_modulator import analyze_pwm_pulses, measure_duty_windows
from simulations.averaged_model_runner import averaged_parameters_from_config
from simulations.exceptions import SimulationExecutionError
from simulations.runner import SimulationRunner
from storage.result_store import write_dataframe, write_json, save_config_snapshot

DATA_SOURCE_SPICE = "spice_simulation"
STAGE7_RESULTS_ROOT = Path(__file__).resolve().parents[1] / "results" / "stage7"


@dataclass
class ClosedLoopRun:
    name: str
    run_id: str
    mode: str
    variant: str
    data: pd.DataFrame
    metadata: dict[str, Any]
    layout: ClosedLoopLayout
    netlist: str
    config_snapshot: dict[str, Any]
    duration_ms: float
    pwm_cycles: pd.DataFrame | None = None
    data_source: str = DATA_SOURCE_SPICE

    @property
    def point_count(self) -> int:
        return int(len(self.data))

    @property
    def pwm_statistics(self) -> dict[str, Any]:
        return self.metadata.get("pwm_statistics", {})


def _series(frame: pd.DataFrame, name: str, default: float = math.nan) -> np.ndarray:
    if name in frame.columns:
        return frame[name].to_numpy(dtype=float)
    return np.full(len(frame), float(default))


def _require(frame: pd.DataFrame, name: str) -> np.ndarray:
    if name not in frame.columns:
        raise KeyError(f"required SPICE column {name!r} is missing")
    return frame[name].to_numpy(dtype=float)


def _cycle_duty(time_s: np.ndarray, cycles: pd.DataFrame, period_s: float) -> np.ndarray:
    """把逐周期占空比映射回原始采样点。"""
    index = np.floor(time_s / period_s).astype(int)
    mapping = dict(zip(cycles["index"].astype(int), cycles["duty"].astype(float)))
    return np.array([mapping.get(int(item), math.nan) for item in index], dtype=float)


def _driver_current(frame: pd.DataFrame, layout: ClosedLoopLayout) -> np.ndarray:
    candidates = []
    if layout.mode == "closed_loop" and layout.variant in ("E", "D"):
        candidates = ["ecdrv_branch_current_a"]
    elif layout.mode == "open_loop" and layout.variant in ("E", "D"):
        candidates = ["vdrv_branch_current_a"]
    elif layout.variant == "SW" and layout.mode == "closed_loop":
        candidates = ["bctrl_branch_current_a"]
    elif layout.variant == "SW":
        candidates = ["vpwm_branch_current_a"]
    for name in candidates:
        if name in frame.columns:
            return frame[name].to_numpy(dtype=float)
    return np.full(len(frame), math.nan)


def extract_waveform(frame: pd.DataFrame, layout: ClosedLoopLayout, config: ClosedLoopConfig) -> pd.DataFrame:
    """把原始 SPICE 列转换成任务书要求的统一步形列。"""
    time_s = _require(frame, "time_s")
    vout = _require(frame, "out_v")
    vin = _series(frame, "vin_v")
    sw = _series(frame, "sw_v")
    gate = _series(frame, "gate_v")
    drain = _series(frame, "drain_v")
    il = _require(frame, "vlsense_branch_current_a")
    ic = _series(frame, "vcsense_branch_current_a")
    iin = _require(frame, "vdsense_branch_current_a")
    iload = _require(frame, "vloadsense_branch_current_a")

    columns: dict[str, Any] = {
        "time_s": time_s,
        "vout_v": vout,
        "vin_v": vin,
        "sw_v": sw,
        "il_a": il,
        "ic_a": ic,
        "iin_a": iin,
        "iload_a": iload,
        "vds_v": drain - sw,
        "data_source": DATA_SOURCE_SPICE,
    }
    if layout.variant in ("E", "D"):
        columns["vgs_v"] = gate - sw
    elif layout.mode == "closed_loop" and "ctrl_v" in frame.columns:
        columns["vgs_v"] = _series(frame, "ctrl_v")
    else:
        columns["vgs_v"] = gate
    columns["driver_current_a"] = _driver_current(frame, layout)

    if layout.mode == "closed_loop":
        columns.update(
            {
                "vref_v": _require(frame, "ref_v"),
                "verr_v": _require(frame, "err_v"),
                "ff_v": _require(frame, "ff_v"),
                "prop_v": _require(frame, "prop_v"),
                "integral_v": _require(frame, "integ_v"),
                "raw_v": _require(frame, "raw_v"),
                "duty_cmd_v": _require(frame, "duty_v"),
                "pwm_v": _require(frame, "pwm_v"),
                "carrier_v": _series(frame, "ramp_v"),
            }
        )
        pwm_signal = columns["pwm_v"]
    else:
        drive = 10.0 if layout.variant in ("E", "D") else 5.0
        pwm_signal = np.clip(gate / drive, 0.0, 1.0)
        columns["pwm_v"] = pwm_signal

    data = pd.DataFrame(columns)
    period = config.period_s
    cycles, statistics = analyze_pwm_pulses(
        time_s, np.asarray(pwm_signal, dtype=float), period, threshold=0.5
    )
    duty_cycle = _cycle_duty(time_s, cycles, period)
    data["pwm_duty_cycle"] = duty_cycle
    delta = (vin - vout) * duty_cycle * period / config.power_stage.inductor.inductance_h
    data["inductor_ripple_a"] = delta
    data["inductor_valley_a"] = il - 0.5 * delta
    data["ccm"] = (data["inductor_valley_a"] > 0.0).astype(float)
    return data, cycles, statistics


def run_closed_loop(
    config: ClosedLoopConfig,
    *,
    mode: str = "closed_loop",
    runner: SimulationRunner | None = None,
    pwm_window_s: float = 1e-3,
) -> ClosedLoopRun:
    """执行一次真实 SPICE 闭环或开环瞬态仿真。"""
    if not isinstance(config, ClosedLoopConfig):
        raise ValueError("config must be ClosedLoopConfig")
    circuit, layout = build_closed_loop_buck(config, mode=mode)
    executor = runner or SimulationRunner(temperature_c=config.temperature_c)
    result = executor.run_transient(
        circuit,
        step_s=config.step_time_s,
        end_s=config.end_time_s,
        max_time=config.max_step_time_s,
        use_initial_condition=True,
        parameters={
            "stage": 7,
            "variant": config.variant,
            "mode": mode,
            "controller": config.controller.to_dict(),
            "soft_start": config.soft_start.to_dict(),
            "carrier": config.carrier.to_dict(),
        },
    )
    data, cycles, statistics = extract_waveform(result.data, layout, config)
    # 启动前 1 ms 的栅极振铃会产生多次/窄脉冲，单独统计，不混入稳态质量判断。
    startup_exclusion = 1e-3 if config.end_time_s > 2e-3 else 0.0
    steady_mask = data["time_s"].to_numpy() >= startup_exclusion
    if steady_mask.sum() > 100:
        _, steady_statistics = analyze_pwm_pulses(
            data["time_s"].to_numpy()[steady_mask],
            data["pwm_v"].to_numpy(dtype=float)[steady_mask],
            config.period_s,
            threshold=0.5,
        )
    else:
        steady_statistics = statistics
    duty_windows = measure_duty_windows(
        data["time_s"].to_numpy(), data["pwm_v"].to_numpy(), pwm_window_s
    )
    finite_vout = np.isfinite(data["vout_v"].to_numpy())
    quality = {
        "finite_vout_fraction": float(np.mean(finite_vout)),
        "finite_il_fraction": float(np.mean(np.isfinite(data["il_a"].to_numpy()))),
        "minimum_vout_v": float(np.nanmin(data["vout_v"])),
        "maximum_vout_v": float(np.nanmax(data["vout_v"])),
        "minimum_il_a": float(np.nanmin(data["il_a"])),
        "maximum_il_a": float(np.nanmax(data["il_a"])),
        "ccm_fraction": float(data["ccm"].mean()),
        "pwm_cycles": int(statistics.cycles),
        "pwm_valid": bool(statistics.valid),
    }
    metadata = {
        "stage": 7,
        "run_id": result.run_id,
        "name": config.name,
        "mode": mode,
        "variant": config.variant,
        "data_source": DATA_SOURCE_SPICE,
        "model_note": (
            "switching SPICE waveform with behavioral PI controller; "
            "not an averaged model"
        ),
        "circuit_name": result.circuit_name,
        "analysis_type": result.analysis_type.value,
        "backend": result.backend,
        "analysis_command": result.metadata.get("analysis_command"),
        "environment": result.metadata.get("environment", {}),
        "solver_warnings": result.metadata.get("solver_warnings", []),
        "solver_warnings_note": result.metadata.get("solver_warnings_note"),
        "step_time_s": config.step_time_s,
        "max_step_time_s": config.max_step_time_s,
        "end_time_s": config.end_time_s,
        "actual_end_s": float(data["time_s"].iloc[-1]),
        "point_count": int(len(data)),
        "duration_ms": result.duration_ms,
        "closed_loop_config": config.to_dict(),
        "layout": layout.to_dict(),
        "pwm_statistics": statistics.to_dict(),
        "pwm_statistics_after_startup": steady_statistics.to_dict(),
        "pwm_startup_exclusion_s": startup_exclusion,
        "duty_windows": duty_windows.to_dict(orient="records"),
        "quality": quality,
        "open_loop_duty_cycle": config.open_loop_duty_cycle if mode == "open_loop" else None,
        "open_loop_calibration": (
            "offline average-model calibration (not real-time closed loop)"
            if mode == "open_loop"
            else None
        ),
        "waveform_columns": list(data.columns),
        "derived_quantities": {
            "vgs_v": "V(gate)-V(sw) for MOSFET; V(gate) for the SW model",
            "vds_v": "V(drain)-V(sw)",
            "driver_current_a": "SPICE branch current of the gate-drive source",
            "ccm": "valley current from instantaneous iL and cycle duty",
        },
        "raw_spice_columns": list(result.data.columns),
    }
    return ClosedLoopRun(
        name=config.name,
        run_id=result.run_id,
        mode=mode,
        variant=config.variant,
        data=data,
        metadata=metadata,
        layout=layout,
        netlist=result.circuit_netlist,
        config_snapshot=config.to_dict(),
        duration_ms=result.duration_ms,
        pwm_cycles=cycles,
    )


def calibrated_open_loop_duty(
    config: ClosedLoopConfig, *, target_v: float | None = None
) -> float:
    """用平均模型离线求开环固定占空比（不是实时闭环搜索结果）。"""
    parameters = averaged_parameters_from_config(config)
    target = config.target_voltage_v if target_v is None else positive_number(target_v, "target_v")
    return solve_operating_duty(parameters, target)


#: 收敛失败时依次尝试的内部最大步长（秒）。不改变仿真窗口，只放宽数值步长。
STEP_FALLBACK_CANDIDATES_S: tuple[float, ...] = (50e-9, 200e-9, 100e-9)


def run_closed_loop_with_fallback(
    config: ClosedLoopConfig,
    *,
    mode: str = "closed_loop",
    runner: SimulationRunner | None = None,
    candidates: tuple[float, ...] = STEP_FALLBACK_CANDIDATES_S,
) -> ClosedLoopRun:
    """先按配置步长运行，失败时换更粗的最大步长重试并记录真实回退。

    只放宽数值步长，功率级、控制器、负载与输入完全不变；实际使用的步长写入
    ``metadata["step_fallback"]``，禁止把回退结果冒充原始配置。
    """
    steps: list[float | None] = [None]
    steps.extend(item for item in candidates if item != config.step_time_s)
    errors: list[dict[str, Any]] = []
    for step in steps:
        candidate = (
            config
            if step is None
            else config.with_timing(
                config.end_time_s, step_time_s=step, max_step_time_s=step
            )
        )
        try:
            run = run_closed_loop(candidate, mode=mode, runner=runner)
        except SimulationExecutionError as error:
            errors.append(
                {
                    "step_time_s": candidate.step_time_s,
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                }
            )
            continue
        run.metadata["step_fallback"] = {
            "requested_step_time_s": config.step_time_s,
            "used_step_time_s": candidate.step_time_s,
            "attempts": errors + [{"step_time_s": candidate.step_time_s, "status": "OK"}],
        }
        return run
    raise SimulationExecutionError(
        "closed-loop transient failed for all step candidates: "
        + "; ".join(
            f"{item['step_time_s']:.3e} s -> {item['error_message']}" for item in errors
        )
    )



def save_closed_loop_run(
    run: ClosedLoopRun,
    *,
    root: Path = STAGE7_RESULTS_ROOT,
    save_waveform: bool = False,
    extra_metadata: dict[str, Any] | None = None,
) -> Path:
    """保存一次运行：metadata、配置快照、网表、PWM 周期表与可选原始波形。"""
    directory = Path(root) / "runs" / f"run_{run.run_id}"
    directory.mkdir(parents=True, exist_ok=True)
    metadata = dict(run.metadata)
    if extra_metadata:
        metadata.update(extra_metadata)
    metadata["saved_at"] = datetime.now().isoformat(timespec="seconds")
    metadata["files"] = {
        "metadata.json": "run metadata, environment, layout, PWM statistics",
        "config_snapshot.yaml": "closed-loop configuration snapshot",
        "circuit.cir": "netlist including analysis command",
        "pwm_cycles.csv": "per-cycle PWM statistics",
    }
    if save_waveform:
        metadata["files"]["waveform.csv.gz"] = "gzip compressed switching waveform"
    write_json(directory / "metadata.json", metadata)
    save_config_snapshot(directory / "config_snapshot.yaml", run.config_snapshot)
    (directory / "circuit.cir").write_text(run.netlist, encoding="utf-8")
    if run.pwm_cycles is not None:
        write_dataframe(directory / "pwm_cycles.csv", run.pwm_cycles)
    if save_waveform:
        with gzip.open(directory / "waveform.csv.gz", "wt", encoding="utf-8", newline="") as handle:
            run.data.to_csv(handle, index=False, float_format="%.9g")
    return directory


__all__ = [
    "ClosedLoopRun",
    "DATA_SOURCE_SPICE",
    "STAGE7_RESULTS_ROOT",
    "STEP_FALLBACK_CANDIDATES_S",
    "calibrated_open_loop_duty",
    "extract_waveform",
    "run_closed_loop",
    "run_closed_loop_with_fallback",
    "save_closed_loop_run",
]
