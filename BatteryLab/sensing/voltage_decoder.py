"""单体差分电压编码/解码（四电阻差分放大器）。"""

from __future__ import annotations

import math


class VoltageDecodeError(ValueError):
    """电压解码输入非法。"""


def _real(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise VoltageDecodeError(f"{name} 必须是有限数值")
    return float(value)


def four_resistor_output(
    vhigh_v: float,
    vlow_v: float,
    *,
    r1_ohm: float,
    r2_ohm: float,
    r3_ohm: float,
    r4_ohm: float,
    reference_v: float,
) -> float:
    """四电阻差分放大器理想解析输出。

    Vout = (1 + R2/R1) * (Vhigh*R4 + Vref*R3)/(R3+R4) - (R2/R1)*Vlow
    当 R2/R1 = R4/R3 = k 时退化为 Vout = Vref + k*(Vhigh - Vlow)。
    """
    r1 = _real(r1_ohm, "R1")
    r2 = _real(r2_ohm, "R2")
    r3 = _real(r3_ohm, "R3")
    r4 = _real(r4_ohm, "R4")
    if min(r1, r2, r3, r4) <= 0.0:
        raise VoltageDecodeError("差分放大器电阻必须为正")
    vhigh = _real(vhigh_v, "Vhigh")
    vlow = _real(vlow_v, "Vlow")
    vref = _real(reference_v, "Vref")
    vp = (vhigh * r4 + vref * r3) / (r3 + r4)
    return (1.0 + r2 / r1) * vp - (r2 / r1) * vlow


def matched_output(cell_voltage_v: float, *, gain: float, reference_v: float) -> float:
    gain_value = _real(gain, "增益")
    if gain_value <= 0.0:
        raise VoltageDecodeError("差分增益必须为正")
    return _real(reference_v, "参考电压") + gain_value * _real(cell_voltage_v, "单体电压")


def cell_voltage_from_output(output_v: float, *, gain: float, reference_v: float) -> float:
    gain_value = _real(gain, "增益")
    if gain_value <= 0.0:
        raise VoltageDecodeError("差分增益必须为正")
    return (_real(output_v, "输出电压") - _real(reference_v, "参考电压")) / gain_value


def input_common_mode(vhigh_v: float, vlow_v: float) -> float:
    return 0.5 * (_real(vhigh_v, "Vhigh") + _real(vlow_v, "Vlow"))


def amplifier_pin_common_mode(
    vhigh_v: float,
    vlow_v: float,
    *,
    r1_ohm: float,
    r2_ohm: float,
    r3_ohm: float,
    r4_ohm: float,
    reference_v: float,
) -> dict[str, float]:
    """计算运放两个输入引脚的实际电压（理想虚短假设）。

    这是判断输入共模范围是否超限的关键量：电池上端节点电压可以远高于
    运放供电，真正需要核对的是分压后落在运放引脚上的电压。
    """
    vhigh = _real(vhigh_v, "Vhigh")
    vlow = _real(vlow_v, "Vlow")
    out = four_resistor_output(
        vhigh,
        vlow,
        r1_ohm=r1_ohm,
        r2_ohm=r2_ohm,
        r3_ohm=r3_ohm,
        r4_ohm=r4_ohm,
        reference_v=reference_v,
    )
    vp = (vhigh * float(r4_ohm) + float(reference_v) * float(r3_ohm)) / (float(r3_ohm) + float(r4_ohm))
    vn = (vlow * float(r2_ohm) + out * float(r1_ohm)) / (float(r1_ohm) + float(r2_ohm))
    return {"v_inp_v": vp, "v_inm_v": vn, "v_out_v": out}


def output_saturated(output_v: float, *, low_v: float, high_v: float) -> bool:
    return output_v <= low_v or output_v >= high_v
