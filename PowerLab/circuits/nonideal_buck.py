"""非理想 Buck 电路构建：五种对照模型 A–E。

=====================  =======  =========  ==========  ====  ====
模型                   主开关    驱动方式    续流二极管    DCR   ESR
=====================  =======  =========  ==========  ====  ====
A 第三阶段基线          SW      对地 PWM    理想教学 D   否    否
B 无源非理想            SW      对地 PWM    理想教学 D   是    是
C 非理想二极管          SW      对地 PWM    非理想 D     是    是
D 浮地 MOSFET           NMOS    浮动驱动    非理想 D     是    是
E 完整模型 + 寄生电容    NMOS    浮动驱动    非理想 D     是    是
=====================  =======  =========  ==========  ====  ====

节点约定（D/E 与 B/C 共用测量结构）::

    VIN → VDSENSE → drain ── M1/S1 ── sw ── VLSENSE ── lx ── L1 ── l_dcr
                                      │                       RDCR ── out
                                      │                                │
                                     DFREE(阳极 diode_a, 阴极 sw)      ├── RLOAD ── GND
                                      │                                ├── VCSENSE ── c_esr
                                    VDIOSENSE                          │              RESR
                                     GND                               │              cap_internal
                                                                      └── C1 ── GND

0 V 电压源 ``VDSENSE`` / ``VLSENSE`` / ``VCSENSE`` / ``VDIOSENSE`` 只用于取得
真实支路电流，不改变拓扑。Model A 直接复用第三阶段 ``circuits.buck`` 构建器。
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from PySpice.Spice.Netlist import Circuit

from .buck import build_buck_from_parameters
from .buck_config import BuckConfig, BuckParameters
from .diode_models import add_nonideal_diode
from .gate_driver import add_floating_gate_driver, add_ground_referenced_gate_drive
from .mosfet_models import add_educational_nmos, add_mosfet_parasitic_capacitors
from .nonideal_config import NonidealBuckConfig
from .passive_models import add_capacitor_with_esr, add_inductor_with_dcr
from .pwm import PWMParameters
from .switch_models import DiodeConfig, SwitchConfig, add_diode_model, add_switch_model

DEFAULT_CIRCUIT_TITLE = "PowerLab Nonideal Buck (Stage 4)"

#: 节点名称。
NODE_INPUT = "vin"
NODE_DRAIN = "drain"
NODE_GATE = "gate"
NODE_DRIVE = "drv"
NODE_SWITCH = "sw"
NODE_DIODE_ANODE = "diode_a"
NODE_INDUCTOR = "lx"
NODE_INDUCTOR_DCR = "l_dcr"
NODE_OUTPUT = "out"
NODE_CAPACITOR_ESR = "c_esr"
NODE_CAPACITOR_INTERNAL = "cap_internal"

#: 0 V 电流传感支路名称（结果列名会加 ``_branch_current_a`` 后缀）。
BRANCH_INPUT = "vin"
BRANCH_DRAIN = "vdsense"
BRANCH_DRIVE = "vdrv"
BRANCH_DIODE = "vdiosense"
BRANCH_INDUCTOR = "vlsense"
BRANCH_CAPACITOR = "vcsense"

#: 对照模型使用的教学开关参数（与第三阶段一致）。
LEGACY_SWITCH = SwitchConfig(
    on_resistance_ohm=1e-3,
    off_resistance_ohm=1e6,
    threshold_voltage_v=2.5,
    hysteresis_voltage_v=0.1,
)

#: 对照模型使用的教学二极管参数（与第三阶段一致）。
LEGACY_DIODE = DiodeConfig(
    model_name="DFREE",
    saturation_current_a=1e-6,
    ideality_factor=1.0,
    series_resistance_ohm=1e-3,
)

#: 对地 PWM 栅极电平（SW 对照模型）。
LEGACY_GATE_HIGH_V = 5.0


@dataclass(frozen=True)
class VariantFeatures:
    """一种对照模型的建模开关组合。"""

    variant: str
    label: str
    uses_mosfet: bool
    uses_parasitic_capacitors: bool
    uses_nonideal_diode: bool
    uses_dcr: bool
    uses_esr: bool
    uses_floating_driver: bool
    description: str

    def to_dict(self) -> dict[str, object]:
        return {
            "variant": self.variant,
            "label": self.label,
            "uses_mosfet": self.uses_mosfet,
            "uses_parasitic_capacitors": self.uses_parasitic_capacitors,
            "uses_nonideal_diode": self.uses_nonideal_diode,
            "uses_dcr": self.uses_dcr,
            "uses_esr": self.uses_esr,
            "uses_floating_driver": self.uses_floating_driver,
            "description": self.description,
        }


#: 五种对照模型的固定定义（顺序即 A→E 递进）。
VARIANT_TABLE: dict[str, VariantFeatures] = {
    "A": VariantFeatures(
        variant="A",
        label="Stage-3 SW baseline",
        uses_mosfet=False,
        uses_parasitic_capacitors=False,
        uses_nonideal_diode=False,
        uses_dcr=False,
        uses_esr=False,
        uses_floating_driver=False,
        description="SW switch, ideal teaching diode, ideal L and C (stage-3 baseline)",
    ),
    "B": VariantFeatures(
        variant="B",
        label="Passive parasitics",
        uses_mosfet=False,
        uses_parasitic_capacitors=False,
        uses_nonideal_diode=False,
        uses_dcr=True,
        uses_esr=True,
        uses_floating_driver=False,
        description="SW switch and ideal teaching diode plus inductor DCR and capacitor ESR",
    ),
    "C": VariantFeatures(
        variant="C",
        label="Nonideal diode",
        uses_mosfet=False,
        uses_parasitic_capacitors=False,
        uses_nonideal_diode=True,
        uses_dcr=True,
        uses_esr=True,
        uses_floating_driver=False,
        description="SW switch plus nonideal diode, DCR and ESR",
    ),
    "D": VariantFeatures(
        variant="D",
        label="Floating MOSFET",
        uses_mosfet=True,
        uses_parasitic_capacitors=False,
        uses_nonideal_diode=True,
        uses_dcr=True,
        uses_esr=True,
        uses_floating_driver=True,
        description="Level 1 NMOS with ideal floating gate drive, nonideal diode, DCR, ESR",
    ),
    "E": VariantFeatures(
        variant="E",
        label="Full model with parasitics",
        uses_mosfet=True,
        uses_parasitic_capacitors=True,
        uses_nonideal_diode=True,
        uses_dcr=True,
        uses_esr=True,
        uses_floating_driver=True,
        description="Full model: NMOS, floating drive, Cgs/Cgd/Cds, nonideal diode, DCR, ESR",
    ),
}


def get_variant_features(variant: str) -> VariantFeatures:
    """按字母返回对照模型定义。"""
    if not isinstance(variant, str) or not variant.strip():
        raise ValueError("variant must be a non-empty string")
    key = variant.strip().upper()
    if key not in VARIANT_TABLE:
        raise ValueError(f"unknown model variant {variant!r}; expected one of {tuple(VARIANT_TABLE)}")
    return VARIANT_TABLE[key]


def legacy_baseline_parameters(config: NonidealBuckConfig) -> BuckParameters:
    """把第四阶段参数映射成第三阶段 ``BuckParameters``（Model A 基线）。"""
    if not isinstance(config, NonidealBuckConfig):
        raise ValueError("config must be NonidealBuckConfig")
    return BuckParameters(
        circuit=BuckConfig(
            input_voltage_v=config.input_voltage_v,
            target_output_voltage_v=config.target_output_voltage_v,
            rated_output_current_a=config.rated_output_current_a,
            switching_frequency_hz=config.switching_frequency_hz,
            duty_cycle=config.duty_cycle,
            inductance_h=config.inductor.inductance_h,
            capacitance_f=config.capacitor.capacitance_f,
            load_resistance_ohm=config.load_resistance_ohm,
        ),
        pwm=PWMParameters(
            frequency_hz=config.switching_frequency_hz,
            duty_cycle=config.duty_cycle,
            low_voltage_v=0.0,
            high_voltage_v=LEGACY_GATE_HIGH_V,
            rise_time_s=config.gate_driver.rise_time_s,
            fall_time_s=config.gate_driver.fall_time_s,
            delay_s=config.gate_driver.delay_s,
        ),
        switch=LEGACY_SWITCH,
        diode=LEGACY_DIODE,
        transient=config.transient,
        steady_state=config.steady_state,
        version=config.version,
        circuit_name="Stage 3 SW Buck baseline",
        topology=config.topology,
        control_mode=config.control_mode,
        model_type="stage3_sw_baseline",
    )


def _build_legacy_baseline(config: NonidealBuckConfig) -> Circuit:
    return build_buck_from_parameters(
        legacy_baseline_parameters(config),
        title="PowerLab Stage-3 SW Buck baseline",
    )


def _add_power_stage(
    circuit: Circuit,
    config: NonidealBuckConfig,
    features: VariantFeatures,
) -> None:
    """添加输入源、主开关、续流二极管与全部无源器件。"""
    circuit.V("IN", NODE_INPUT, circuit.gnd, config.input_voltage_v)
    circuit.V("DSENSE", NODE_INPUT, NODE_DRAIN, 0.0)

    if features.uses_mosfet:
        add_educational_nmos(
            circuit,
            config.mosfet,
            NODE_DRAIN,
            NODE_GATE,
            NODE_SWITCH,
        )
        if features.uses_parasitic_capacitors:
            add_mosfet_parasitic_capacitors(
                circuit,
                config.mosfet,
                NODE_DRAIN,
                NODE_GATE,
                NODE_SWITCH,
            )
        add_floating_gate_driver(
            circuit,
            config.pwm,
            config.gate_driver,
            source_node=NODE_SWITCH,
            gate_node=NODE_GATE,
            drive_node=NODE_DRIVE,
        )
    else:
        add_ground_referenced_gate_drive(
            circuit,
            PWMParameters(
                frequency_hz=config.switching_frequency_hz,
                duty_cycle=config.duty_cycle,
                low_voltage_v=0.0,
                high_voltage_v=LEGACY_GATE_HIGH_V,
                rise_time_s=config.gate_driver.rise_time_s,
                fall_time_s=config.gate_driver.fall_time_s,
                delay_s=config.gate_driver.delay_s,
            ),
            NODE_GATE,
        )
        model = add_switch_model(circuit, LEGACY_SWITCH, name="SWMOD")
        circuit.S("1", NODE_DRAIN, NODE_SWITCH, NODE_GATE, circuit.gnd, model=model)

    circuit.V("DIOSENSE", circuit.gnd, NODE_DIODE_ANODE, 0.0)
    if features.uses_nonideal_diode:
        add_nonideal_diode(
            circuit,
            config.diode,
            NODE_DIODE_ANODE,
            NODE_SWITCH,
        )
    else:
        model = add_diode_model(circuit, LEGACY_DIODE)
        circuit.D("FREE", NODE_DIODE_ANODE, NODE_SWITCH, model=model)

    circuit.V("LSENSE", NODE_SWITCH, NODE_INDUCTOR, 0.0)
    inductor = (
        config.inductor
        if features.uses_dcr
        else replace(config.inductor, dcr_ohm=0.0)
    )
    add_inductor_with_dcr(
        circuit,
        inductor,
        NODE_INDUCTOR,
        NODE_OUTPUT,
        internal_node=NODE_INDUCTOR_DCR,
    )
    circuit.V("CSENSE", NODE_OUTPUT, NODE_CAPACITOR_ESR, 0.0)
    capacitor = (
        config.capacitor
        if features.uses_esr
        else replace(config.capacitor, esr_ohm=0.0)
    )
    add_capacitor_with_esr(
        circuit,
        capacitor,
        NODE_CAPACITOR_ESR,
        circuit.gnd,
        internal_node=NODE_CAPACITOR_INTERNAL,
    )
    circuit.R("LOAD", NODE_OUTPUT, circuit.gnd, config.load_resistance_ohm)


def build_nonideal_buck(
    config: NonidealBuckConfig,
    variant: str | None = None,
    *,
    title: str = DEFAULT_CIRCUIT_TITLE,
) -> Circuit:
    """按对照模型变体构建非理想 Buck 电路（不执行仿真）。

    ``variant`` 为空时使用 ``config.model_variant``。
    Model A 直接委托第三阶段构建器，保证基线真实保留。
    """
    if not isinstance(config, NonidealBuckConfig):
        raise ValueError("config must be NonidealBuckConfig")
    features = get_variant_features(variant or config.model_variant)
    if not isinstance(title, str) or not title.strip():
        raise ValueError("title must be a non-empty string")

    if features.variant == "A":
        return _build_legacy_baseline(config)

    circuit = Circuit(f"{title.strip()} - Model {features.variant}")
    _add_power_stage(circuit, config, features)
    return circuit


def variant_description(variant: str) -> str:
    """返回模型说明文本。"""
    return get_variant_features(variant).description
