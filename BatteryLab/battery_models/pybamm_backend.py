"""PyBaMM 统一轻量封装。

BatteryLab 只做应用层封装：模型、参数集、求解器均由 PyBaMM 提供，
电化学求解器本身不是本项目自主开发。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np
import pandas as pd
import pybamm

SUPPORTED_MODELS = ("SPM", "Thevenin")

WAVEFORM_COLUMNS = ("time_s", "voltage_v", "current_a", "soc", "temperature_c")


class BatteryModelError(ValueError):
    """模型或配置非法。"""


class SimulationRunError(RuntimeError):
    """真实求解失败。"""


@dataclass
class BatterySimulationConfig:
    """一次电池仿真的配置。"""

    model_name: str = "SPM"
    duration_s: float = 3600.0
    parameter_set: str | None = None
    initial_soc: float | None = None
    c_rate: float | None = None
    temperature_c: float | None = None
    output_points: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def validate(self, require_duration: bool = True) -> None:
        if self.model_name not in SUPPORTED_MODELS:
            raise BatteryModelError(f"不支持的模型: {self.model_name!r}，可选 {SUPPORTED_MODELS}")
        if require_duration and (not np.isfinite(self.duration_s) or self.duration_s <= 0):
            raise BatteryModelError("duration_s 必须是有限正数")
        if self.initial_soc is not None and not 0.0 < float(self.initial_soc) < 1.0:
            raise BatteryModelError("initial_soc 必须在 (0, 1) 开区间内")
        if self.c_rate is not None and float(self.c_rate) <= 0:
            raise BatteryModelError("c_rate 必须为正")
        if self.output_points is not None and int(self.output_points) < 2:
            raise BatteryModelError("output_points 至少为 2")


class PyBaMMBackend:
    """模型创建、真实求解与波形提取。"""

    def __init__(self, model_name: str = "SPM") -> None:
        if model_name not in SUPPORTED_MODELS:
            raise BatteryModelError(f"不支持的模型: {model_name!r}")
        self.model_name = model_name

    # ------------------------------------------------------------------ 模型
    def create_model(self, model_name: str | None = None) -> pybamm.BaseModel:
        name = model_name or self.model_name
        if name == "SPM":
            return pybamm.lithium_ion.SPM()
        if name == "Thevenin":
            return pybamm.equivalent_circuit.Thevenin()
        raise BatteryModelError(f"不支持的模型: {name!r}")

    def create_parameter_values(
        self,
        model: pybamm.BaseModel,
        config: BatterySimulationConfig,
    ) -> pybamm.ParameterValues:
        if config.parameter_set:
            try:
                values = pybamm.ParameterValues(config.parameter_set)
            except Exception as exc:  # noqa: BLE001 - 参数集不存在需要如实报错
                available = ", ".join(sorted(pybamm.parameter_sets.keys()))
                raise BatteryModelError(
                    f"参数集 {config.parameter_set!r} 不可用: {exc}; 可用参数集: {available}"
                ) from exc
        else:
            values = model.default_parameter_values

        if config.initial_soc is not None:
            soc = float(config.initial_soc)
            if "Initial SoC" in values.keys():
                values.update({"Initial SoC": soc})
            else:
                try:
                    values.set_initial_stoichiometries(soc)
                except Exception as exc:  # noqa: BLE001
                    raise BatteryModelError(f"无法设置初始 SOC={soc}: {exc}") from exc

        if config.temperature_c is not None and "Ambient temperature [K]" in values.keys():
            kelvin = float(config.temperature_c) + 273.15
            values.update({"Ambient temperature [K]": kelvin})
            if "Initial temperature [K]" in values.keys():
                values.update({"Initial temperature [K]": kelvin})
        return values

    # ------------------------------------------------------------------ 求解
    def run(
        self,
        config: BatterySimulationConfig,
        experiment: pybamm.Experiment | None = None,
    ) -> dict[str, Any]:
        config.validate(require_duration=experiment is None)
        model = self.create_model(config.model_name)
        parameter_values = self.create_parameter_values(model, config)

        simulation = pybamm.Simulation(
            model,
            experiment=experiment,
            parameter_values=parameter_values,
        )
        wall_start = time.perf_counter()
        try:
            if experiment is None:
                if config.output_points:
                    t_eval = np.linspace(0.0, float(config.duration_s), int(config.output_points))
                    solution = simulation.solve(t_eval=t_eval)
                else:
                    solution = simulation.solve([0.0, float(config.duration_s)])
            else:
                solution = simulation.solve()
        except Exception as exc:  # noqa: BLE001 - 求解失败必须保留真实原因
            raise SimulationRunError(f"PyBaMM 求解失败: {exc}") from exc
        wall_time_s = time.perf_counter() - wall_start

        waveform = self.extract_waveform(solution)
        t_end = float(waveform["time_s"].iloc[-1])
        metadata = {
            "model_name": model.name,
            "model_key": config.model_name,
            "parameter_set_requested": config.parameter_set,
            "parameter_set_effective": self.describe_parameter_set(config.parameter_set, parameter_values),
            "solver": type(simulation.solver).__name__,
            "duration_requested_s": float(config.duration_s),
            "time_start_s": float(waveform["time_s"].iloc[0]),
            "time_end_s": t_end,
            "points": int(len(waveform)),
            "termination": str(solution.termination),
            "wall_time_s": wall_time_s,
            "initial_soc_requested": config.initial_soc,
            "temperature_c_requested": config.temperature_c,
            "experiment_steps": (
                len(experiment.operating_conditions)
                if experiment is not None and hasattr(experiment, "operating_conditions")
                else 0
            ),
            "pybamm_version": pybamm.__version__,
            "data_source": "pybamm_simulation",
        }
        return {
            "solution": solution,
            "simulation": simulation,
            "waveform": waveform,
            "metadata": metadata,
        }

    # ------------------------------------------------------------ 参数集信息
    @staticmethod
    def describe_parameter_set(requested: str | None, values: pybamm.ParameterValues) -> str:
        """尽量给出真实参数集名称：按官方参数集逐项比对实际数值。"""
        if requested:
            return requested
        keys = ("Nominal cell capacity [A.h]", "Lower voltage cut-off [V]", "Upper voltage cut-off [V]")
        try:
            targets = [float(values[key]) for key in keys]
        except Exception:  # noqa: BLE001 - 参数集可能使用函数或缺少字段
            return "model_default"
        for name in sorted(pybamm.parameter_sets):
            try:
                candidate = pybamm.ParameterValues(name)
                candidate_values = [float(candidate[key]) for key in keys]
            except Exception:  # noqa: BLE001
                continue
            if all(abs(a - b) < 1e-9 for a, b in zip(targets, candidate_values)):
                return f"{name} (matched_by_nominal_values)"
        return "model_default"

    # ------------------------------------------------------------ 波形提取
    def extract_waveform(self, solution: pybamm.Solution) -> pd.DataFrame:
        def entries(name: str) -> np.ndarray | None:
            try:
                data = np.asarray(solution[name].entries, dtype=float)
            except Exception:  # noqa: BLE001 - 变量不存在属正常情况
                return None
            if data.ndim > 1:
                data = np.squeeze(data)
            if data.ndim > 1:
                data = data[:, 0]
            return data

        time_s = entries("Time [s]")
        voltage_v = entries("Voltage [V]")
        current_a = entries("Current [A]")
        if time_s is None or voltage_v is None or current_a is None:
            raise SimulationRunError("求解结果缺少 Time/Voltage/Current 变量")
        if not (len(time_s) == len(voltage_v) == len(current_a)):
            raise SimulationRunError("求解结果变量长度不一致")
        if not np.isfinite(time_s).all() or not np.isfinite(voltage_v).all() or not np.isfinite(current_a).all():
            raise SimulationRunError("求解结果含有非有限数值")

        frame = pd.DataFrame(
            {
                "time_s": time_s,
                "voltage_v": voltage_v,
                "current_a": current_a,
            }
        )

        def aligned(name: str) -> np.ndarray | None:
            data = entries(name)
            if data is None or data.shape != time_s.shape:
                return None
            return data

        soc = aligned("SoC")
        frame["soc"] = soc if soc is not None else np.nan
        temperature = aligned("Cell temperature [degC]")
        if temperature is None:
            temperature = aligned("Cell temperature [C]")
        frame["temperature_c"] = temperature if temperature is not None else np.nan
        return frame


def run_thevenin_teaching_case(
    *,
    capacity_ah: float,
    r0_ohm: float,
    branches: Sequence[tuple[float, float]],
    ocv_v: float,
    initial_soc: float,
    schedule: Sequence[tuple[float, float]],
    output_time_s: Any,
    lower_voltage_v: float = 3.0,
    upper_voltage_v: float = 4.2,
    temperature_c: float = 25.0,
) -> dict[str, Any]:
    """用 PyBaMM 官方 Thevenin 模型复现教学 ECM 工况。

    ``branches`` 为 (R, C) 列表；``schedule`` 为 (时长 s, 电流 A) 列表，
    放电为正。仅做功能性交叉验证，不把 PyBaMM 结果描述为自主求解器输出。
    """
    if len(branches) not in (1, 2):
        raise BatteryModelError("PyBaMM Thevenin 对照仅支持 1 或 2 个 RC 支路")
    model = pybamm.equivalent_circuit.Thevenin(options={"number of rc elements": len(branches)})
    values = model.default_parameter_values
    updates: dict[str, Any] = {
        "Initial SoC": float(initial_soc),
        "Cell capacity [A.h]": float(capacity_ah),
        "Nominal cell capacity [A.h]": float(capacity_ah),
        "Lower voltage cut-off [V]": float(lower_voltage_v),
        "Upper voltage cut-off [V]": float(upper_voltage_v),
        "Open-circuit voltage [V]": lambda soc: float(ocv_v) + 0.0 * soc,
        "R0 [Ohm]": float(r0_ohm),
        "Ambient temperature [K]": float(temperature_c) + 273.15,
        "Initial temperature [K]": float(temperature_c) + 273.15,
        "Element-1 initial overpotential [V]": 0.0,
    }
    for index, (resistance, capacitance) in enumerate(branches, start=1):
        updates[f"R{index} [Ohm]"] = float(resistance)
        updates[f"C{index} [F]"] = float(capacitance)
        updates[f"Element-{index} initial overpotential [V]"] = 0.0
    values.update(updates, check_already_exists=False)

    steps: list[str] = []
    for duration, current in schedule:
        duration_text = f"{float(duration):g} seconds"
        if abs(float(current)) < 1e-12:
            steps.append(f"Rest for {duration_text}")
        elif current > 0:
            steps.append(f"Discharge at {float(current):g} A for {duration_text}")
        else:
            steps.append(f"Charge at {abs(float(current)):g} A for {duration_text}")
    experiment = pybamm.Experiment(steps)
    simulation = pybamm.Simulation(model, experiment=experiment, parameter_values=values)
    wall_start = time.perf_counter()
    try:
        solution = simulation.solve()
    except Exception as exc:  # noqa: BLE001
        raise SimulationRunError(f"PyBaMM Thevenin 求解失败: {exc}") from exc
    wall_time_s = time.perf_counter() - wall_start

    target_time = np.asarray(output_time_s, dtype=float)
    if not np.isfinite(target_time).all():
        raise BatteryModelError("输出时间含非有限数值")
    voltage = np.asarray(solution["Voltage [V]"](target_time), dtype=float).reshape(-1)
    soc = np.asarray(solution["SoC"](target_time), dtype=float).reshape(-1)
    if voltage.size != target_time.size or soc.size != target_time.size:
        raise SimulationRunError("PyBaMM 插值结果长度不一致")
    if not np.isfinite(voltage).all():
        raise SimulationRunError("PyBaMM 插值结果含非有限数值")

    current = np.zeros_like(target_time)
    elapsed = 0.0
    for duration, value in schedule:
        start = elapsed
        elapsed += float(duration)
        mask = (target_time >= start - 1e-12) & (target_time < elapsed - 1e-12)
        current[mask] = float(value)
    current[target_time >= elapsed - 1e-12] = float(schedule[-1][1])

    frame = pd.DataFrame(
        {
            "time_s": target_time,
            "voltage_v": voltage,
            "current_a": current,
            "soc": soc,
        }
    )
    return {
        "frame": frame,
        "solution": solution,
        "metadata": {
            "model": model.name,
            "model_family": "pybamm.equivalent_circuit.Thevenin",
            "number_of_rc_elements": len(branches),
            "parameter_set": "teaching_override_on_default",
            "data_source": "pybamm_simulation",
            "solver": type(simulation.solver).__name__,
            "points": int(target_time.size),
            "wall_time_s": wall_time_s,
            "termination": str(solution.termination),
            "schedule": [{"duration_s": float(d), "current_a": float(i)} for d, i in schedule],
            "pybamm_version": pybamm.__version__,
            "parameter_source": "educational_assumption",
        },
    }
