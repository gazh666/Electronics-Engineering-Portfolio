"""VirtualDUT 12 V 输入 / 5 V 输出行为模型单元测试。"""

import math
from pathlib import Path

import pytest

from models.virtual_dut import DUTConfig, DUTState, MODEL_SOURCE, DUTResult, VirtualDUT

DUT_CONFIG = Path(__file__).resolve().parents[1] / "configs" / "dut_config.yaml"


def test_default_parameters():
    dut = VirtualDUT()
    assert dut.nominal_voltage == 5.0
    assert dut.min_input == 9.0
    assert dut.max_input == 16.0
    assert dut.max_current == 2.0
    assert dut.output_resistance == 0.02
    assert dut.nominal_efficiency == 0.90


def test_no_load_output_is_nominal():
    result = VirtualDUT().calculate(12.0, 0.0)
    assert result.state == "NORMAL"
    assert result.vin == pytest.approx(12.0)
    assert result.vout == pytest.approx(5.0)
    assert result.iout == 0.0
    assert result.pout == 0.0
    assert result.pin == 0.0
    assert result.iin == 0.0
    assert result.efficiency is None
    assert result.source == MODEL_SOURCE


def test_load_current_causes_resistive_drop_and_conversion():
    result = VirtualDUT().calculate(12.0, 1.0)
    assert result.vout == pytest.approx(4.98)
    assert result.iout == pytest.approx(1.0)
    assert result.pout == pytest.approx(4.98)
    assert result.pin == pytest.approx(4.98 / 0.90)
    assert result.iin == pytest.approx(4.98 / 0.90 / 12.0)
    # 0.90 是预设模型参数，不是实验测得的效率
    assert result.efficiency == pytest.approx(0.90)


@pytest.mark.parametrize("load_current,vout", [(0.0, 5.0), (2.0, 4.96)])
def test_current_boundary_allowed(load_current, vout):
    result = VirtualDUT().calculate(12.0, load_current)
    assert result.state == "NORMAL"
    assert result.vout == pytest.approx(vout)


@pytest.mark.parametrize("vin", [9.0, 16.0])
def test_input_boundary_allowed(vin):
    assert VirtualDUT().calculate(vin, 0.5).state == "NORMAL"


@pytest.mark.parametrize(
    "vin,load_current,state",
    [
        (8.99, 0.5, "UNDERVOLTAGE"),
        (16.01, 0.5, "OVERVOLTAGE"),
        (12.0, 2.01, "OVERCURRENT"),
    ],
)
def test_protection_states_disable_output(vin, load_current, state):
    result = VirtualDUT().calculate(vin, load_current)
    assert result.state == state
    assert result.vout == 0.0
    assert result.iout == 0.0
    assert result.pout == 0.0
    assert result.pin == 0.0
    assert result.iin == 0.0
    assert result.efficiency is None


def test_output_disabled_has_priority():
    dut = VirtualDUT()
    result = dut.calculate(12.0, 1.0, enabled=False)
    assert result.state == "OUTPUT_OFF"
    assert result.vout == 0.0
    # 即使输入低于欠压点，输出关断仍然优先
    assert dut.calculate(0.0, 0.0, enabled=False).state == "OUTPUT_OFF"


@pytest.mark.parametrize(
    "vin,load_current",
    [
        (math.nan, 1.0),
        (12.0, math.nan),
        (math.inf, 1.0),
        (12.0, math.inf),
    ],
)
def test_non_finite_inputs_rejected(vin, load_current):
    with pytest.raises(ValueError):
        VirtualDUT().calculate(vin, load_current)


@pytest.mark.parametrize("vin,load_current", [(-0.1, 1.0), (12.0, -0.1)])
def test_negative_inputs_rejected(vin, load_current):
    with pytest.raises(ValueError):
        VirtualDUT().calculate(vin, load_current)


def test_result_source_default():
    result = DUTResult(12.0, 0.0, 5.0, 0.0, 0.0, 0.0, None, "NORMAL")
    assert result.source == MODEL_SOURCE


# ---------------------------------------------------------------------------
# 阶段五新增：配置、输入限流、判定顺序与边界
# ---------------------------------------------------------------------------


def test_calculate_with_limit_keywords():
    """阶段五接口：输入电流限制参与判定，并记录设置值。"""
    result = VirtualDUT().calculate(
        vin=12.0, input_current_limit=2.0, load_current=1.0
    )
    assert result.state == DUTState.NORMAL
    assert result.vin_setpoint == pytest.approx(12.0)
    assert result.input_current_limit == pytest.approx(2.0)
    assert result.load_current_setpoint == pytest.approx(1.0)
    assert result.vout == pytest.approx(4.98)
    assert result.power_loss == pytest.approx(result.pin - result.pout)


def test_positional_reference_order_supported():
    """兼容阶段五参考写法 calculate(vin, limit, load)。"""
    result = VirtualDUT().calculate(12.0, 2.0, 1.0)
    assert result.vout == pytest.approx(4.98)
    assert result.input_current_limit == pytest.approx(2.0)


def test_rated_current_boundary():
    dut = VirtualDUT()
    assert dut.calculate(12.0, 2.0, 2.0).state == DUTState.NORMAL
    assert dut.calculate(12.0, 2.0, 2.0001).state == DUTState.OVERCURRENT


@pytest.mark.parametrize("vin,state", [(8.999, "UNDERVOLTAGE"), (16.001, "OVERVOLTAGE")])
def test_input_just_outside_range(vin, state):
    assert VirtualDUT().calculate(vin, 2.0, 1.0).state == state


def test_output_off_has_highest_priority():
    dut = VirtualDUT()
    # 同时存在欠压、过流、限流时，输出关断仍优先
    result = dut.calculate(
        8.0,
        0.1,
        3.0,
        output_enabled=False,
        load_enabled=True,
    )
    assert result.state == DUTState.OUTPUT_OFF
    assert result.vin == 0.0
    assert result.vout == 0.0


def test_undervoltage_precedes_overcurrent():
    result = VirtualDUT().calculate(8.0, 2.0, 3.0)
    assert result.state == DUTState.UNDERVOLTAGE


def test_overvoltage_precedes_overcurrent():
    result = VirtualDUT().calculate(17.0, 2.0, 3.0)
    assert result.state == DUTState.OVERVOLTAGE


def test_overcurrent_precedes_input_current_limit():
    # 负载超额定同时输入限流很低：应报告过流
    result = VirtualDUT().calculate(12.0, 0.1, 2.5)
    assert result.state == DUTState.OVERCURRENT


def test_zero_current_limit_stops_loaded_output():
    result = VirtualDUT().calculate(12.0, 0.0, 1.0)
    assert result.state == DUTState.INPUT_CURRENT_LIMIT
    assert result.vout == 0.0
    assert result.efficiency is None


def test_zero_current_limit_allows_no_load():
    result = VirtualDUT().calculate(12.0, 0.0, 0.0)
    assert result.state == DUTState.NORMAL
    assert result.efficiency is None


@pytest.mark.parametrize("efficiency", [0.0, -0.1, 1.01])
def test_invalid_efficiency_config_rejected(efficiency):
    with pytest.raises(ValueError):
        DUTConfig(nominal_efficiency=efficiency)


def test_negative_output_resistance_rejected():
    with pytest.raises(ValueError):
        DUTConfig(output_resistance=-0.01)


def test_rated_voltage_must_be_positive():
    with pytest.raises(ValueError):
        DUTConfig(nominal_output_voltage=0.01, max_output_current=2.0, output_resistance=0.02)


def test_config_change_affects_result():
    dut = VirtualDUT(
        DUTConfig(nominal_output_voltage=3.3, max_output_current=2.0, output_resistance=0.02)
    )
    result = dut.calculate(12.0, 2.0, 1.0)
    assert result.vout == pytest.approx(3.28)


@pytest.mark.parametrize(
    "load_current,limit",
    [(-0.1, 2.0), (1.0, -0.1), (math.nan, 2.0), (1.0, math.inf)],
)
def test_invalid_current_inputs_rejected(load_current, limit):
    with pytest.raises(ValueError):
        VirtualDUT().calculate(12.0, limit, load_current)


def test_boolean_load_current_rejected():
    with pytest.raises(ValueError):
        VirtualDUT().calculate(vin=12.0, load_current=True, input_current_limit=2.0)


def test_power_balance_and_determinism():
    dut = VirtualDUT()
    first = dut.calculate(12.0, 2.0, 1.5)
    second = dut.calculate(12.0, 2.0, 1.5)
    assert first == second
    assert first.pin == pytest.approx(first.pout + first.power_loss)
    assert first.pin >= first.pout


def test_recovers_after_protection():
    dut = VirtualDUT()
    assert dut.calculate(8.0, 2.0, 1.0).state == DUTState.UNDERVOLTAGE
    recovered = dut.calculate(12.0, 2.0, 1.0)
    assert recovered.state == DUTState.NORMAL
    assert recovered.vout == pytest.approx(4.98)


def test_from_yaml_loads_parameters():
    dut = VirtualDUT.from_yaml(DUT_CONFIG)
    assert dut.nominal_voltage == pytest.approx(5.0)
    assert dut.min_input == pytest.approx(9.0)
    assert dut.max_input == pytest.approx(16.0)
    assert dut.max_current == pytest.approx(2.0)
    assert dut.nominal_efficiency == pytest.approx(0.90)


def test_from_yaml_missing_file():
    with pytest.raises(FileNotFoundError):
        VirtualDUT.from_yaml("not_exists_dut.yaml")


def test_from_yaml_missing_fields(tmp_path):
    path = tmp_path / "dut.yaml"
    path.write_text(
        "dut:\n"
        "  nominal_input_voltage: 12.0\n"
        "  min_input_voltage: 9.0\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="缺少字段"):
        VirtualDUT.from_yaml(path)


def test_from_yaml_invalid_type(tmp_path):
    path = tmp_path / "dut.yaml"
    path.write_text(
        "dut:\n"
        "  nominal_input_voltage: 12.0\n"
        "  min_input_voltage: 9.0\n"
        "  max_input_voltage: 16.0\n"
        "  nominal_output_voltage: 5.0\n"
        "  max_output_current: 2.0\n"
        "  output_resistance: 0.02\n"
        "  nominal_efficiency: high\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        VirtualDUT.from_yaml(path)
