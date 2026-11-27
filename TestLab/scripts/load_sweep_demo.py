"""多工况负载扫描：12 V 输入下从空载扫描到过流保护。

输出 CSV 与 HTML 图表均基于行为模型计算结果，不是真实测量。
每次运行使用唯一编号，避免覆盖历史记录。
"""

from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from bench.virtual_test_bench import VirtualTestBench
from core.paths import RESULTS_DIR
from instruments.manager import InstrumentManager
from models.virtual_dut import VirtualDUT

ROOT = Path(__file__).resolve().parents[1]
INSTRUMENT_CONFIG = ROOT / "configs" / "instruments.yaml"
DUT_CONFIG = ROOT / "configs" / "dut_config.yaml"

LOAD_CURRENTS = [
    0.0,
    0.25,
    0.5,
    0.75,
    1.0,
    1.25,
    1.5,
    1.75,
    2.0,
    2.25,
    2.5,
]

CSV_FIELDS = (
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
    "efficiency",
    "state",
    "source",
)


def run_sweep() -> pd.DataFrame:
    """执行负载扫描并返回实际计算结果表。"""
    dut = VirtualDUT.from_yaml(DUT_CONFIG)
    records: list[dict[str, object]] = []

    with InstrumentManager(INSTRUMENT_CONFIG) as manager:
        bench = VirtualTestBench(manager, dut)
        psu = bench.psu
        load = bench.load

        try:
            psu.set_output(False)
            load.set_input(False)

            psu.set_voltage(12.0)
            psu.set_current(2.0)
            load.set_mode("CC")
            psu.set_output(True)
            load.set_input(True)

            for current in LOAD_CURRENTS:
                load.set_current(current)
                result = bench.read_state()
                row = asdict(result)
                # 枚举转为字符串，便于 CSV/HTML 展示
                row["state"] = getattr(result.state, "value", result.state)
                records.append(row)
        finally:
            try:
                load.set_input(False)
            finally:
                psu.set_output(False)

    return pd.DataFrame(records)[list(CSV_FIELDS)]


def build_figure(frame: pd.DataFrame) -> go.Figure:
    """绘制电压、功率、输入电流与效率随负载变化（2x2 子图）。"""
    currents = frame["load_current_setpoint"].tolist()
    efficiency = [
        None if pd.isna(value) else float(value) * 100.0
        for value in frame["efficiency"]
    ]

    fig = make_subplots(
        rows=2,
        cols=2,
        subplot_titles=(
            "输出电压 vs 负载电流",
            "输出功率 vs 负载电流",
            "输入电流 vs 负载电流",
            "转换效率 vs 负载电流",
        ),
    )

    fig.add_trace(
        go.Scatter(x=currents, y=frame["vout"], mode="lines+markers", name="Vout (V)"),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(x=currents, y=frame["pout"], mode="lines+markers", name="Pout (W)"),
        row=1,
        col=2,
    )
    fig.add_trace(
        go.Scatter(x=currents, y=frame["iin"], mode="lines+markers", name="Iin (A)"),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=currents,
            y=efficiency,
            mode="lines+markers",
            name="Efficiency (%)",
            connectgaps=False,
        ),
        row=2,
        col=2,
    )

    # 明确标注过流停机区域：负载 > 2 A 时模型输出归零
    overcurrent_start = float(frame["load_current_setpoint"].max()) - 0.25
    if overcurrent_start > 2.0:
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

    fig.add_annotation(
        x=0.5,
        y=-0.18,
        xref="paper",
        yref="paper",
        text="模型计算值，非真实测量；90% 为预设效率参数，空载/停机效率不可定义留空。",
        showarrow=False,
        font=dict(size=11, color="#666666"),
    )

    fig.update_xaxes(title_text="负载电流 (A)")
    fig.update_yaxes(title_text="电压 (V)", row=1, col=1)
    fig.update_yaxes(title_text="功率 (W)", row=1, col=2)
    fig.update_yaxes(title_text="电流 (A)", row=2, col=1)
    fig.update_yaxes(title_text="效率 (%)", row=2, col=2)
    fig.update_layout(
        title="VirtualDUT 负载扫描（12 V 输入，behavioral_model）",
        height=780,
        showlegend=False,
    )
    return fig


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]

    frame = run_sweep()
    csv_path = RESULTS_DIR / f"load_sweep_{run_id}.csv"
    html_path = RESULTS_DIR / f"load_sweep_{run_id}.html"

    frame.to_csv(csv_path, index=False, encoding="utf-8-sig")
    figure = build_figure(frame)
    figure.write_html(html_path)

    print(f"Run ID: {run_id}")
    print(
        frame[
            [
                "load_current_setpoint",
                "vout",
                "pout",
                "iin",
                "efficiency",
                "state",
            ]
        ].to_string(index=False)
    )
    print(f"CSV: {csv_path}")
    print(f"HTML: {html_path}")
    print("Load sweep: PASS")


if __name__ == "__main__":
    main()
