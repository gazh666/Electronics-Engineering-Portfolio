"""输入电压扫描演示：固定 1 A 负载，计算线性调整率并导出图表。"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import yaml

from analysis.metrics import (
    line_regulation_mv_per_v,
    line_regulation_span_percent,
)
from analysis.performance_analyzer import PerformanceAnalyzer
from bench.virtual_test_bench import VirtualTestBench
from core.paths import RESULTS_DIR
from instruments.manager import InstrumentManager
from models.virtual_dut import VirtualDUT

ROOT = Path(__file__).resolve().parents[1]
INSTRUMENT_CONFIG = ROOT / "configs" / "instruments.yaml"
DUT_CONFIG = ROOT / "configs" / "dut_config.yaml"
SWEEP_CONFIG = ROOT / "configs" / "sweep_config.yaml"
LIMITS_CONFIG = ROOT / "configs" / "performance_limits.yaml"


def _state_text(value) -> str:
    return getattr(value, "value", value)


def _flatten(row: dict, run_id: str, timestamp: str) -> dict:
    """把分析记录展开为 CSV 字段。"""
    metrics = row.get("metrics") or {}
    return {
        "run_id": run_id,
        "timestamp": timestamp,
        "sweep_type": "line_sweep",
        "vin_setpoint": row.get("vin_setpoint"),
        "input_current_limit": row.get("input_current_limit"),
        "load_current_setpoint": row.get("load_current_setpoint"),
        "vin": row.get("vin"),
        "iin": row.get("iin"),
        "vout": row.get("vout"),
        "iout": row.get("iout"),
        "pin": row.get("pin"),
        "pout": row.get("pout"),
        "power_loss": row.get("power_loss"),
        "efficiency_percent": metrics.get("efficiency_percent"),
        "voltage_error_v": metrics.get("voltage_error_v"),
        "voltage_error_percent": metrics.get("voltage_error_percent"),
        "absolute_voltage_error_percent": metrics.get(
            "absolute_voltage_error_percent"
        ),
        "dut_state": _state_text(row.get("state")),
        "data_quality_status": row.get("data_quality_status"),
        "metric_status": row.get("metric_status"),
        "data_source": row.get("source"),
    }


def main() -> None:
    with SWEEP_CONFIG.open("r", encoding="utf-8") as file:
        sweep = yaml.safe_load(file)["line_sweep"]

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    timestamp = datetime.now().isoformat(timespec="seconds")
    output_dir = RESULTS_DIR / f"line_sweep_{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    dut = VirtualDUT.from_yaml(DUT_CONFIG)
    analyzer = PerformanceAnalyzer(LIMITS_CONFIG)
    raw_rows: list[dict] = []
    analyzed: list[dict] = []

    with InstrumentManager(INSTRUMENT_CONFIG) as manager:
        bench = VirtualTestBench(manager, dut)
        psu = bench.psu
        load = bench.load
        try:
            psu.set_output(False)
            load.set_input(False)
            psu.set_current(sweep["input_current_limit"])
            load.set_mode("CC")
            load.set_current(sweep["load_current"])
            psu.set_output(True)
            load.set_input(True)

            for vin in sweep["input_voltages"]:
                psu.set_voltage(vin)
                result = bench.read_state()
                raw = asdict(result)
                raw["state"] = _state_text(result.state)
                raw["vin"] = result.vin
                raw_rows.append(raw)
                analyzed.append(analyzer.analyze(result))
        finally:
            try:
                load.set_input(False)
            finally:
                psu.set_output(False)

    raw_frame = pd.DataFrame(raw_rows)
    analyzed_frame = pd.DataFrame(
        [_flatten(row, run_id, timestamp) for row in analyzed]
    )
    raw_frame.to_csv(
        output_dir / "raw_line_sweep.csv", index=False, encoding="utf-8-sig"
    )
    analyzed_frame.to_csv(
        output_dir / "analyzed_results.csv", index=False, encoding="utf-8-sig"
    )

    normal = [
        row
        for row in analyzed
        if _state_text(row["state"]) == "NORMAL"
        and row.get("metrics") is not None
    ]
    normal.sort(key=lambda row: row["vin"])
    span_percent = line_regulation_span_percent(
        [row["vout"] for row in normal], analyzer.nominal_voltage
    )
    mv_per_v = line_regulation_mv_per_v(
        normal[0]["vin"],
        normal[-1]["vin"],
        normal[0]["vout"],
        normal[-1]["vout"],
    )

    limit = analyzer.limits.max_line_regulation_percent
    summary = {
        "run_id": run_id,
        "line_regulation_percent": span_percent,
        "line_regulation_mv_per_v": mv_per_v,
        "limit_percent": limit,
        "status": "PASS" if span_percent <= limit else "FAIL",
        "normal_sample_count": len(normal),
        "note": (
            "当前模型输出电压不随输入电压变化，线性调整率为 0% 是模型结构"
            "决定的，不代表真实电源性能。"
        ),
    }
    (output_dir / "line_regulation_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    figure = go.Figure()
    for state, group in analyzed_frame.groupby("dut_state"):
        color = "#1f77b4" if state == "NORMAL" else "#d62728"
        figure.add_trace(
            go.Scatter(
                x=group["vin"],
                y=group["vout"],
                mode="lines+markers",
                name=state,
                line=dict(color=color),
                marker=dict(size=8),
            )
        )
    figure.add_hline(
        y=analyzer.limits.voltage_min_v,
        line_dash="dash",
        line_color="green",
        annotation_text="下限 4.9 V",
    )
    figure.add_hline(
        y=analyzer.limits.voltage_max_v,
        line_dash="dash",
        line_color="green",
        annotation_text="上限 5.1 V",
    )
    figure.add_vrect(
        x0=float(min(sweep["input_voltages"])) - 0.2,
        x1=9.0,
        fillcolor="orange",
        opacity=0.12,
        line_width=0,
    )
    figure.add_vrect(
        x0=16.0,
        x1=float(max(sweep["input_voltages"])) + 0.2,
        fillcolor="red",
        opacity=0.12,
        line_width=0,
    )
    figure.update_layout(
        title="输入电压扫描：输出电压（1 A 负载，行为模型计算）",
        xaxis_title="输入电压 Vin (V)",
        yaxis_title="输出电压 Vout (V)",
        annotations=[
            dict(
                x=8.4,
                y=4.2,
                text="欠压保护区",
                showarrow=False,
                font=dict(color="orange"),
            ),
            dict(
                x=16.6,
                y=4.2,
                text="过压保护区",
                showarrow=False,
                font=dict(color="red"),
            ),
            dict(
                x=0.5,
                y=-0.18,
                xref="paper",
                yref="paper",
                text="数据来源 behavioral_model；模型假设，非真实测量。",
                showarrow=False,
                font=dict(size=11, color="#666666"),
            ),
        ],
    )
    figure.write_html(output_dir / "line_regulation.html")

    print(f"Run ID: {run_id}")
    print(analyzed_frame.to_string(index=False))
    print("Normal samples:", len(normal))
    print("Line regulation (%):", span_percent)
    print("Line regulation (mV/V):", mv_per_v)
    print("Status:", summary["status"])
    print("Output directory:", output_dir)
    print("Line sweep: PASS")


if __name__ == "__main__":
    main()
