"""异常分类单元测试：按类型与状态码，不依赖异常字符串。"""

from __future__ import annotations

import pyvisa
import pytest
from pyvisa.constants import StatusCode

from instruments.exceptions import (
    InstrumentConnectionError,
    InstrumentNotConnectedError,
    InstrumentResponseError,
    InstrumentSessionLostError,
    InstrumentTimeoutError,
)
from reliability.error_classifier import (
    ErrorCategory,
    classify_error,
    is_retryable_category,
)
from reliability.exceptions import (
    CommunicationTimeoutError,
    DeviceDisconnectedError,
    InvalidResponseError,
    RetryExhaustedError,
    UnsafeShutdownError,
)


def _visa_error(code):
    error = pyvisa.errors.VisaIOError(code)
    return error


def test_timeout_category():
    assert classify_error(InstrumentTimeoutError("t")) is ErrorCategory.TRANSIENT_COMMUNICATION
    assert classify_error(CommunicationTimeoutError("t")) is ErrorCategory.TRANSIENT_COMMUNICATION


def test_disconnect_category():
    assert classify_error(InstrumentSessionLostError("d")) is ErrorCategory.DEVICE_DISCONNECTED
    assert classify_error(DeviceDisconnectedError("d")) is ErrorCategory.DEVICE_DISCONNECTED
    assert classify_error(InstrumentNotConnectedError("d")) is ErrorCategory.DEVICE_DISCONNECTED


def test_invalid_data_category():
    assert classify_error(InstrumentResponseError("bad")) is ErrorCategory.INVALID_DATA
    assert classify_error(InvalidResponseError("bad")) is ErrorCategory.INVALID_DATA


def test_shutdown_category():
    assert classify_error(UnsafeShutdownError("off")) is ErrorCategory.SHUTDOWN_ERROR


def test_configuration_category():
    assert classify_error(ValueError("bad value")) is ErrorCategory.CONFIGURATION_ERROR
    assert classify_error(TypeError("bad type")) is ErrorCategory.CONFIGURATION_ERROR


def test_unknown_category_is_default():
    assert classify_error(RuntimeError("boom")) is ErrorCategory.UNKNOWN_ERROR
    assert classify_error(InstrumentConnectionError("io")) is ErrorCategory.DEVICE_DISCONNECTED


def test_visa_timeout_code_maps_to_transient():
    assert (
        classify_error(_visa_error(StatusCode.error_timeout))
        is ErrorCategory.TRANSIENT_COMMUNICATION
    )


def test_visa_connection_lost_maps_to_disconnect():
    code = getattr(StatusCode, "error_connection_lost", None)
    if code is None:
        pytest.skip("当前 PyVISA 版本没有 error_connection_lost")
    assert classify_error(_visa_error(code)) is ErrorCategory.DEVICE_DISCONNECTED


def test_visa_other_code_is_unknown():
    assert classify_error(_visa_error(StatusCode.error_invalid_parameter)) is ErrorCategory.UNKNOWN_ERROR


def test_retry_exhausted_keeps_last_category():
    error = RetryExhaustedError("exhausted", category=ErrorCategory.TRANSIENT_COMMUNICATION)
    assert classify_error(error) is ErrorCategory.TRANSIENT_COMMUNICATION


def test_retryable_categories_only_transient():
    assert is_retryable_category(ErrorCategory.TRANSIENT_COMMUNICATION) is True
    assert is_retryable_category(ErrorCategory.DEVICE_DISCONNECTED) is False
    assert is_retryable_category(ErrorCategory.INVALID_DATA) is False
    assert is_retryable_category(ErrorCategory.UNKNOWN_ERROR) is False
