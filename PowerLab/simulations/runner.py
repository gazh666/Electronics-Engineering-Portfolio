"""统一仿真执行器。

四个接口：``run_operating_point`` / ``run_dc`` / ``run_ac`` / ``run_transient``。
每个接口都完成：参数校验 → 共享库串行求解 → 波形复制 → 数据质量检查
→ 组装 :class:`SimulationResult`。求解失败直接抛异常，绝不返回空数据伪装成功。
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any
from uuid import uuid4

import pandas as pd

from analysis import waveform_quality
from circuits.validators import (
    ac_sweep,
    dc_sweep,
    temperature_celsius,
    transient_max_time,
    transient_parameters,
)

from .backend import (
    DEFAULT_TEMPERATURE_C,
    analysis_command,
    backend_info,
    create_simulator,
    dc_source_key,
    full_netlist,
    simulation_lock,
)
from .exceptions import InvalidWaveformError, SimulationError, SimulationExecutionError
from .models import AnalysisType, SimulationResult
from .waveform_extractor import (
    analysis_branches,
    analysis_nodes,
    branch_waveform,
    extract_ac_frequency,
    extract_ac_node_parts,
    extract_ac_branch_parts,
    extract_dc_sweep,
    extract_operating_point_branches,
    extract_operating_point_nodes,
    extract_transient_time,
    node_waveform,
    require_equal_lengths,
)

BRANCH_DIRECTION_NOTE = (
    "SPICE i(Vsource) is positive when current flows from the positive node "
    "through the source to the negative node; subtract/negate it to obtain "
    "the current delivered to a passive load (never use abs())."
)

SOLVER_WARNING_NOTE = (
    "PySpice 1.5 shared-library backend does not expose ngspice solver warnings; "
    "an empty list means 'not reported', not 'no warnings occurred'."
)


def new_run_id() -> str:
    """生成唯一运行编号。"""
    return f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"


def _circuit_title(circuit: Any) -> str:
    title = getattr(circuit, "title", None)
    if isinstance(title, str) and title.strip():
        return title.strip()
    return type(circuit).__name__


def _base_metadata(
    *,
    circuit: Any,
    analysis_type: AnalysisType,
    command: str,
    node_names: list[str],
    branch_names: list[str],
    quality: dict[str, Any],
    total_elapsed_ms: float,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "analysis_command": command,
        "node_names": node_names,
        "branch_names": branch_names,
        "branch_current_sign_convention": BRANCH_DIRECTION_NOTE,
        "environment": backend_info(),
        "solver_warnings": [],
        "solver_warnings_note": SOLVER_WARNING_NOTE,
        "quality": quality,
        "total_elapsed_ms": total_elapsed_ms,
        "simulation_temperature_c": None,
    }
    if extra:
        metadata.update(extra)
    return metadata


class SimulationRunner:
    """真实 SPICE 仿真执行器（共享库串行）。"""

    def __init__(self, temperature_c: float = DEFAULT_TEMPERATURE_C) -> None:
        self.temperature_c = temperature_celsius(temperature_c)

    # ------------------------------------------------------------------ OP
    def run_operating_point(
        self,
        circuit: Any,
        *,
        parameters: dict[str, Any] | None = None,
    ) -> SimulationResult:
        started = time.perf_counter()
        with simulation_lock():
            simulator = create_simulator(circuit, self.temperature_c)
            solve_started = time.perf_counter()
            try:
                analysis = simulator.operating_point()
            except Exception as exc:  # noqa: BLE001
                raise SimulationExecutionError(
                    f"operating point simulation failed for {_circuit_title(circuit)}: {exc}"
                ) from exc
            duration_ms = (time.perf_counter() - solve_started) * 1000.0

            nodes = extract_operating_point_nodes(analysis)
            branches = extract_operating_point_branches(analysis)
            netlist = full_netlist(circuit, AnalysisType.OP, self.temperature_c)

        quality = waveform_quality.assess_operating_point(nodes, branches)
        try:
            waveform_quality.ensure_valid(quality, "operating point")
        except ValueError as exc:
            raise InvalidWaveformError(str(exc)) from exc

        row: dict[str, float] = {}
        units: dict[str, str] = {}
        for name, value in nodes.items():
            column = f"{name}_v"
            row[column] = value
            units[column] = "V"
        for name, value in branches.items():
            column = f"{name}_branch_current_a"
            row[column] = value
            units[column] = "A"

        metadata = _base_metadata(
            circuit=circuit,
            analysis_type=AnalysisType.OP,
            command=analysis_command(AnalysisType.OP),
            node_names=sorted(nodes),
            branch_names=sorted(branches),
            quality=quality,
            total_elapsed_ms=(time.perf_counter() - started) * 1000.0,
        )
        metadata["simulation_temperature_c"] = self.temperature_c

        return SimulationResult(
            run_id=new_run_id(),
            circuit_name=_circuit_title(circuit),
            analysis_type=AnalysisType.OP,
            backend=backend_info()["backend"],
            data=pd.DataFrame([row]),
            circuit_netlist=netlist,
            duration_ms=duration_ms,
            parameters=dict(parameters or {}),
            units=units,
            metadata=metadata,
        )

    # ------------------------------------------------------------------ DC
    def run_dc(
        self,
        circuit: Any,
        source_name: str,
        start: float,
        stop: float,
        step: float,
        *,
        parameters: dict[str, Any] | None = None,
    ) -> SimulationResult:
        if not isinstance(source_name, str) or not source_name.strip():
            raise ValueError("source_name must be a non-empty string")
        source_name = source_name.strip()
        start_v, stop_v, step_v = dc_sweep(start, stop, step, name="dc_sweep")

        started = time.perf_counter()
        with simulation_lock():
            simulator = create_simulator(circuit, self.temperature_c)
            solve_started = time.perf_counter()
            try:
                analysis = simulator.dc(**{dc_source_key(source_name): slice(start_v, stop_v, step_v)})
            except Exception as exc:  # noqa: BLE001
                raise SimulationExecutionError(
                    f"DC sweep simulation failed for {_circuit_title(circuit)}: {exc}"
                ) from exc
            duration_ms = (time.perf_counter() - solve_started) * 1000.0

            sweep = extract_dc_sweep(analysis)
            nodes = analysis_nodes(analysis)
            branches = analysis_branches(analysis)
            node_values = {name: node_waveform(analysis, name) for name in nodes}
            branch_values = {
                name: branch_waveform(analysis, name) for name in branches
            }
            netlist = full_netlist(
                circuit,
                AnalysisType.DC,
                self.temperature_c,
                source_name=source_name,
                start=start_v,
                stop=stop_v,
                step=step_v,
            )

        columns: dict[str, Any] = {"sweep_v": sweep}
        columns.update({f"{name}_v": values for name, values in node_values.items()})
        columns.update(
            {f"{name}_branch_current_a": values for name, values in branch_values.items()}
        )
        quality = waveform_quality.assess_dc(
            sweep,
            {key: value for key, value in columns.items() if key != "sweep_v"},
            start_v,
            stop_v,
            step_v,
        )
        try:
            waveform_quality.ensure_valid(quality, "DC sweep")
        except ValueError as exc:
            raise InvalidWaveformError(str(exc)) from exc

        units = {"sweep_v": "V"}
        for name in node_values:
            units[f"{name}_v"] = "V"
        for name in branch_values:
            units[f"{name}_branch_current_a"] = "A"

        data = pd.DataFrame(columns)
        require_equal_lengths(**{key: data[key].to_numpy() for key in data.columns})

        metadata = _base_metadata(
            circuit=circuit,
            analysis_type=AnalysisType.DC,
            command=analysis_command(
                AnalysisType.DC,
                source_name=source_name,
                start=start_v,
                stop=stop_v,
                step=step_v,
            ),
            node_names=nodes,
            branch_names=branches,
            quality=quality,
            total_elapsed_ms=(time.perf_counter() - started) * 1000.0,
            extra={
                "sweep_source": source_name,
                "sweep_start_v": start_v,
                "sweep_stop_v": stop_v,
                "sweep_step_v": step_v,
                "simulation_temperature_c": self.temperature_c,
            },
        )

        return SimulationResult(
            run_id=new_run_id(),
            circuit_name=_circuit_title(circuit),
            analysis_type=AnalysisType.DC,
            backend=backend_info()["backend"],
            data=data,
            circuit_netlist=netlist,
            duration_ms=duration_ms,
            parameters=dict(parameters or {}),
            units=units,
            metadata=metadata,
        )

    # ------------------------------------------------------------------ AC
    def run_ac(
        self,
        circuit: Any,
        start_hz: float,
        stop_hz: float,
        points_per_decade: int = 50,
        *,
        variation: str = "dec",
        parameters: dict[str, Any] | None = None,
    ) -> SimulationResult:
        start, stop, points, variation = ac_sweep(
            start_hz, stop_hz, points_per_decade, variation=variation
        )

        started = time.perf_counter()
        with simulation_lock():
            simulator = create_simulator(circuit, self.temperature_c)
            solve_started = time.perf_counter()
            try:
                analysis = simulator.ac(
                    variation=variation,
                    number_of_points=points,
                    start_frequency=start,
                    stop_frequency=stop,
                )
            except Exception as exc:  # noqa: BLE001
                raise SimulationExecutionError(
                    f"AC simulation failed for {_circuit_title(circuit)}: {exc}"
                ) from exc
            duration_ms = (time.perf_counter() - solve_started) * 1000.0

            frequency = extract_ac_frequency(analysis)
            nodes = analysis_nodes(analysis)
            branches = analysis_branches(analysis)
            node_parts = {name: extract_ac_node_parts(analysis, name) for name in nodes}
            branch_parts = {
                name: extract_ac_branch_parts(analysis, name) for name in branches
            }
            netlist = full_netlist(
                circuit,
                AnalysisType.AC,
                self.temperature_c,
                start_hz=start,
                stop_hz=stop,
                points_per_decade=points,
                variation=variation,
            )

        columns: dict[str, Any] = {"frequency_hz": frequency}
        for name, (real, imag) in node_parts.items():
            columns[f"{name}_real_v"] = real
            columns[f"{name}_imag_v"] = imag
        for name, (real, imag) in branch_parts.items():
            columns[f"{name}_real_a"] = real
            columns[f"{name}_imag_a"] = imag

        complex_pairs = {f"V({name})": parts for name, parts in node_parts.items()}
        complex_pairs.update({f"I({name})": parts for name, parts in branch_parts.items()})
        quality = waveform_quality.assess_ac(
            frequency,
            {key: value for key, value in columns.items() if key != "frequency_hz"},
            start_hz=start,
            stop_hz=stop,
            complex_pairs=complex_pairs,
        )
        try:
            waveform_quality.ensure_valid(quality, "AC sweep")
        except ValueError as exc:
            raise InvalidWaveformError(str(exc)) from exc

        units = {"frequency_hz": "Hz"}
        for name in node_parts:
            units[f"{name}_real_v"] = "V"
            units[f"{name}_imag_v"] = "V"
        for name in branch_parts:
            units[f"{name}_real_a"] = "A"
            units[f"{name}_imag_a"] = "A"

        data = pd.DataFrame(columns)

        metadata = _base_metadata(
            circuit=circuit,
            analysis_type=AnalysisType.AC,
            command=analysis_command(
                AnalysisType.AC,
                start_hz=start,
                stop_hz=stop,
                points_per_decade=points,
                variation=variation,
            ),
            node_names=nodes,
            branch_names=branches,
            quality=quality,
            total_elapsed_ms=(time.perf_counter() - started) * 1000.0,
            extra={
                "ac_start_hz": start,
                "ac_stop_hz": stop,
                "ac_points_per_decade": points,
                "ac_variation": variation,
                "complex_data_preserved": True,
                "simulation_temperature_c": self.temperature_c,
            },
        )

        return SimulationResult(
            run_id=new_run_id(),
            circuit_name=_circuit_title(circuit),
            analysis_type=AnalysisType.AC,
            backend=backend_info()["backend"],
            data=data,
            circuit_netlist=netlist,
            duration_ms=duration_ms,
            parameters=dict(parameters or {}),
            units=units,
            metadata=metadata,
        )

    # ------------------------------------------------------------- transient
    def run_transient(
        self,
        circuit: Any,
        step_s: float,
        end_s: float,
        start_s: float = 0.0,
        *,
        max_time: float | None = None,
        use_initial_condition: bool = False,
        parameters: dict[str, Any] | None = None,
    ) -> SimulationResult:
        start_t, end_t, step_t = transient_parameters(step_s, end_s, start_s)
        max_time_t = (
            None if max_time is None else transient_max_time(max_time, step_t)
        )
        uic = bool(use_initial_condition)

        started = time.perf_counter()
        with simulation_lock():
            simulator = create_simulator(circuit, self.temperature_c)
            solve_started = time.perf_counter()
            try:
                transient_kwargs: dict[str, Any] = {
                    "step_time": step_t,
                    "end_time": end_t,
                    "start_time": start_t,
                }
                if max_time_t is not None:
                    transient_kwargs["max_time"] = max_time_t
                if uic:
                    transient_kwargs["use_initial_condition"] = True
                analysis = simulator.transient(**transient_kwargs)
            except Exception as exc:  # noqa: BLE001
                raise SimulationExecutionError(
                    f"transient simulation failed for {_circuit_title(circuit)}: {exc}"
                ) from exc
            duration_ms = (time.perf_counter() - solve_started) * 1000.0

            time_s = extract_transient_time(analysis)
            nodes = analysis_nodes(analysis)
            branches = analysis_branches(analysis)
            node_values = {name: node_waveform(analysis, name) for name in nodes}
            branch_values = {
                name: branch_waveform(analysis, name) for name in branches
            }
            netlist = full_netlist(
                circuit,
                AnalysisType.TRANSIENT,
                self.temperature_c,
                step_s=step_t,
                end_s=end_t,
                start_s=start_t,
                max_time_s=max_time_t,
                use_initial_condition=uic,
            )

        columns: dict[str, Any] = {"time_s": time_s}
        columns.update({f"{name}_v": values for name, values in node_values.items()})
        columns.update(
            {f"{name}_branch_current_a": values for name, values in branch_values.items()}
        )
        quality = waveform_quality.assess_transient(
            time_s,
            {key: value for key, value in columns.items() if key != "time_s"},
            expected_end_s=end_t,
        )
        try:
            waveform_quality.ensure_valid(quality, "transient")
        except ValueError as exc:
            raise InvalidWaveformError(str(exc)) from exc

        units = {"time_s": "s"}
        for name in node_values:
            units[f"{name}_v"] = "V"
        for name in branch_values:
            units[f"{name}_branch_current_a"] = "A"

        data = pd.DataFrame(columns)

        metadata = _base_metadata(
            circuit=circuit,
            analysis_type=AnalysisType.TRANSIENT,
            command=analysis_command(
                AnalysisType.TRANSIENT,
                step_s=step_t,
                end_s=end_t,
                start_s=start_t,
                max_time_s=max_time_t,
                use_initial_condition=uic,
            ),
            node_names=nodes,
            branch_names=branches,
            quality=quality,
            total_elapsed_ms=(time.perf_counter() - started) * 1000.0,
            extra={
                "step_s": step_t,
                "end_s": end_t,
                "start_s": start_t,
                "max_time_s": max_time_t,
                "use_initial_condition": uic,
                "actual_end_s": float(data["time_s"].iloc[-1]),
                "nonuniform_sampling": bool(quality.get("nonuniform_sampling", False)),
                "simulation_temperature_c": self.temperature_c,
            },
        )

        return SimulationResult(
            run_id=new_run_id(),
            circuit_name=_circuit_title(circuit),
            analysis_type=AnalysisType.TRANSIENT,
            backend=backend_info()["backend"],
            data=data,
            circuit_netlist=netlist,
            duration_ms=duration_ms,
            parameters=dict(parameters or {}),
            units=units,
            metadata=metadata,
        )


def run_checked(callable_: Any, *args: Any, **kwargs: Any) -> SimulationResult:
    """便捷包装：把 ``SimulationError`` 原样上抛，其余异常统一分类。"""
    try:
        return callable_(*args, **kwargs)
    except SimulationError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SimulationExecutionError(f"simulation runner failed: {exc}") from exc
