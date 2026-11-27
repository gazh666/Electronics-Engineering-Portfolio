"""CC-CV 双闭环：网表内行为源级联 PI，真实 ngspice 求解。

结构（全部在 SPICE 网表内，不在 Python 侧预生成波形）：

```text
Vpack ──► 电压 PI ──► 电流指令(受软启动限制) ──► 电流 PI ──► 占空比 ──► PWM ──► 栅极
             ▲                                        ▲
             └──────── 真实 V(pack) 节点 ─────────────┴── I(VSENSE) 电感电流
```

数值要点（已实测）：
- 时间步必须 ≤ 20 ns（1/500 开关周期）。50 ns 时 PWM 边沿量化会造成
  约 0.1–0.4 A 的伪极限环，看起来像控制不稳定，实际是求解分辨率不足。
- 积分节点 1 kΩ 泄漏 + ``u(time-1e-9)`` 保证 DC 工作点唯一。
- 前馈使用滤波后的输出电压，避免 ``D=(Vout+Vd)/Vin`` 形成代数正反馈。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from PySpice.Spice.Netlist import Circuit

from charging.config import ChargerConfig, ControllerConfig, PowerStageConfig
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

# 实测最小可靠时间步：50 ns 会因 PWM 边沿量化产生伪极限环。
MINIMUM_RELIABLE_STEP_S = 2e-8

CASCADE_NODES = (
    "vset",
    "iset",
    "en",
    "ss",
    "ilim",
    "ev",
    "xv",
    "vraw",
    "vfrz",
    "iref",
    "ei",
    "xi",
    "ifrz",
    "ff_in",
    "ff",
    "draw",
    "duty",
    "ramp",
)


@dataclass(frozen=True)
class CascadeParameters:
    voltage_kp_a_per_v: float
    voltage_ki_a_per_vs: float
    voltage_kaw_per_s: float
    current_kp_duty_per_a: float
    current_ki_duty_per_as: float
    current_kaw_per_s: float
    voltage_target_v: float
    current_target_a: float
    duty_min: float
    duty_max: float
    soft_start_time_s: float
    switching_frequency_hz: float
    diode_drop_v: float = 0.5
    feedforward_filter_time_s: float = 1e-3

    def __post_init__(self) -> None:
        finite_positive = (
            "voltage_ki_a_per_vs",
            "current_ki_duty_per_as",
            "voltage_target_v",
            "current_target_a",
            "switching_frequency_hz",
            "feedforward_filter_time_s",
        )
        for name in finite_positive:
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0.0:
                raise ChargerCircuitError(f"{name} 必须为正")
        for name in (
            "voltage_kp_a_per_v",
            "voltage_kaw_per_s",
            "current_kp_duty_per_a",
            "current_kaw_per_s",
            "soft_start_time_s",
            "diode_drop_v",
        ):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0.0:
                raise ChargerCircuitError(f"{name} 非法")
        if not 0.0 <= self.duty_min < self.duty_max < 1.0:
            raise ChargerCircuitError("占空比范围非法")

    @classmethod
    def from_configs(
        cls, charger: ChargerConfig, controller: ControllerConfig
    ) -> "CascadeParameters":
        return cls(
            voltage_kp_a_per_v=controller.voltage_loop.kp,
            voltage_ki_a_per_vs=controller.voltage_loop.ki,
            voltage_kaw_per_s=controller.voltage_loop.kaw,
            current_kp_duty_per_a=controller.current_loop.kp,
            current_ki_duty_per_as=controller.current_loop.ki,
            current_kaw_per_s=controller.current_loop.kaw,
            voltage_target_v=charger.charging.constant_voltage_v,
            current_target_a=charger.charging.constant_current_a,
            duty_min=controller.duty_min,
            duty_max=controller.duty_max,
            soft_start_time_s=charger.charging.soft_start_time_s,
            switching_frequency_hz=charger.power_stage.switching_frequency_hz,
            diode_drop_v=charger.power_stage.diode_forward_voltage_estimate_v,
        )

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


def build_cascade_circuit(
    power_stage: PowerStageConfig,
    fixture: PackFixture,
    parameters: CascadeParameters,
    *,
    voltage_set_expression: str | None = None,
    current_set_expression: str | None = None,
    enable_expression: str = "DC 1",
    vin_expression: str = "DC 18",
    models: ChargerDeviceModels | None = None,
    title: str = "BatteryLab stage6 CC-CV cascade charger",
) -> tuple[Circuit, ChargerLayout]:
    devices = models or ChargerDeviceModels.from_power_stage(power_stage)
    circuit = Circuit(title)
    layout = add_power_stage(
        circuit, power_stage, fixture, devices, vin_expression=vin_expression
    )
    p = parameters
    vset = voltage_set_expression or f"DC {p.voltage_target_v:.9g}"
    iset = current_set_expression or f"DC {p.current_target_a:.9g}"
    lines = [
        f".param FS={p.switching_frequency_hz:.9g}",
        f".param KPV={p.voltage_kp_a_per_v:.9g}",
        f".param KIV={p.voltage_ki_a_per_vs:.9g}",
        f".param KAWV={p.voltage_kaw_per_s:.9g}",
        f".param KPI={p.current_kp_duty_per_a:.9g}",
        f".param KII={p.current_ki_duty_per_as:.9g}",
        f".param KAWI={p.current_kaw_per_s:.9g}",
        f".param DMAX={p.duty_max:.9g}",
        f".param DMIN={p.duty_min:.9g}",
        f".param TSOFT={p.soft_start_time_s:.9g}",
        f"VSET vset 0 {vset}",
        f"VISET iset 0 {iset}",
        f"VENABLE en 0 {enable_expression}",
        # TSOFT=0 表示关闭软启动；用极小正值避免 time/0 产生非有限值。
        "BSS ss 0 V={min(time/max(TSOFT,1e-12),1)*u(V(en)-0.5)}",
        "BILIM ilim 0 V={V(iset)*V(ss)}",
        # ---------------- 电压外环 ----------------
        "BEV ev 0 V={V(vset)-V(pack)}",
        "CXV xv 0 1 IC=0",
        "RXV xv 0 1e3",
        "BVRAW vraw 0 V={KPV*V(ev)+V(xv)}",
        "BIREF iref 0 V={min(max(V(vraw),0),V(ilim))}",
        # 条件积分：饱和方向与误差同向时冻结；反向时允许退出饱和。
        "BVFRZ vfrz 0 V={min(u(V(vraw)-V(ilim)-1e-6)*u(V(ev))+u(-V(vraw)-1e-6)*u(-V(ev)),1)}",
        "BIV 0 xv I={(KIV*V(ev)+KAWV*(V(iref)-V(vraw)))*(1-V(vfrz))*u(time-1e-9)*u(V(en)-0.5)}",
        # ---------------- 电流内环 ----------------
        "BEI ei 0 V={V(iref)-I(VSENSE)}",
        "CXI xi 0 1 IC=0",
        "RXI xi 0 1e3",
        "RFF out ff_in 1e3",
        f"CFF ff_in 0 {p.feedforward_filter_time_s / 1e3:.9g}",
        f"BFF ff 0 V={{min(max((V(ff_in)+{p.diode_drop_v:.9g})/(V(vin)+{p.diode_drop_v:.9g}),DMIN),DMAX)}}",
        "BDRAW draw 0 V={V(ff)+KPI*V(ei)+V(xi)}",
        "BDUTY duty 0 V={min(max(V(draw),DMIN),DMAX)}",
        "BIFRZ ifrz 0 V={min(u(V(draw)-DMAX-1e-6)*u(V(ei))+u(-V(draw)-1e-6)*u(-V(ei)),1)}",
        "BII 0 xi I={(KII*V(ei)+KAWI*(V(duty)-V(draw)))*(1-V(ifrz))*u(time-1e-9)*u(V(en)-0.5)}",
        # ---------------- PWM 与驱动 ----------------
        "BRAMP ramp 0 V={time*FS-floor(time*FS)}",
        "BGATE graw 0 V={5*u(V(duty)-V(ramp)-0.001)*u(V(en)-0.5)*u(time-1e-9)}",
        "RG graw gate 100",
        "CG gate 0 1n",
    ]
    circuit.raw_spice += "\n".join(lines) + "\n"
    return circuit, layout


def run_cascade_buck(
    power_stage: PowerStageConfig,
    fixture: PackFixture,
    parameters: CascadeParameters,
    *,
    duration_s: float,
    step_s: float = MINIMUM_RELIABLE_STEP_S,
    voltage_set_expression: str | None = None,
    current_set_expression: str | None = None,
    enable_expression: str = "DC 1",
    vin_expression: str = "DC 18",
    temperature_c: float = 25.0,
    reltol: float = 1e-3,
    abstol: float = 1e-8,
    vntol: float = 1e-5,
) -> tuple[ChargerWaveform, Circuit, ChargerLayout]:
    if step_s > MINIMUM_RELIABLE_STEP_S:
        raise ChargerCircuitError(
            f"时间步 {step_s:g} s 大于可靠上限 {MINIMUM_RELIABLE_STEP_S:g} s，会出现 PWM 量化伪极限环"
        )
    circuit, layout = build_cascade_circuit(
        power_stage,
        fixture,
        parameters,
        voltage_set_expression=voltage_set_expression,
        current_set_expression=current_set_expression,
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
    ) + CASCADE_NODES + layout.cell_positive_nodes[1:] + tuple(
        f"a{index}" for index in range(1, len(fixture.cells) + 1)
    ) + tuple(f"o{index}" for index in range(1, len(fixture.cells) + 1))
    data = run_transient(
        circuit,
        duration_s=duration_s,
        step_s=step_s,
        max_step_s=step_s,
        nodes=nodes,
        branches=("VIN", "VSENSE", "VBATSENSE"),
        temperature_c=temperature_c,
        reltol=reltol,
        abstol=abstol,
        vntol=vntol,
    )
    waveform = extract_waveform(data, layout, current_reference_node="iref")
    return waveform, circuit, layout


def numerical_assumptions(parameters: CascadeParameters) -> dict[str, Any]:
    return {
        "controller_location": "inside_spice_netlist_behavioral_sources",
        "minimum_step_s": MINIMUM_RELIABLE_STEP_S,
        "integrator_dc_solution": "1k leak + u(time-1e-9) gating",
        "pwm": "behavioral comparator with 1 mV bias",
        "anti_windup": "back-calculation on both loops",
        "feedforward": "filtered output voltage, not instantaneous",
        "parameters": parameters.to_dict(),
        "limitation": "short-window local fixture; SOC not solved in SPICE",
    }
