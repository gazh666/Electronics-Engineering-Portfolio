"""故障注入单元测试：阶段八可重复异常场景。"""

import math
from pathlib import Path

import pytest

from engine.fault_injector import (
    FAULT_CURRENT_OFFSET,
    FAULT_DISCONNECT,
    FAULT_INTERRUPT,
    FAULT_INVALID_RESPONSE,
    FAULT_NAN,
    FAULT_TIMEOUT,
    FAULT_VOLTAGE_OFFSET,
    LOCATION_BRIDGE,
    LOCATION_DMM_CURRENT,
    LOCATION_DMM_VOLTAGE,
    FaultInjector,
    FaultSpec,
    TestInterrupted,
)
from instruments import (
    InstrumentError,
    InstrumentNotConnectedError,
    InstrumentTimeoutError,
)
from models.virtual_dut import VirtualDUT


def _injector(*specs: FaultSpec) -> FaultInjector:
    return FaultInjector(specs=specs)


# ---------------------------------------------------------------------------
# 配置校验
# ---------------------------------------------------------------------------


def test_unknown_fault_type_rejected():
    with pytest.raises(ValueError):
        FaultSpec("unknown", LOCATION_BRIDGE)


def test_negative_times_rejected():
    with pytest.raises(ValueError):
        FaultSpec(FAULT_TIMEOUT, LOCATION_BRIDGE, times=-1)


def test_non_finite_offset_rejected():
    with pytest.raises(ValueError):
        FaultSpec(FAULT_VOLTAGE_OFFSET, LOCATION_DMM_VOLTAGE, value=math.nan)


# ---------------------------------------------------------------------------
# 通信类故障
# ---------------------------------------------------------------------------


def test_communication_timeout_raises_and_is_recorded():
    injector = _injector(FaultSpec(FAULT_TIMEOUT, LOCATION_BRIDGE))

    with pytest.raises(InstrumentTimeoutError):
        injector.apply(LOCATION_BRIDGE)

    record = injector.to_dicts()[0]
    assert record["fault_type"] == FAULT_TIMEOUT
    assert record["location"] == LOCATION_BRIDGE
    assert record["occurrences"] == 1
    assert record["retries"] == 0
    assert record["final_status"] == "RAISED"

    injector.mark_retry()
    injector.finalize("ERROR")
    record = injector.to_dicts()[0]
    assert record["retries"] == 1
    assert record["final_status"] == "ERROR"


def test_instrument_disconnect_raises():
    injector = _injector(FaultSpec(FAULT_DISCONNECT, LOCATION_BRIDGE))
    with pytest.raises(InstrumentNotConnectedError):
        injector.apply(LOCATION_BRIDGE)


def test_invalid_string_response_raises():
    injector = _injector(FaultSpec(FAULT_INVALID_RESPONSE, LOCATION_BRIDGE))
    with pytest.raises(InstrumentError):
        injector.apply(LOCATION_BRIDGE)


def test_test_interruption_is_ordinary_runtime_error():
    injector = _injector(FaultSpec(FAULT_INTERRUPT, LOCATION_BRIDGE))
    with pytest.raises(TestInterrupted):
        injector.apply(LOCATION_BRIDGE)
    # 不是 KeyboardInterrupt，执行引擎可以按普通异常收尾
    assert issubclass(TestInterrupted, RuntimeError)


# ---------------------------------------------------------------------------
# 数据类故障
# ---------------------------------------------------------------------------


def test_nan_data_replaces_reading():
    injector = _injector(FaultSpec(FAULT_NAN, LOCATION_DMM_VOLTAGE))
    value = injector.apply(LOCATION_DMM_VOLTAGE, 5.0)
    assert value is not None and math.isnan(value)


def test_voltage_offset_is_deterministic():
    injector = _injector(
        FaultSpec(FAULT_VOLTAGE_OFFSET, LOCATION_DMM_VOLTAGE, value=0.25)
    )
    assert injector.apply(LOCATION_DMM_VOLTAGE, 5.0) == pytest.approx(5.25)


def test_current_offset_is_deterministic():
    injector = _injector(
        FaultSpec(FAULT_CURRENT_OFFSET, LOCATION_DMM_CURRENT, value=0.1)
    )
    assert injector.apply(LOCATION_DMM_CURRENT, 1.0) == pytest.approx(1.1)


def test_nan_fault_requires_reading_value():
    injector = _injector(FaultSpec(FAULT_NAN, LOCATION_BRIDGE))
    with pytest.raises(ValueError):
        injector.apply(LOCATION_BRIDGE)


# ---------------------------------------------------------------------------
# 次数与匹配
# ---------------------------------------------------------------------------


def test_limited_times_only_faults_once():
    injector = _injector(FaultSpec(FAULT_TIMEOUT, LOCATION_BRIDGE, times=1))

    with pytest.raises(InstrumentTimeoutError):
        injector.apply(LOCATION_BRIDGE)

    # 第二次不再注入，返回原始值
    assert injector.apply(LOCATION_BRIDGE, 12.0) == pytest.approx(12.0)
    assert injector.to_dicts()[0]["occurrences"] == 1


def test_unlimited_times_always_faults():
    injector = _injector(FaultSpec(FAULT_TIMEOUT, LOCATION_BRIDGE, times=0))
    for _ in range(3):
        with pytest.raises(InstrumentTimeoutError):
            injector.apply(LOCATION_BRIDGE)
    assert injector.to_dicts()[0]["occurrences"] == 3


def test_non_matching_location_has_no_effect():
    injector = _injector(FaultSpec(FAULT_TIMEOUT, LOCATION_BRIDGE))
    assert injector.apply(LOCATION_DMM_VOLTAGE, 5.0) == pytest.approx(5.0)
    record = injector.to_dicts()[0]
    assert record["occurrences"] == 0
    assert record["final_status"] == "NOT_TRIGGERED"
    injector.finalize("PASS")
    assert injector.to_dicts()[0]["final_status"] == "NOT_TRIGGERED"


# ---------------------------------------------------------------------------
# DUT 模型参数故障
# ---------------------------------------------------------------------------


def test_extra_dropout_is_restored():
    dut = VirtualDUT()
    with FaultInjector(dut).extra_dropout(0.2):
        assert dut.nominal_voltage == pytest.approx(4.8)
    assert dut.nominal_voltage == pytest.approx(5.0)


def test_disable_ocp_is_restored():
    dut = VirtualDUT()
    with FaultInjector(dut).disable_ocp():
        assert dut.max_current == math.inf
    assert dut.max_current == pytest.approx(2.0)


def test_efficiency_override_is_restored():
    dut = VirtualDUT()
    with FaultInjector(dut).efficiency_override(1.2):
        assert dut.nominal_efficiency == pytest.approx(1.2)
    assert dut.nominal_efficiency == pytest.approx(0.90)


# ---------------------------------------------------------------------------
# 阶段八：新 FaultScenario / Reliability FaultInjector
# ---------------------------------------------------------------------------


from reliability.exceptions import (  # noqa: E402
    CommunicationTimeoutError,
    DeviceDisconnectedError,
    UnsafeShutdownError,
)
from reliability.fault_injector import (  # noqa: E402
    FAULT_INJECTED_SOURCE,
    INVALID_RESPONSE_TEXT,
    FaultInjector as ScenarioFaultInjector,
    apply_measurement_faults,
)
from reliability.fault_models import (  # noqa: E402
    FaultScenario,
    FaultScenarioLibrary,
    FaultTarget,
    FaultType,
    load_fault_scenarios,
)
from instruments.exceptions import InstrumentSessionLostError  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]


def _scenario(**overrides):
    data = {
        "scenario_id": "T001",
        "name": "测试场景",
        "fault_type": FaultType.TIMEOUT,
        "target": FaultTarget.INSTRUMENT_QUERY,
        "operation": "VOLT?",
        "device": "PS001",
    }
    data.update(overrides)
    return FaultScenario(**data)


def _dut_result():
    return VirtualDUT().calculate(12.0, 1.0)


def test_scenario_rejects_invalid_fault_type():
    with pytest.raises(ValueError):
        _scenario(fault_type="NOT_A_FAULT")


def test_scenario_rejects_measurement_type_on_query():
    with pytest.raises(ValueError):
        _scenario(fault_type=FaultType.NAN_VALUE, target=FaultTarget.INSTRUMENT_QUERY)


def test_scenario_rejects_shutdown_outside_cleanup():
    with pytest.raises(ValueError):
        _scenario(fault_type=FaultType.SHUTDOWN_FAILURE, operation="OUTP 0")


def test_scenario_rejects_zero_occurrences():
    with pytest.raises(ValueError):
        _scenario(occurrences=0)


def test_scenario_rejects_offset_without_offset_type():
    with pytest.raises(ValueError):
        _scenario(offset=0.3)


def test_scenario_requires_nonzero_offset_for_offset_type():
    with pytest.raises(ValueError):
        _scenario(
            fault_type=FaultType.VOLTAGE_OFFSET,
            target=FaultTarget.MODEL_MEASUREMENT,
            operation="vout",
            device=None,
            offset=0.0,
        )


def test_scenario_rejects_unknown_measurement_field():
    with pytest.raises(ValueError):
        _scenario(
            fault_type=FaultType.NAN_VALUE,
            target=FaultTarget.MODEL_MEASUREMENT,
            operation="banana",
            device=None,
        )


def test_scenario_file_loads_nine_unique_scenarios():
    library = load_fault_scenarios(ROOT / "configs" / "fault_scenarios.yaml")
    assert library.ids() == [f"F00{i}" for i in range(1, 10)]
    assert len(set(library.ids())) == 9


def test_scenario_library_rejects_duplicate_ids():
    with pytest.raises(ValueError):
        FaultScenarioLibrary([_scenario(), _scenario()])


def test_injector_disabled_by_default():
    injector = ScenarioFaultInjector([_scenario()])
    assert injector.enabled is False
    assert injector.before_query("VOLT?", device="PS001") is None
    assert injector.events == []


def test_injector_trigger_and_occurrence_are_exact():
    injector = ScenarioFaultInjector(
        [_scenario(trigger_at=2, occurrences=1)], enabled=True
    )
    assert injector.before_query("VOLT?", device="PS001") is None
    with pytest.raises(CommunicationTimeoutError):
        injector.before_query("VOLT?", device="PS001")
    assert injector.before_query("VOLT?", device="PS001") is None
    assert injector.call_counts["T001"] == 3
    assert injector.injected_counts["T001"] == 1
    assert len(injector.events) == 1


def test_injector_filters_device_and_case():
    injector = ScenarioFaultInjector(
        [_scenario(device="DMM001")], enabled=True, case_id="CASE-A"
    )
    assert injector.before_query("VOLT?", device="PS001") is None
    injector = ScenarioFaultInjector(
        [_scenario(case_id="CASE-B")], enabled=True, case_id="CASE-A"
    )
    assert injector.before_query("VOLT?", device="PS001") is None


def test_injector_invalid_response_returns_text():
    injector = ScenarioFaultInjector(
        [_scenario(fault_type=FaultType.INVALID_RESPONSE)], enabled=True
    )
    assert injector.before_query("VOLT?", device="PS001") == INVALID_RESPONSE_TEXT


def test_injector_disconnect_is_session_lost_error():
    injector = ScenarioFaultInjector(
        [_scenario(fault_type=FaultType.DISCONNECT)], enabled=True
    )
    with pytest.raises(DeviceDisconnectedError) as excinfo:
        injector.before_query("VOLT?", device="PS001")
    assert isinstance(excinfo.value, InstrumentSessionLostError)


def test_injector_conflicting_scenarios_rejected():
    left = _scenario(scenario_id="A001")
    right = _scenario(scenario_id="B001")
    with pytest.raises(ValueError):
        ScenarioFaultInjector([left, right], enabled=True)


def test_injector_cleanup_shutdown_failure():
    injector = ScenarioFaultInjector(
        [
            _scenario(
                fault_type=FaultType.SHUTDOWN_FAILURE,
                target=FaultTarget.CLEANUP,
                operation="OUTP 0",
            )
        ],
        enabled=True,
    )
    with pytest.raises(UnsafeShutdownError):
        injector.before_cleanup("OUTP 0", device="PS001")


def test_measurement_nan_changes_view_not_original():
    result = _dut_result()
    injector = ScenarioFaultInjector(
        [
            _scenario(
                fault_type=FaultType.NAN_VALUE,
                target=FaultTarget.MODEL_MEASUREMENT,
                operation="vout",
                device=None,
            )
        ],
        enabled=True,
    )
    view = apply_measurement_faults(result, injector)
    assert math.isnan(view.vout)
    assert result.vout == pytest.approx(4.98)
    assert view.source == FAULT_INJECTED_SOURCE
    assert view.pout == result.pout


def test_measurement_consistent_offset_recomputes_power():
    result = _dut_result()
    injector = ScenarioFaultInjector(
        [
            _scenario(
                fault_type=FaultType.VOLTAGE_OFFSET,
                target=FaultTarget.MODEL_MEASUREMENT,
                operation="vout",
                device=None,
                offset=-0.3,
            )
        ],
        enabled=True,
    )
    view = apply_measurement_faults(result, injector, consistent=True)
    assert view.vout == pytest.approx(result.vout - 0.3)
    assert view.pout == pytest.approx(view.vout * view.iout)
    assert view.pin == pytest.approx(view.vin * view.iin)
    assert view.power_loss == pytest.approx(view.pin - view.pout)
    assert view.efficiency == pytest.approx(result.efficiency)
    assert result.vout == pytest.approx(4.98)


def test_measurement_inconsistent_offset_keeps_original_power():
    result = _dut_result()
    injector = ScenarioFaultInjector(
        [
            _scenario(
                fault_type=FaultType.VOLTAGE_OFFSET,
                target=FaultTarget.MODEL_MEASUREMENT,
                operation="vout",
                device=None,
                offset=-0.3,
            )
        ],
        enabled=True,
    )
    view = apply_measurement_faults(result, injector, consistent=False)
    assert view.vout == pytest.approx(result.vout - 0.3)
    assert view.pout == result.pout
    assert view.pin == result.pin
    assert view.source == FAULT_INJECTED_SOURCE
