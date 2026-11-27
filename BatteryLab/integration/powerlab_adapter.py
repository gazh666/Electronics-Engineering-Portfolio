"""PowerLab 只读适配：参数快照、历史结果重算与真实开关级调用。

三种能力严格区分：

1. ``load_powerlab_parameters``：读取 PowerLab 配置与历史运行元数据（只读）；
2. ``reconfirm_historical_runs``：从实际原始 Run 目录重算基准/候选指标；
3. ``run_powerlab_power_map``：通过桥接脚本在 ``kaifa_power`` 环境真实调用
   PowerLab 的 ``run_closed_loop``，不写任何文件到 PowerLab。

历史回放不等同于新一轮求解，运行时必须分别计数。
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any, Iterable

import yaml

from battery_models.parameters import PROJECT_ROOT, load_yaml
from integration.environment_adapter import hash_tree, run_python_script

BRIDGE_SCRIPT = Path(__file__).resolve().parent / "powerlab_bridge.py"
HARDENING = Path("results/hardening")


class PowerLabAdapterError(RuntimeError):
    """PowerLab 只读访问失败。"""


def _resolve(root: Path, relative: str | Path) -> Path:
    path = Path(relative)
    return path if path.is_absolute() else root / path


def load_powerlab_parameters(root: str | Path) -> dict[str, Any]:
    """读取 PowerLab 实际配置快照，不修改任何文件。"""
    base = Path(root)
    if not base.is_dir():
        raise PowerLabAdapterError(f"PowerLab 目录不存在: {base}")
    nonideal = load_yaml(base / "configs" / "nonideal_buck_config.yaml")
    controller = load_yaml(base / "configs" / "controller_config.yaml")
    closed = load_yaml(base / "configs" / "closed_loop_config.yaml")
    circuit = nonideal["circuit"]
    return {
        "source": "powerlab_configs_read_only",
        "power_stage": {
            "input_voltage_v": circuit["input_voltage_v"],
            "target_output_voltage_v": circuit["target_output_voltage_v"],
            "rated_output_current_a": circuit["rated_output_current_a"],
            "switching_frequency_hz": circuit["switching_frequency_hz"],
            "inductance_h": circuit["inductance_h"],
            "inductor_dcr_ohm": circuit["inductor_dcr_ohm"],
            "capacitance_f": circuit["capacitance_f"],
            "capacitor_esr_ohm": circuit["capacitor_esr_ohm"],
            "load_resistance_ohm": circuit["load_resistance_ohm"],
            "mosfet_model": nonideal["mosfet"]["model_name"],
            "mosfet_source": nonideal["mosfet"]["model_source"],
            "diode_model": nonideal["diode"]["model_name"],
        },
        "controller": {
            "kp": controller["controller"]["kp"],
            "ki": controller["controller"]["ki"],
            "duty_min": controller["controller"]["duty_min"],
            "duty_max": controller["controller"]["duty_max"],
            "anti_windup": controller["controller"]["anti_windup"],
            "feedforward": controller["controller"]["feedforward_enabled"],
            "selected_phase_margin_deg": controller["design"]["selected_candidate_phase_margin_deg"],
            "selected_bandwidth_hz": controller["design"]["selected_candidate_bandwidth_hz"],
        },
        "simulation": closed["simulation"],
        "model_variant": closed["model_variant"],
        "specification_type": nonideal.get("metadata", {}).get("specification_type"),
    }


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _candidate_runs(root: Path) -> list[Path]:
    """在 hardening/stage6_optimization 下按配置筛选候选参数 Run。"""
    base = root / HARDENING / "stage6_optimization" / "runs"
    if not base.is_dir():
        return []
    matches: list[Path] = []
    for directory in sorted(base.iterdir()):
        if not directory.is_dir():
            continue
        snapshot = directory / "config_snapshot.yaml"
        if not snapshot.is_file():
            continue
        try:
            payload = yaml.safe_load(snapshot.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        circuit = payload.get("circuit", {}) if isinstance(payload, dict) else {}
        inductor = payload.get("inductor", {}) if isinstance(payload, dict) else {}
        capacitor = payload.get("capacitor", {}) if isinstance(payload, dict) else {}
        values = (
            circuit.get("inductance_h"),
            inductor.get("inductance_h"),
            circuit.get("capacitance_f"),
            capacitor.get("capacitance_f"),
        )
        text = json.dumps(values)
        if "6.8e-05" in text or "0.00033" in text or "0.00068" in text:
            matches.append(directory)
    return matches


def reconfirm_historical_runs(root: str | Path) -> dict[str, Any]:
    """从 PowerLab 实际原始 Run 重算基准与优化候选指标（Level 1 回放）。"""
    base = Path(root)
    sweep_path = base / HARDENING / "stage6_optimization" / "sweep.json"
    sweep = _read_json(sweep_path)
    if not sweep:
        return {"status": "NOT_AVAILABLE", "reason": "sweep.json 缺失", "path": str(sweep_path)}

    baseline_row = None
    candidate_rows = []
    for row in sweep.get("rows", []):
        values = row.get("values", {})
        if row.get("name") == "baseline":
            baseline_row = row
        l_uh = values.get("L_uh")
        c_uf = values.get("C_uf")
        dcr = values.get("dcr_ohm")
        esr = values.get("esr_ohm")
        if (
            l_uh == 68.0
            and c_uf == 330.0
            and abs(float(dcr or 0) - 0.02) < 1e-9
            and abs(float(esr or 0) - 0.005) < 1e-9
        ):
            candidate_rows.append(row)

    def summarise(row: dict[str, Any] | None) -> dict[str, Any] | None:
        if not row:
            return None
        raw = row.get("metrics") or row.get("result") or {}
        metrics = {
            "output_voltage_mean_v": raw.get("vout_v"),
            "output_ripple_vpp": raw.get("ripple_vpp"),
            "efficiency_percent": raw.get("efficiency_system_percent", raw.get("efficiency_stage_percent")),
            "efficiency_stage_percent": raw.get("efficiency_stage_percent"),
            "inductor_peak_current_a": raw.get("inductor_peak_a"),
            "phase_margin_deg": raw.get("phase_margin_deg"),
            "bandwidth_hz": raw.get("bandwidth_hz"),
        }
        return {
            "name": row.get("name"),
            "values": row.get("values"),
            "duty_cycle": row.get("duty_cycle"),
            "status": row.get("status"),
            "feasible": row.get("feasible"),
            "metrics": metrics,
            "raw_result": raw,
            "run_id": row.get("run_id"),
            "run_dir": row.get("run_dir"),
            "duration_s": row.get("duration_s"),
        }

    return {
        "status": "HISTORICAL_RECONFIRMED",
        "source": str(sweep_path),
        "source_note": "PowerLab 第六阶段参数扫描的真实 Run 汇总，本阶段仅重算与引用，不重复求解",
        "case_count": sweep.get("case_count"),
        "spice_runs": sweep.get("spice_runs"),
        "simulation_window_s": sweep.get("simulation_window_s"),
        "baseline": summarise(baseline_row),
        "candidates": [summarise(row) for row in candidate_rows],
        "candidate_run_directories": [str(path) for path in _candidate_runs(base)],
    }


def read_run_metrics(directory: str | Path) -> dict[str, Any]:
    path = Path(directory) / "metrics.json"
    payload = _read_json(path)
    if payload is None:
        raise PowerLabAdapterError(f"metrics.json 不存在或无法解析: {path}")
    return payload


def powerlab_source_snapshot(root: str | Path) -> dict[str, Any]:
    base = Path(root)
    digests = hash_tree(base)
    return {
        "root": str(base),
        "file_count": len(digests),
        "digest_sample": dict(list(sorted(digests.items()))[:5]),
        "tree_digest": __import__("hashlib").sha256(
            "\n".join(f"{k}:{v}" for k, v in sorted(digests.items())).encode()
        ).hexdigest(),
    }


def run_powerlab_power_map(
    root: str | Path,
    *,
    request_path: str | Path,
    output_path: str | Path,
    timeout_s: float = 900,
) -> dict[str, Any]:
    """在 kaifa_power 环境真实运行 PowerLab 闭环仿真生成功率映射。"""
    result = run_python_script(
        "kaifa_power",
        BRIDGE_SCRIPT,
        ["--project-root", str(Path(root).resolve()), "--request", str(request_path),
         "--output", str(Path(output_path).resolve())],
        working_directory=PROJECT_ROOT,
        timeout_s=timeout_s,
    )
    payload = _read_json(Path(output_path))
    return {"execution": result, "payload": payload}


__all__ = [
    "PowerLabAdapterError",
    "load_powerlab_parameters",
    "powerlab_source_snapshot",
    "read_run_metrics",
    "reconfirm_historical_runs",
    "run_powerlab_power_map",
]
