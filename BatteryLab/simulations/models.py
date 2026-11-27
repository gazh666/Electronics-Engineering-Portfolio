"""模型清单与实验定义。

这里只描述模型类型与官方示例实验，不重复实现 PyBaMM 内部方程。
"""

from __future__ import annotations

MODEL_CATALOG = {
    "SPM": {
        "display_name": "Single Particle Model",
        "pybamm_path": "pybamm.lithium_ion.SPM",
        "category": "electrochemical",
        "data_source": "pybamm_simulation",
        "notes": "单颗粒电化学模型，默认参数集来自 PyBaMM 官方示例。",
    },
    "Thevenin": {
        "display_name": "Thevenin Equivalent Circuit Model",
        "pybamm_path": "pybamm.equivalent_circuit.Thevenin",
        "category": "equivalent_circuit",
        "data_source": "pybamm_simulation",
        "notes": "一阶 RC 等效电路模型，默认参数集 ECM_Example 为教学示例（100Ah）。",
    },
}


def cc_cv_experiment_steps(upper_voltage_v: float, c_rate: str = "C/2") -> list[str]:
    """构造官方 Experiment 字符串序列（放电-静置-充电-恒压-静置）。"""
    return [
        f"Discharge at {c_rate} for 20 minutes",
        "Rest for 5 minutes",
        f"Charge at {c_rate} until {upper_voltage_v:g} V",
        f"Hold at {upper_voltage_v:g} V until C/20",
        "Rest for 5 minutes",
    ]
