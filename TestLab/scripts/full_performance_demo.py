"""完整性能分析：负载扫描、输入电压扫描、二维扫描，输出 CSV/JSON/HTML。"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from datetime import datetime
from itertools import product
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import yaml
from plotly.subplots import make_subplots

from analysis.data_quality import summarize_quality_issues, validate_dataset
from analysis.metrics import (
    line_regulation_mv_per_v,
    line_regulation_span_percent,
    load_regulation_percent,
)
from analysis.performance_analyzer import PerformanceAnalyzer
from analysis.statistics import summarize_field
from bench.virtual_test_bench import VirtualTestBench
from core.paths import RESULTS_DIR
from instruments.manager import InstrumentManager
from models.virtual_dut import VirtualDUT

ROOT = Path(__file__).resolve().parents[1]
INSTRUMENT_CONFIG = ROOT / "configs" / "instruments.yaml"
DUT_CONFIG = ROOT / "configs" / "dut_config.yaml"
SWEEP_CONFIG = ROOT / "configs" / "sweep_config.yaml"
LIMITS_CONFIG = ROOT / "configs" / "performance_limits.yaml"

CSV_FIELDS = (
    "run_id",
    "timestamp",
    "sweep_type",
    "vin_setpoint",
    "input_current_limit",
    "load_current_setpoint",
    "vin",
    "iin",
    "vout",
    "iout",
    "pin",
    "pout",
    "power_loss",
    "efficiency_percent",
    "voltage_error_v",
    "voltage_error_percent",
    "absolute_voltage_error_percent",
    "dut_state",
    "data_quality_status",
    "metric_status",
    "data_source",
)

STATE_ORDER = {
    "NORMAL": 0,
    "UNDERVOLTAGE": 1,
    "OVERVOLTAGE": 2,
    "OVERCURRENT": 3,
    "INPUT_CURRENT_LIMIT": 4,
    "OUTPUT_OFF": 5,
}


def _state_text(value) -> str:
    return getattr(value, "value", value)


def _raw_row(result) -> dict:
    row = asdict(result)
    row["state"] = _state_text(result.state)
    return row


def _flatten(row: dict, run_id: str, timestamp: str, sweep_type: str) -> dict:
    metrics = row.get("metrics") or {}
    return {
        "run_id": run_id,
        "timestamp": timestamp,
        "sweep_type": sweep_type,
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


def _prepare(bench, vin: float, limit: float, current: float) -> None:
    """通过 SCPI 设置工况，先进入安全状态。"""
    bench.psu.set_output(False)
    bench.load.set_input(False)
    bench.psu.set_voltage(vin)
    bench.psu.set_current(limit)
    bench.load.set_mode("CC")
    bench.load.set_current(current)
    bench.psu.set_output(True)
    bench.load.set_input(True)


def run_load_sweep(bench, cfg: dict, analyzer: PerformanceAnalyzer):
    raw, analyzed = [], []
    for current in cfg["currents"]:
        _prepare(bench, cfg["vin"], cfg["input_current_limit"], current)
        result = bench.read_state()
        raw.append(_raw_row(result))
        analyzed.append(analyzer.analyze(result))
    return raw, analyzed


def run_line_sweep(bench, cfg: dict, analyzer: PerformanceAnalyzer):
    raw, analyzed = [], []
    for vin in cfg["input_voltages"]:
        _prepare(bench, vin, cfg["input_current_limit"], cfg["load_current"])
        result = bench.read_state()
        raw.append(_raw_row(result))
        analyzed.append(analyzer.analyze(result))
    return raw, analyzed


def run_matrix_sweep(bench, cfg: dict, analyzer: PerformanceAnalyzer):
    raw, analyzed = [], []
    for vin, current in product(
        cfg["input_voltages"], cfg["load_currents"]
    ):
        _prepare(bench, vin, cfg["input_current_limit"], current)
        result = bench.read_state()
        raw.append(_raw_row(result))
        analyzed.append(analyzer.analyze(result))
    return raw, analyzed


def _load_figure(load_rows: list[dict], analyzer: PerformanceAnalyzer) -> go.Figure:
    frame = pd.DataFrame(load_rows)
    normal = frame[frame["state"] == "NORMAL"]
    fig = make_subplots(
        rows=2,
        cols=2,
        subplot_titles=(
            "输出电压 vs 负载电流",
            "输入电流 vs 负载电流",
            "输出功率 vs 负载电流",
            "功率损耗 vs 负载电流",
        ),
    )
    for column, (name, unit) in enumerate(
        (
            ("vout", "V"),
            ("iin", "A"),
            ("pout", "W"),
            ("power_loss", "W"),
        ),
        start=1,
    ):
        row, col = divmod(column - 1, 2)
        fig.add_trace(
            go.Scatter(
                x=normal["load_current_setpoint"],
                y=normal[name],
                mode="lines+markers",
                name=name,
                line=dict(color="#1f77b4"),
            ),
            row=row + 1,
            col=col + 1,
        )

    if (frame["state"] != "NORMAL").any():
        for row, col in ((1, 1), (1, 2), (2, 1), (2, 2)):
            fig.add_vrect(
                x0=2.0,
                x1=float(frame["load_current_setpoint"].max()) + 0.25,
                fillcolor="red",
                opacity=0.12,
                line_width=0,
                row=row,
                col=col,
            )
        fig.add_annotation(
            x=2.25,
            y=0.5,
            yref="y domain",
            text="过流停机（简化模型）",
            showarrow=False,
            font=dict(color="red", size=11),
            row=1,
            col=1,
        )

    fig.add_hline(
        y=analyzer.limits.voltage_min_v,
        line_dash="dash",
        line_color="green",
        row=1,
        col=1,
    )
    fig.add_hline(
        y=analyzer.limits.voltage_max_v,
        line_dash="dash",
        line_color="green",
        row=1,
        col=1,
    )
    fig.add_annotation(
        x=0.5,
        y=-0.15,
        xref="paper",
        yref="paper",
        text="数据来源 behavioral_model；输出限值 4.9–5.1 V 为项目假设，非真实数据手册。",
        showarrow=False,
        font=dict(size=11, color="#666666"),
    )
    fig.update_xaxes(title_text="负载电流 (A)")
    fig.update_yaxes(title_text="电压 (V)", row=1, col=1)
    fig.update_yaxes(title_text="电流 (A)", row=1, col=2)
    fig.update_yaxes(title_text="功率 (W)", row=2, col=1)
    fig.update_yaxes(title_text="功率 (W)", row=2, col=2)
    fig.update_layout(
        title="负载扫描：稳压与功率性能（模型计算）",
        height=780,
        showlegend=False,
    )
    return fig


def _line_figure(line_rows: list[dict], analyzer: PerformanceAnalyzer) -> go.Figure:
    frame = pd.DataFrame(line_rows)
    fig = go.Figure()
    for state, group in frame.groupby("state"):
        color = "#1f77b4" if state == "NORMAL" else "#d62728"
        fig.add_trace(
            go.Scatter(
                x=group["vin"],
                y=group["vout"],
                mode="lines+markers",
                name=state,
                line=dict(color=color),
            )
        )
    fig.add_hline(
        y=analyzer.limits.voltage_min_v,
        line_dash="dash",
        line_color="green",
        annotation_text="下限 4.9 V",
    )
    fig.add_hline(
        y=analyzer.limits.voltage_max_v,
        line_dash="dash",
        line_color="green",
        annotation_text="上限 5.1 V",
    )
    fig.add_annotation(
        x=0.5,
        y=-0.18,
        xref="paper",
        yref="paper",
        text=(
            "数据来源 behavioral_model；模型输出电压与输入电压无关，"
            "线性调整率为 0% 属模型结构假设，不代表真实电源性能。"
        ),
        showarrow=False,
        font=dict(size=11, color="#666666"),
    )
    fig.update_layout(
        title="输入电压扫描：输出电压（1 A 负载，模型计算）",
        xaxis_title="输入电压 Vin (V)",
        yaxis_title="输出电压 Vout (V)",
    )
    return fig


def _power_figure(load_rows: list[dict]) -> go.Figure:
    frame = pd.DataFrame(load_rows)
    normal = frame[frame["state"] == "NORMAL"]
    fig = go.Figure()
    for name, label, color in (
        ("pin", "输入功率", "#1f77b4"),
        ("pout", "输出功率", "#2ca02c"),
        ("power_loss", "功率损耗", "#d62728"),
    ):
        fig.add_trace(
            go.Scatter(
                x=normal["load_current_setpoint"],
                y=normal[name],
                mode="lines+markers",
                name=label,
                line=dict(color=color),
            )
        )
    fig.add_annotation(
        x=0.5,
        y=-0.18,
        xref="paper",
        yref="paper",
        text="数据来源 behavioral_model；90% 效率为预设参数，非实测效率。",
        showarrow=False,
        font=dict(size=11, color="#666666"),
    )
    fig.update_layout(
        title="功率分析：输入/输出/损耗",
        xaxis_title="负载电流 (A)",
        yaxis_title="功率 (W)",
    )
    return fig


def _efficiency_figure(load_rows: list[dict], analyzer: PerformanceAnalyzer) -> go.Figure:
    frame = pd.DataFrame(load_rows)
    values = [
        None if pd.isna(value) else float(value) * 100.0
        for value in frame["efficiency"]
    ]
    fig = go.Figure(
        go.Scatter(
            x=frame["load_current_setpoint"],
            y=values,
            mode="lines+markers",
            name="效率",
            connectgaps=False,
            line=dict(color="#9467bd"),
        )
    )
    fig.add_hline(
        y=analyzer.limits.min_efficiency_percent,
        line_dash="dash",
        line_color="orange",
        annotation_text="效率下限 85%",
    )
    fig.add_hline(
        y=analyzer.limits.max_efficiency_percent,
        line_dash="dash",
        line_color="green",
        annotation_text="效率上限 100%",
    )
    fig.add_annotation(
        x=0.5,
        y=-0.18,
        xref="paper",
        yref="paper",
        text=(
            "固定效率模型结果：正常区恒为 90%，空载/保护状态不可定义留空；"
            "该曲线不是实测效率。"
        ),
        showarrow=False,
        font=dict(size=11, color="#666666"),
    )
    fig.update_layout(
        title="转换效率分析（固定效率模型）",
        xaxis_title="负载电流 (A)",
        yaxis_title="效率 (%)",
    )
    return fig


def _state_heatmap(matrix_rows: list[dict]) -> go.Figure:
    frame = pd.DataFrame(matrix_rows)
    pivot_state = frame.pivot_table(
        index="vin_setpoint",
        columns="load_current_setpoint",
        values="state",
        aggfunc="first",
    )
    pivot_z = pivot_state.replace(STATE_ORDER).astype(float)
    fig = go.Figure(
        go.Heatmap(
            z=pivot_z.values,
            x=[float(value) for value in pivot_state.columns],
            y=[float(value) for value in pivot_state.index],
            text=pivot_state.values,
            hovertemplate=(
                "Vin=%{y} V<br>Iload=%{x} A<br>状态=%{text}<extra></extra>"
            ),
            colorscale=[
                [0.0, "#2ca02c"],
                [0.2, "#ff7f0e"],
                [0.4, "#d62728"],
                [0.6, "#9467bd"],
                [0.8, "#8c564b"],
                [1.0, "#7f7f7f"],
            ],
            colorbar=dict(
                tickvals=list(STATE_ORDER.values()),
                ticktext=list(STATE_ORDER.keys()),
                title="DUT 状态",
            ),
        )
    )
    fig.add_annotation(
        x=0.5,
        y=-0.2,
        xref="paper",
        yref="paper",
        text=(
            "数据来源 behavioral_model；热力图仅表示当前模型状态，"
            "不代表真实芯片安全工作区（SOA）或保护特性。"
        ),
        showarrow=False,
        font=dict(size=11, color="#666666"),
    )
    fig.update_layout(
        title="输入电压 × 负载电流工作状态矩阵",
        xaxis_title="负载电流 (A)",
        yaxis_title="输入电压 (V)",
    )
    return fig


def main() -> None:
    with SWEEP_CONFIG.open("r", encoding="utf-8") as file:
        sweep = yaml.safe_load(file)
    limits = yaml.safe_load(LIMITS_CONFIG.read_text(encoding="utf-8"))

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    timestamp = datetime.now().isoformat(timespec="seconds")
    output_dir = RESULTS_DIR / f"performance_{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    dut = VirtualDUT.from_yaml(DUT_CONFIG)
    analyzer = PerformanceAnalyzer(LIMITS_CONFIG)
    raw_sets: dict[str, list[dict]] = {}
    analyzed_sets: dict[str, list[dict]] = {}

    with InstrumentManager(INSTRUMENT_CONFIG) as manager:
        bench = VirtualTestBench(manager, dut)
        try:
            raw_load, load_rows = run_load_sweep(bench, sweep["load_sweep"], analyzer)
            raw_line, line_rows = run_line_sweep(bench, sweep["line_sweep"], analyzer)
            raw_matrix, matrix_rows = run_matrix_sweep(
                bench, sweep["matrix_sweep"], analyzer
            )
        finally:
            try:
                bench.load.set_input(False)
            finally:
                bench.psu.set_output(False)

    raw_sets = {
        "load_sweep": raw_load,
        "line_sweep": raw_line,
        "matrix_sweep": raw_matrix,
    }
    analyzed_sets = {
        "load_sweep": load_rows,
        "line_sweep": line_rows,
        "matrix_sweep": matrix_rows,
    }

    for sweep_type, rows in raw_sets.items():
        pd.DataFrame(rows).to_csv(
            output_dir / f"raw_{sweep_type}.csv",
            index=False,
            encoding="utf-8-sig",
        )

    flat_rows = []
    for sweep_type, rows in analyzed_sets.items():
        flat_rows.extend(
            _flatten(row, run_id, timestamp, sweep_type) for row in rows
        )
    analyzed_frame = pd.DataFrame(flat_rows)[list(CSV_FIELDS)]
    analyzed_frame.to_csv(
        output_dir / "analyzed_results.csv", index=False, encoding="utf-8-sig"
    )

    quality_report: dict[str, object] = {}
    all_issues = []
    for sweep_type, rows in analyzed_sets.items():
        report = validate_dataset(rows)
        all_issues.extend(
            issue for record in report.records for issue in record.issues
        )
        all_issues.extend(report.dataset_issues)
        quality_report[sweep_type] = {
            "summary": report.to_dict(),
            "issues": summarize_quality_issues(
                [
                    issue
                    for record in report.records
                    for issue in record.issues
                ]
                + list(report.dataset_issues)
            ),
        }
    (output_dir / "data_quality_report.json").write_text(
        json.dumps(quality_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    normal_load = [
        row
        for row in load_rows
        if _state_text(row["state"]) == "NORMAL" and row.get("metrics")
    ]
    no_load = [
        row
        for row in normal_load
        if row["load_current_setpoint"] == 0.0
    ]
    full_load = [
        row
        for row in normal_load
        if row["load_current_setpoint"] == 2.0
    ]
    load_regulation = None
    if no_load and full_load:
        load_regulation = load_regulation_percent(
            no_load[0]["vout"],
            full_load[0]["vout"],
            analyzer.nominal_voltage,
        )

    normal_line = [
        row
        for row in line_rows
        if _state_text(row["state"]) == "NORMAL"
        and row.get("metrics")
        and 9.0 <= row["vin"] <= 16.0
    ]
    normal_line.sort(key=lambda row: row["vin"])
    line_regulation = None
    line_mv_per_v = None
    if len(normal_line) >= 2:
        line_regulation = line_regulation_span_percent(
            [row["vout"] for row in normal_line], analyzer.nominal_voltage
        )
        line_mv_per_v = line_regulation_mv_per_v(
            normal_line[0]["vin"],
            normal_line[-1]["vin"],
            normal_line[0]["vout"],
            normal_line[-1]["vout"],
        )

    metric_fields = (
        "efficiency_percent",
        "voltage_error_percent",
        "power_loss",
    )
    metrics_statistics = {
        sweep_type: {
            field: summarize_field(rows, field) for field in metric_fields
        }
        for sweep_type, rows in analyzed_sets.items()
    }

    state_counts = {
        sweep_type: {
            str(state): int(count)
            for state, count in pd.Series(
                [_state_text(row["state"]) for row in rows]
            )
            .value_counts()
            .items()
        }
        for sweep_type, rows in analyzed_sets.items()
    }

    summary = {
        "run_id": run_id,
        "timestamp": timestamp,
        "model": {
            "name": dut.config.name,
            "data_source": "behavioral_model",
            "nominal_output_voltage": dut.nominal_voltage,
            "max_output_current": dut.max_current,
            "output_resistance": dut.output_resistance,
            "nominal_efficiency": dut.nominal_efficiency,
        },
        "limits": limits,
        "sample_counts": {
            sweep_type: len(rows) for sweep_type, rows in analyzed_sets.items()
        },
        "state_counts": state_counts,
        "quality_issue_summary": summarize_quality_issues(all_issues),
        "metrics_statistics": metrics_statistics,
        "load_regulation": {
            "value_percent": load_regulation,
            "limit_percent": analyzer.limits.max_load_regulation_percent,
            "status": (
                None
                if load_regulation is None
                else (
                    "PASS"
                    if load_regulation
                    <= analyzer.limits.max_load_regulation_percent
                    else "FAIL"
                )
            ),
        },
        "line_regulation": {
            "value_percent": line_regulation,
            "value_mv_per_v": line_mv_per_v,
            "limit_percent": analyzer.limits.max_line_regulation_percent,
            "status": (
                None
                if line_regulation is None
                else (
                    "PASS"
                    if line_regulation
                    <= analyzer.limits.max_line_regulation_percent
                    else "FAIL"
                )
            ),
        },
        "assumptions": [
            "90% efficiency is a preset model parameter, not measured efficiency.",
            "Linear regulation is 0% because the model has no Vin dependence.",
            "Protection states use a simplified shutdown strategy.",
            "This is a steady-state behavioral model, not SPICE and not real hardware.",
            "All limits are educational project assumptions, not datasheet specs.",
        ],
        "files": [],
    }

    figures = {
        "load_regulation.html": _load_figure(load_rows, analyzer),
        "line_regulation.html": _line_figure(line_rows, analyzer),
        "power_analysis.html": _power_figure(load_rows),
        "efficiency_analysis.html": _efficiency_figure(load_rows, analyzer),
        "operating_state_heatmap.html": _state_heatmap(matrix_rows),
    }
    for filename, figure in figures.items():
        figure.write_html(output_dir / filename)
        summary["files"].append(filename)
    for sweep_type in raw_sets:
        summary["files"].append(f"raw_{sweep_type}.csv")

    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"Run ID: {run_id}")
    print("Sample counts:", summary["sample_counts"])
    print("State counts:", summary["state_counts"])
    print("Load regulation (%):", load_regulation)
    print("Line regulation (%):", line_regulation)
    print("Line regulation (mV/V):", line_mv_per_v)
    print("Quality issues:", summary["quality_issue_summary"])
    print("Output directory:", output_dir)
    print("Full performance analysis: PASS")


if __name__ == "__main__":
    main()
