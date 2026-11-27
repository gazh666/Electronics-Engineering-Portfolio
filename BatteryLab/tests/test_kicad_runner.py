import json
import sys

import pytest

from eda_tools.kicad_runner import find_kicad_cli, probe_cli_help, run_kicad_command


def test_find_kicad_cli_with_invalid_configured_path(tmp_path):
    with pytest.raises(FileNotFoundError):
        find_kicad_cli(str(tmp_path / "missing_kicad-cli.exe"))


def test_find_kicad_cli_with_valid_configured_path(tmp_path):
    fake = tmp_path / "kicad-cli.exe"
    fake.write_text("", encoding="utf-8")
    assert find_kicad_cli(str(fake)) == str(fake.resolve())


def test_run_command_writes_json(tmp_path):
    result = run_kicad_command(
        sys.executable,
        ["-c", "print('hello')"],
        tmp_path,
        "demo_task",
    )
    assert result["status"] == "COMMAND_OK"
    assert result["returncode"] == 0
    assert "hello" in result["stdout"]

    report = tmp_path / "demo_task.json"
    assert report.is_file()
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["task"] == "demo_task"


def test_run_command_nonzero_exit(tmp_path):
    result = run_kicad_command(
        sys.executable,
        ["-c", "import sys; sys.exit(3)"],
        tmp_path,
        "nonzero_task",
    )
    assert result["status"] == "COMMAND_NONZERO"
    assert result["returncode"] == 3


def test_run_command_missing_executable(tmp_path):
    result = run_kicad_command(
        str(tmp_path / "no_such_binary"),
        ["--version"],
        tmp_path,
        "missing_binary",
    )
    assert result["status"] == "EXECUTION_ERROR"
    assert "error" in result


def test_run_command_timeout(tmp_path):
    result = run_kicad_command(
        sys.executable,
        ["-c", "import time; time.sleep(5)"],
        tmp_path,
        "timeout_task",
        timeout_s=0.5,
    )
    assert result["status"] == "TIMEOUT"
    assert result["returncode"] is None


def test_probe_help_records_each_group(tmp_path):
    results = probe_cli_help(
        sys.executable,
        [["-c", "print('a')"]],
        str(tmp_path),
    )
    assert len(results) == 1
    assert next(iter(results.values()))["returncode"] == 0
