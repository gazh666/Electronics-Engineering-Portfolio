"""四电阻差分放大器（Task 7/8/9）。

Vout = (1 + R2/R1) * (Vhigh*R4 + Vref*R3)/(R3+R4) - (R2/R1)*Vlow
匹配条件 R2/R1 = R4/R3 = k 时：Vout = Vref + k*(Vhigh - Vlow)。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np
from PySpice.Spice.Netlist import Circuit

from circuits.opamp_models import OpAmpSpec, add_opamp
from circuits.spice_utils import run_operating_point
from sensing.voltage_decoder import amplifier_pin_common_mode, four_resistor_output


class DifferentialAmplifierError(ValueError):
    """差分放大器参数非法。"""


@dataclass(frozen=True)
class DifferentialAmplifierConfig:
    r1_ohm: float
    r2_ohm: float
    r3_ohm: float
    r4_ohm: float
    reference_v: float
    supply_v: float = 5.0

    def __post_init__(self) -> None:
        for label, value in (
            ("R1", self.r1_ohm),
            ("R2", self.r2_ohm),
            ("R3", self.r3_ohm),
            ("R4", self.r4_ohm),
            ("参考电压", self.reference_v),
            ("供电电压", self.supply_v),
        ):
            if not math.isfinite(value):
                raise DifferentialAmplifierError(f"{label} 必须有限")
        if min(self.r1_ohm, self.r2_ohm, self.r3_ohm, self.r4_ohm) <= 0.0:
            raise DifferentialAmplifierError("电阻必须为正")
        if self.supply_v <= 0.0:
            raise DifferentialAmplifierError("供电电压必须为正")

    @property
    def nominal_gain(self) -> float:
        return self.r2_ohm / self.r1_ohm

    @property
    def gain_mismatch_ratio(self) -> float:
        return (self.r4_ohm / self.r3_ohm) / self.nominal_gain

    @classmethod
    def from_config(cls, config: dict) -> "DifferentialAmplifierConfig":
        amp = config["differential_amplifier"]
        return cls(
            r1_ohm=float(amp["r1_ohm"]),
            r2_ohm=float(amp["r2_ohm"]),
            r3_ohm=float(amp["r3_ohm"]),
            r4_ohm=float(amp["r4_ohm"]),
            reference_v=float(amp["reference_voltage_v"]),
            supply_v=float(amp["supply_voltage_v"]),
        )

    def output(self, vhigh_v: float, vlow_v: float) -> float:
        return four_resistor_output(
            vhigh_v,
            vlow_v,
            r1_ohm=self.r1_ohm,
            r2_ohm=self.r2_ohm,
            r3_ohm=self.r3_ohm,
            r4_ohm=self.r4_ohm,
            reference_v=self.reference_v,
        )


def ideal_opamp_spec(config: DifferentialAmplifierConfig) -> OpAmpSpec:
    return OpAmpSpec(
        name="eop",
        model_kind="ideal",
        open_loop_gain=1_000_000.0,
        output_low_v=0.0,
        output_high_v=config.supply_v,
        input_common_mode_min_v=0.0,
        input_common_mode_max_v=config.supply_v,
    )


def teaching_opamp_spec(config: DifferentialAmplifierConfig, *, offset_v: float = 0.0, gbw_hz: float = 1_000_000.0) -> OpAmpSpec:
    return OpAmpSpec(
        name="eop",
        model_kind="teaching_nonideal",
        open_loop_gain=100_000.0,
        output_low_v=0.05,
        output_high_v=config.supply_v - 0.05,
        input_offset_v=offset_v,
        gain_bandwidth_hz=gbw_hz,
        input_common_mode_min_v=0.0,
        input_common_mode_max_v=config.supply_v,
    )


def build_differential_amplifier_circuit(
    vhigh_v: float,
    vlow_v: float,
    config: DifferentialAmplifierConfig,
    *,
    opamp: OpAmpSpec | None = None,
    high_source_name: str = "vhigh",
) -> Circuit:
    circuit = Circuit("BatteryLab differential amplifier")
    circuit.V(high_source_name, "hi", circuit.gnd, float(vhigh_v))
    circuit.V("vlow", "lo", circuit.gnd, float(vlow_v))
    circuit.V("vref", "vref", circuit.gnd, float(config.reference_v))
    circuit.R("1", "lo", "inm", config.r1_ohm)
    circuit.R("2", "out", "inm", config.r2_ohm)
    circuit.R("3", "hi", "inp", config.r3_ohm)
    circuit.R("4", "inp", "vref", config.r4_ohm)
    add_opamp(
        circuit,
        opamp or ideal_opamp_spec(config),
        output_node="out",
        non_inverting_node="inp",
        inverting_node="inm",
    )
    return circuit


def solve_differential(
    vhigh_v: float,
    vlow_v: float,
    config: DifferentialAmplifierConfig,
    *,
    opamp: OpAmpSpec | None = None,
) -> dict[str, float]:
    circuit = build_differential_amplifier_circuit(vhigh_v, vlow_v, config, opamp=opamp)
    solution = run_operating_point(circuit, ["out", "inp", "inm", "hi", "lo", "vref"])
    vout = solution["out"]
    theory = config.output(vhigh_v, vlow_v)
    # 输入网络电流（从电池/参考源看进去）
    i_r3 = (solution["hi"] - solution["inp"]) / config.r3_ohm
    i_r1 = (solution["lo"] - solution["inm"]) / config.r1_ohm
    i_r4 = (solution["inp"] - solution["vref"]) / config.r4_ohm
    pins = amplifier_pin_common_mode(
        vhigh_v,
        vlow_v,
        r1_ohm=config.r1_ohm,
        r2_ohm=config.r2_ohm,
        r3_ohm=config.r3_ohm,
        r4_ohm=config.r4_ohm,
        reference_v=config.reference_v,
    )
    return {
        "vhigh_v": float(vhigh_v),
        "vlow_v": float(vlow_v),
        "vout_v": float(vout),
        "theory_v": float(theory),
        "error_v": float(vout - theory),
        "vinp_v": solution["inp"],
        "vinm_v": solution["inm"],
        "vinp_theory_v": pins["v_inp_v"],
        "vinm_theory_v": pins["v_inm_v"],
        "common_mode_v": 0.5 * (vhigh_v + vlow_v),
        "pin_common_mode_v": 0.5 * (solution["inp"] + solution["inm"]),
        "i_high_input_a": float(i_r3),
        "i_low_input_a": float(i_r1),
        "i_reference_a": float(i_r4),
    }


def sweep_differential(
    differential_voltages_v: Sequence[float],
    *,
    common_mode_v: float,
    config: DifferentialAmplifierConfig,
    opamp: OpAmpSpec | None = None,
) -> list[dict[str, float]]:
    rows = []
    for vdiff in differential_voltages_v:
        vhigh = common_mode_v + 0.5 * float(vdiff)
        vlow = common_mode_v - 0.5 * float(vdiff)
        rows.append(solve_differential(vhigh, vlow, config, opamp=opamp))
    return rows


def sweep_common_mode(
    common_mode_voltages_v: Sequence[float],
    *,
    differential_v: float,
    config: DifferentialAmplifierConfig,
    opamp: OpAmpSpec | None = None,
) -> list[dict[str, float]]:
    rows = []
    for vcm in common_mode_voltages_v:
        vhigh = float(vcm) + 0.5 * float(differential_v)
        vlow = float(vcm) - 0.5 * float(differential_v)
        rows.append(solve_differential(vhigh, vlow, config, opamp=opamp))
    return rows


def differential_gain(rows: Sequence[dict[str, float]]) -> float:
    """由相邻差分点斜率估计实际差分增益。"""
    if len(rows) < 2:
        raise DifferentialAmplifierError("至少需要两个差分点")
    vdiff = np.array([row["vhigh_v"] - row["vlow_v"] for row in rows], dtype=float)
    vout = np.array([row["vout_v"] for row in rows], dtype=float)
    slope, _ = np.polyfit(vdiff, vout, 1)
    return float(slope)


def common_mode_gain(rows: Sequence[dict[str, float]]) -> float:
    if len(rows) < 2:
        raise DifferentialAmplifierError("至少需要两个共模点")
    vcm = np.array([row["common_mode_v"] for row in rows], dtype=float)
    vout = np.array([row["vout_v"] for row in rows], dtype=float)
    slope, _ = np.polyfit(vcm, vout, 1)
    return float(slope)


def cmrr_db(differential_gain_value: float, common_mode_gain_value: float) -> float | None:
    """CMRR = 20log10(|Ad/Acm|)。Acm 接近数值零时返回 None（只报告下界）。"""
    if abs(common_mode_gain_value) <= 1e-12:
        return None
    return 20.0 * math.log10(abs(differential_gain_value) / abs(common_mode_gain_value))


def cmrr_numeric_floor_db(differential_gain_value: float, resolution_v: float) -> float:
    """理想匹配模型的数值 CMRR 下界估计（受求解分辨率限制）。"""
    if resolution_v <= 0.0:
        raise DifferentialAmplifierError("分辨率必须为正")
    return 20.0 * math.log10(abs(differential_gain_value) / resolution_v)


def resistor_mismatch_values(
    config: DifferentialAmplifierConfig,
    tolerance_percent: float,
    rng: np.random.Generator,
) -> tuple[DifferentialAmplifierConfig, dict[str, float]]:
    """对四个电阻独立施加百分比容差，返回新配置与相对偏差。"""
    if tolerance_percent < 0.0:
        raise DifferentialAmplifierError("容差不能为负")
    fraction = tolerance_percent / 100.0
    draws = {name: float(rng.uniform(-fraction, fraction)) for name in ("r1", "r2", "r3", "r4")}
    new = DifferentialAmplifierConfig(
        r1_ohm=config.r1_ohm * (1.0 + draws["r1"]),
        r2_ohm=config.r2_ohm * (1.0 + draws["r2"]),
        r3_ohm=config.r3_ohm * (1.0 + draws["r3"]),
        r4_ohm=config.r4_ohm * (1.0 + draws["r4"]),
        reference_v=config.reference_v,
        supply_v=config.supply_v,
    )
    return new, draws


def build_differential_sweep_circuit(
    vcm_v: float,
    vdiff_v: float,
    config: DifferentialAmplifierConfig,
    *,
    opamp: OpAmpSpec | None = None,
) -> Circuit:
    """共模源与差分控制源分离，扫描时保持另一端条件不变。

    节点电压由两个行为电压源给出：
        V(hi) = V(cm) + 0.5*V(dctrl)
        V(lo) = V(cm) - 0.5*V(dctrl)
    """
    circuit = Circuit("BatteryLab differential amplifier sweep")
    circuit.V("cm", "cm", circuit.gnd, float(vcm_v))
    circuit.V("dctrl", "dctrl", circuit.gnd, float(vdiff_v))
    circuit.B("bhi", "hi", circuit.gnd, v="V(cm)+0.5*V(dctrl)")
    circuit.B("blo", "lo", circuit.gnd, v="V(cm)-0.5*V(dctrl)")
    circuit.V("vref", "vref", circuit.gnd, float(config.reference_v))
    circuit.R("1", "lo", "inm", config.r1_ohm)
    circuit.R("2", "out", "inm", config.r2_ohm)
    circuit.R("3", "hi", "inp", config.r3_ohm)
    circuit.R("4", "inp", "vref", config.r4_ohm)
    add_opamp(
        circuit,
        opamp or ideal_opamp_spec(config),
        output_node="out",
        non_inverting_node="inp",
        inverting_node="inm",
    )
    return circuit


def _rows_from_arrays(
    vhigh: np.ndarray,
    vlow: np.ndarray,
    out: np.ndarray,
    inp: np.ndarray,
    inm: np.ndarray,
    config: DifferentialAmplifierConfig,
) -> list[dict[str, float]]:
    rows = []
    for index in range(len(vhigh)):
        theory = config.output(float(vhigh[index]), float(vlow[index]))
        rows.append(
            {
                "vhigh_v": float(vhigh[index]),
                "vlow_v": float(vlow[index]),
                "vout_v": float(out[index]),
                "theory_v": float(theory),
                "error_v": float(out[index] - theory),
                "vinp_v": float(inp[index]),
                "vinm_v": float(inm[index]),
                "common_mode_v": float(0.5 * (vhigh[index] + vlow[index])),
                "pin_common_mode_v": float(0.5 * (inp[index] + inm[index])),
            }
        )
    return rows


def _sweep_grid(values: Sequence[float]) -> tuple[float, float, float]:
    array = np.asarray([float(value) for value in values], dtype=float)
    if array.size == 1:
        return float(array[0]), float(array[0]) + 1e-3, 1e-3
    start, stop = float(array.min()), float(array.max())
    step = (stop - start) / (array.size - 1)
    return start, stop, step


def sweep_differential_fast(
    differential_voltages_v: Sequence[float],
    *,
    common_mode_v: float,
    config: DifferentialAmplifierConfig,
    opamp: OpAmpSpec | None = None,
) -> list[dict[str, float]]:
    """一次真实 DC 扫描完成固定共模下的差分电压扫描。"""
    from circuits.spice_utils import run_dc_sweep

    start, stop, step = _sweep_grid(differential_voltages_v)
    circuit = build_differential_sweep_circuit(common_mode_v, start, config, opamp=opamp)
    data = run_dc_sweep(circuit, source_name="Vdctrl", start=start, stop=stop, step=step, nodes=["out", "inp", "inm", "hi", "lo"])
    requested = np.asarray([float(value) for value in differential_voltages_v], dtype=float)
    vhigh = common_mode_v + 0.5 * requested
    vlow = common_mode_v - 0.5 * requested
    out = np.interp(requested, data["sweep"], data["out"])
    inp = np.interp(requested, data["sweep"], data["inp"])
    inm = np.interp(requested, data["sweep"], data["inm"])
    return _rows_from_arrays(vhigh, vlow, out, inp, inm, config)


def sweep_common_mode_fast(
    common_mode_voltages_v: Sequence[float],
    *,
    differential_v: float,
    config: DifferentialAmplifierConfig,
    opamp: OpAmpSpec | None = None,
) -> list[dict[str, float]]:
    """一次真实 DC 扫描完成固定差分下的共模电压扫描。"""
    from circuits.spice_utils import run_dc_sweep

    start, stop, step = _sweep_grid(common_mode_voltages_v)
    circuit = build_differential_sweep_circuit(start, differential_v, config, opamp=opamp)
    data = run_dc_sweep(circuit, source_name="Vcm", start=start, stop=stop, step=step, nodes=["out", "inp", "inm", "hi", "lo"])
    requested = np.asarray([float(value) for value in common_mode_voltages_v], dtype=float)
    vhigh = requested + 0.5 * differential_v
    vlow = requested - 0.5 * differential_v
    out = np.interp(requested, data["sweep"], data["out"])
    inp = np.interp(requested, data["sweep"], data["inp"])
    inm = np.interp(requested, data["sweep"], data["inm"])
    return _rows_from_arrays(vhigh, vlow, out, inp, inm, config)


def build_low_ground_sweep_circuit(
    high_v: float,
    config: DifferentialAmplifierConfig,
    *,
    opamp: OpAmpSpec | None = None,
) -> Circuit:
    circuit = Circuit("BatteryLab differential amplifier high sweep")
    circuit.V("high", "hi", circuit.gnd, float(high_v))
    circuit.V("vlow", "lo", circuit.gnd, 0.0)
    circuit.V("vref", "vref", circuit.gnd, float(config.reference_v))
    circuit.R("1", "lo", "inm", config.r1_ohm)
    circuit.R("2", "out", "inm", config.r2_ohm)
    circuit.R("3", "hi", "inp", config.r3_ohm)
    circuit.R("4", "inp", "vref", config.r4_ohm)
    add_opamp(
        circuit,
        opamp or ideal_opamp_spec(config),
        output_node="out",
        non_inverting_node="inp",
        inverting_node="inm",
    )
    return circuit


def sweep_high_voltage_fast(
    cell_voltages_v: Sequence[float],
    config: DifferentialAmplifierConfig,
    *,
    opamp: OpAmpSpec | None = None,
) -> list[dict[str, float]]:
    """低端接地时扫描高端电压，一次 DC 扫描覆盖校准与验证点。"""
    from circuits.spice_utils import run_dc_sweep

    start, stop, step = _sweep_grid(cell_voltages_v)
    circuit = build_low_ground_sweep_circuit(start, config, opamp=opamp)
    data = run_dc_sweep(circuit, source_name="Vhigh", start=start, stop=stop, step=step, nodes=["out", "inp", "inm"])
    requested = np.asarray([float(value) for value in cell_voltages_v], dtype=float)
    out = np.interp(requested, data["sweep"], data["out"])
    inp = np.interp(requested, data["sweep"], data["inp"])
    inm = np.interp(requested, data["sweep"], data["inm"])
    zeros = np.zeros_like(requested)
    return _rows_from_arrays(requested, zeros, out, inp, inm, config)
