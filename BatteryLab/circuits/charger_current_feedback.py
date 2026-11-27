"""电流内环：网表内行为源 PI + PWM，真实 ngspice 闭环。

只闭合电流环，用于单独验证内环跟踪、软启动、抗饱和与输入阶跃响应；
电压外环不在此模块，避免把"电流达标"误当成 CC-CV 整体达标。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

from PySpice.Spice.Netlist import Circuit

from charging.config import PowerStageConfig
from circuits.charger_buck import (
    ChargerCircuitError,
    ChargerLayout,
    ChargerWaveform,
    PackFixture,
    add_power_stage,
    extract_waveform,
)
from circuits.charger_switch_models import ChargerDeviceModels
from circuits.spice_utils import run_transient


@dataclass(frozen=True)
class CurrentLoopParameters:
    kp_duty_per_a: float
    ki_duty_per_as: float
    anti_windup_per_s: float
    duty_max: float = 0.9
    duty_min: float = 0.0
    soft_start_time_s: float = 5e-3
    switching_frequency_hz: float = 100e3
    diode_drop_v: float = 0.5
    feedforward_filter_time_s: float = 1e-3

    def __post_init__(self) -> None:
        if not 0.0 <= self.duty_min < self.duty_max < 1.0:
            raise ChargerCircuitError("占空比范围非法")
        for name in (
            "kp_duty_per_a",
            "ki_duty_per_as",
            "anti_windup_per_s",
            "switching_frequency_hz",
            "diode_drop_v",
        ):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0.0:
                raise ChargerCircuitError(f"{name} 非法")
        if self.soft_start_time_s < 0.0:
            raise ChargerCircuitError("软启动时间不能为负")
        if self.feedforward_filter_time_s <= 0.0:
            raise ChargerCircuitError("前馈滤波时间必须为正")

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


CONTROLLER_NODES = (
    "iset",
    "ilim",
    "ss",
    "ei",
    "xi",
    "ifrz",
    "ff_in",
    "ff",
    "draw",
    "duty",
    "ramp",
    "en",
)


def build_current_loop_circuit(
    power_stage: PowerStageConfig,
    fixture: PackFixture,
    parameters: CurrentLoopParameters,
    *,
    current_reference_expression: str = "DC 1",
    enable_expression: str = "DC 1",
    vin_expression: str = "DC 18",
    models: ChargerDeviceModels | None = None,
    title: str = "BatteryLab stage6 current-loop buck charger",
) -> tuple[Circuit, ChargerLayout]:
    devices = models or ChargerDeviceModels.from_power_stage(power_stage)
    circuit = Circuit(title)
    layout = add_power_stage(
        circuit, power_stage, fixture, devices, vin_expression=vin_expression
    )
    p = parameters
    lines = [
        f".param FS={p.switching_frequency_hz:.9g}",
        f".param KPI={p.kp_duty_per_a:.9g}",
        f".param KII={p.ki_duty_per_as:.9g}",
        f".param KAWI={p.anti_windup_per_s:.9g}",
        f".param DMAX={p.duty_max:.9g}",
        f".param DMIN={p.duty_min:.9g}",
        f".param TSOFT={p.soft_start_time_s:.9g}",
        f"VISET iset 0 {current_reference_expression}",
        f"VENABLE en 0 {enable_expression}",
        # 软启动斜坡，并与使能相乘：禁止充电时参考立即归零。
        "BSS ss 0 V={min(time/TSOFT,1)*u(V(en)-0.5)}",
        "BILIM ilim 0 V={V(iset)*V(ss)}",
        "BEI ei 0 V={V(ilim)-I(VSENSE)}",
        "CXI xi 0 1 IC=0",
        "RXI xi 0 1e3",
        # 前馈使用滤波后的输出电压：直接使用瞬时 V(out) 会形成
        # D=(Vout+Vd)/Vin 的代数正反馈通路（环路增益≈1），在 LC 谐振附近自激。
        "RFF out ff_in 1e3",
        f"CFF ff_in 0 {p.feedforward_filter_time_s / 1e3:.9g}",
        # 前馈只由工作点决定，不乘软启动：否则占空比被压在电池电压以下，
        # 变换器进入 DCM、电流环需要长时间积分追赶，造成大过冲。
        f"BFF ff 0 V={{min(max((V(ff_in)+{p.diode_drop_v:.9g})/(V(vin)+{p.diode_drop_v:.9g}),DMIN),DMAX)}}",
        "BDRAW draw 0 V={V(ff)+KPI*V(ei)+V(xi)}",
        "BDUTY duty 0 V={min(max(V(draw),DMIN),DMAX)}",
        # 条件积分：饱和方向与误差同向时冻结，反向时允许退出；再叠加反计算。
        "BIFRZ ifrz 0 V={min(u(V(draw)-DMAX-1e-6)*u(V(ei))+u(-V(draw)-DMIN-1e-6)*u(-V(ei)),1)}",
        "BII 0 xi I={(KII*V(ei)+KAWI*(V(duty)-V(draw)))*(1-V(ifrz))*u(time-1e-9)*u(V(en)-0.5)}",
        "BRAMP ramp 0 V={time*FS-floor(time*FS)}",
        # 1 mV 偏置保证 DC 工作点栅极为 0。
        "BGATE graw 0 V={5*u(V(duty)-V(ramp)-0.001)*u(V(en)-0.5)*u(time-1e-9)}",
        "RG graw gate 100",
        "CG gate 0 1n",
    ]
    circuit.raw_spice += "\n".join(lines) + "\n"
    return circuit, layout


def run_current_loop_buck(
    power_stage: PowerStageConfig,
    fixture: PackFixture,
    parameters: CurrentLoopParameters,
    *,
    duration_s: float,
    step_s: float,
    current_reference_expression: str = "DC 1",
    enable_expression: str = "DC 1",
    vin_expression: str = "DC 18",
    temperature_c: float = 25.0,
    reltol: float = 1e-3,
    abstol: float = 1e-8,
    vntol: float = 1e-5,
) -> tuple[ChargerWaveform, Circuit, ChargerLayout]:
    circuit, layout = build_current_loop_circuit(
        power_stage,
        fixture,
        parameters,
        current_reference_expression=current_reference_expression,
        enable_expression=enable_expression,
        vin_expression=vin_expression,
    )
    nodes = (
        "vin",
        "sw",
        "lx",
        "ldcr",
        "out",
        "cap",
        "path",
        "pack",
        "duty",
        "gate",
    ) + CONTROLLER_NODES + layout.cell_positive_nodes[1:] + tuple(
        f"a{index}" for index in range(1, len(fixture.cells) + 1)
    ) + tuple(f"o{index}" for index in range(1, len(fixture.cells) + 1))
    data = run_transient(
        circuit,
        duration_s=duration_s,
        step_s=step_s,
        max_step_s=min(step_s, 1.0 / (20.0 * power_stage.switching_frequency_hz)),
        nodes=nodes,
        branches=("VIN", "VSENSE", "VBATSENSE"),
        temperature_c=temperature_c,
        reltol=reltol,
        abstol=abstol,
        vntol=vntol,
    )
    waveform = extract_waveform(data, layout, current_reference_node="ilim")
    return waveform, circuit, layout


def controller_nodes_for_plot(parameters: CurrentLoopParameters) -> Sequence[str]:
    return CONTROLLER_NODES


def transient_assumptions(parameters: CurrentLoopParameters) -> dict[str, Any]:
    """写入结果元数据：哪些是真实 SPICE，哪些只是数值技巧。"""
    return {
        "controller_location": "inside_spice_netlist_behavioral_sources",
        "integrator_dc_solution": "1k leak + u(time-1e-9) gating",
        "pwm": "behavioral comparator with 1 mV bias",
        "anti_windup": "back-calculation",
        "parameters": parameters.to_dict(),
    }
