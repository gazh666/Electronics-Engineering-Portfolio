"""取消标志与进程终止测试（第九阶段 Task 13）。"""

from __future__ import annotations

import os

import pytest

from jobs.cancellation import (
    CancellationFlag,
    process_alive,
    request_cancel,
    terminate_process,
)


def test_flag_absent_by_default(tmp_path):
    flag = CancellationFlag(tmp_path)
    assert flag.requested() is False
    assert flag.reason() is None


def test_request_cancel_writes_flag(tmp_path):
    request_cancel(tmp_path, reason="user requested cancel")
    flag = CancellationFlag(tmp_path)
    assert flag.requested() is True
    assert flag.reason() == "user requested cancel"


def test_request_cancel_is_atomic(tmp_path):
    request_cancel(tmp_path)
    assert not (tmp_path / "cancel.flag.tmp").exists()
    assert (tmp_path / "cancel.flag").is_file()


def test_flag_reads_reason_from_broken_json(tmp_path):
    (tmp_path / "cancel.flag").write_text("not-json", encoding="utf-8")
    assert CancellationFlag(tmp_path).reason() == "cancel flag present"


def test_current_process_is_alive():
    assert process_alive(os.getpid()) is True


@pytest.mark.parametrize("pid", [0, -1, 2_000_000_000])
def test_invalid_or_missing_pid_is_not_alive(pid):
    assert process_alive(pid) is False


@pytest.mark.parametrize("pid", [0, -3])
def test_terminate_rejects_invalid_pid(pid):
    with pytest.raises(ValueError):
        terminate_process(pid)


def test_terminate_already_exited_process():
    outcome = terminate_process(2_000_000_000)
    assert outcome["terminated"] is True
    assert outcome["already_exited"] is True
