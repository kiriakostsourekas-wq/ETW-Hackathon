from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).parent / "src"))

from batteryhack.analytics import action_windows, heuristic_threshold_schedule, validate_market_frame
from batteryhack.config import DEFAULT_DEMO_DATE, SOURCE_LINKS
from batteryhack.data_sources import load_market_bundle
from batteryhack.forecasting import structural_price_forecast
from batteryhack.optimizer import BatteryParams, optimize_battery_schedule


st.set_page_config(
    page_title="Greek BESS Optimizer",
    page_icon="BESS",
    layout="wide",
)

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.2rem; padding-bottom: 2rem;}
    h1 {letter-spacing: 0;}
    div[data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 0.85rem 1rem;
    }
    .source-badge {
        display: inline-block;
        border: 1px solid #cbd5e1;
        border-radius: 999px;
        padding: 0.15rem 0.55rem;
        margin: 0 0.25rem 0.25rem 0;
        background: #fff;
        color: #334155;
        font-size: 0.82rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(ttl=3600, show_spinner=False)
def cached_bundle(delivery_date_iso: str):
    bundle = load_market_bundle(date.fromisoformat(delivery_date_iso))
    return bundle.frame, bundle.sources, bundle.warnings


def format_eur(value: float) -> str:
    return f"EUR {value:,.0f}"


def format_mwh(value: float) -> str:
    return f"{value:,.1f} MWh"


def build_dispatch_chart(frame: pd.DataFrame, schedule: pd.DataFrame) -> go.Figure:
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Scatter(
            x=frame["timestamp"],
            y=frame["dam_price_eur_mwh"],
            name="DAM price",
            mode="lines",
            line=dict(color="#0f172a", width=2.6),
            hovertemplate="%{x|%H:%M}<br>%{y:.2f} EUR/MWh<extra></extra>",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=frame["timestamp"],
            y=frame["forecast_price_eur_mwh"],
            name="Forecast proxy",
            mode="lines",
            line=dict(color="#64748b", width=2, dash="dot"),
            hovertemplate="%{x|%H:%M}<br>%{y:.2f} EUR/MWh<extra></extra>",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Bar(
            x=schedule["timestamp"],
            y=-schedule["charge_mw"],
            name="Charge",
            marker_color="#2563eb",
            opacity=0.72,
            hovertemplate="%{x|%H:%M}<br>%{y:.2f} MW<extra></extra>",
        ),
        secondary_y=True,
    )
    fig.add_trace(
        go.Bar(
            x=schedule["timestamp"],
            y=schedule["discharge_mw"],
            name="Discharge",
            marker_color="#f97316",
            opacity=0.78,
            hovertemplate="%{x|%H:%M}<br>%{y:.2f} MW<extra></extra>",
        ),
        secondary_y=True,
    )
    fig.update_layout(
        height=430,
        margin=dict(l=10, r=10, t=35, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        bargap=0.02,
        hovermode="x unified",
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
    )
    fig.update_yaxes(title_text="EUR/MWh", secondary_y=False, gridcolor="#e2e8f0")
    fig.update_yaxes(title_text="MW", secondary_y=True, zeroline=True, zerolinecolor="#94a3b8")
    fig.update_xaxes(showgrid=False)
    return fig


def build_soc_chart(schedule: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=schedule["timestamp"],
            y=schedule["soc_pct_end"],
            name="State of charge",
            mode="lines",
            fill="tozeroy",
            line=dict(color="#16a34a", width=2.4),
            hovertemplate="%{x|%H:%M}<br>%{y:.1f}%<extra></extra>",
        )
    )
    fig.update_layout(
        height=260,
        margin=dict(l=10, r=10, t=30, b=10),
        yaxis=dict(title="SoC %", range=[0, 100], gridcolor="#e2e8f0"),
        xaxis=dict(showgrid=False),
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
    )
    return fig


def build_system_chart(frame: pd.DataFrame) -> go.Figure:
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Scatter(
            x=frame["timestamp"],
            y=frame["load_forecast_mw"],
            name="Load forecast",
            mode="lines",
            line=dict(color="#7c3aed", width=2.2),
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=frame["timestamp"],
            y=frame["res_forecast_mw"],
            name="RES forecast",
            mode="lines",
            line=dict(color="#059669", width=2.2),
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=frame["timestamp"],
            y=frame["shortwave_radiation"],
            name="Solar radiation",
            mode="lines",
            line=dict(color="#f59e0b", width=1.8, dash="dot"),
        ),
        secondary_y=True,
    )
    fig.update_layout(
        height=330,
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        hovermode="x unified",
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
    )
    fig.update_yaxes(title_text="MW", secondary_y=False, gridcolor="#e2e8f0")
    fig.update_yaxes(title_text="W/m2", secondary_y=True)
    fig.update_xaxes(showgrid=False)
    return fig


with st.sidebar:
    st.header("Battery")
    delivery_date = st.date_input(
        "Delivery date",
        value=DEFAULT_DEMO_DATE,
        min_value=date(2025, 10, 1),
        max_value=date(2026, 12, 31),
    )
    preset = st.selectbox(
        "Asset preset",
        ["10 MW / 20 MWh", "20 MW / 80 MWh", "Custom"],
    )
    if preset == "10 MW / 20 MWh":
        default_power, default_capacity = 10.0, 20.0
    elif preset == "20 MW / 80 MWh":
        default_power, default_capacity = 20.0, 80.0
    else:
        default_power, default_capacity = 10.0, 40.0

    power_mw = st.number_input("Power MW", min_value=1.0, max_value=500.0, value=default_power, step=1.0)
    capacity_mwh = st.number_input(
        "Capacity MWh",
        min_value=1.0,
        max_value=2000.0,
        value=default_capacity,
        step=5.0,
    )
    round_trip_efficiency = st.slider("Round-trip efficiency", 0.70, 0.98, 0.90, 0.01)
    degradation_cost = st.slider("Degradation cost EUR/MWh throughput", 0.0, 25.0, 4.0, 0.5)
    min_soc, max_soc = st.slider("Operating SoC range", 0, 100, (10, 90), 5)
    initial_soc = st.slider("Initial and terminal SoC", min_soc, max_soc, 50, 5)
    use_cycle_limit = st.checkbox("Limit daily cycles")
    max_cycles = st.slider("Max equivalent cycles", 0.25, 3.0, 1.5, 0.25) if use_cycle_limit else None

params = BatteryParams(
    power_mw=power_mw,
    capacity_mwh=capacity_mwh,
    round_trip_efficiency=round_trip_efficiency,
    min_soc_pct=float(min_soc),
    max_soc_pct=float(max_soc),
    initial_soc_pct=float(initial_soc),
    terminal_soc_pct=float(initial_soc),
    degradation_cost_eur_mwh=degradation_cost,
    max_cycles_per_day=max_cycles,
)

st.title("Greek Day-Ahead Battery Optimizer")
st.caption("Constraint-aware BESS scheduling for Greece's 15-minute Day-Ahead Market.")

with st.spinner("Loading market, system, and weather data..."):
    market, sources, warnings = cached_bundle(delivery_date.isoformat())

market = market.copy()
market["forecast_price_eur_mwh"] = structural_price_forecast(market)
validation_issues = validate_market_frame(market)

try:
    output = optimize_battery_schedule(market, params)
    schedule = output.schedule
    metrics = output.metrics
except Exception as exc:  # noqa: BLE001
    st.error(f"Optimization failed: {exc}")
    st.stop()

heuristic = heuristic_threshold_schedule(market, params.power_mw, params.capacity_mwh)
uplift = metrics["gross_revenue_eur"] - heuristic["heuristic_gross_revenue_eur"]

source_html = "".join(
    f'<span class="source-badge">{name}</span>' for name in sources
)
st.markdown(source_html, unsafe_allow_html=True)
if warnings:
    with st.expander("Data source notes", expanded=False):
        for warning in warnings[:8]:
            st.write(f"- {warning}")
if validation_issues:
    st.warning(" | ".join(validation_issues))

metric_cols = st.columns(6)
metric_cols[0].metric("Net profit", format_eur(metrics["net_revenue_eur"]))
metric_cols[1].metric("Gross arbitrage", format_eur(metrics["gross_revenue_eur"]))
metric_cols[2].metric("Degradation", format_eur(metrics["degradation_cost_eur"]))
metric_cols[3].metric("Discharged", format_mwh(metrics["discharged_mwh"]))
metric_cols[4].metric("Cycles", f"{metrics['equivalent_cycles']:.2f}")
metric_cols[5].metric("Spread captured", f"{metrics['captured_spread_eur_mwh']:.1f} EUR/MWh")

tab_dispatch, tab_signals, tab_story, tab_data = st.tabs(
    ["Dispatch", "Forecast Signals", "Business Case", "Data"]
)

with tab_dispatch:
    st.plotly_chart(build_dispatch_chart(market, schedule), use_container_width=True)
    left, right = st.columns([0.58, 0.42])
    with left:
        st.plotly_chart(build_soc_chart(schedule), use_container_width=True)
    with right:
        windows = action_windows(schedule)
        if windows.empty:
            st.info("The optimizer stays idle because spreads do not cover losses and degradation.")
        else:
            st.dataframe(
                windows.assign(
                    start=windows["start"].dt.strftime("%H:%M"),
                    end=windows["end"].dt.strftime("%H:%M"),
                    energy_mwh=windows["energy_mwh"].round(2),
                    avg_price=windows["avg_price"].round(2),
                ),
                hide_index=True,
                use_container_width=True,
            )
        st.metric("Uplift vs threshold heuristic", format_eur(uplift))

with tab_signals:
    st.plotly_chart(build_system_chart(market), use_container_width=True)
    signal_cols = st.columns(4)
    signal_cols[0].metric("Avg DAM", f"{market['dam_price_eur_mwh'].mean():.1f} EUR/MWh")
    signal_cols[1].metric("Min DAM", f"{market['dam_price_eur_mwh'].min():.1f} EUR/MWh")
    signal_cols[2].metric("Max DAM", f"{market['dam_price_eur_mwh'].max():.1f} EUR/MWh")
    signal_cols[3].metric("Avg net load", f"{(market['load_forecast_mw'] - market['res_forecast_mw']).mean():,.0f} MW")
    st.dataframe(
        market[
            [
                "timestamp",
                "dam_price_eur_mwh",
                "forecast_price_eur_mwh",
                "load_forecast_mw",
                "res_forecast_mw",
                "shortwave_radiation",
                "cloud_cover",
                "wind_speed_10m",
            ]
        ].assign(timestamp=market["timestamp"].dt.strftime("%H:%M")).round(2),
        hide_index=True,
        use_container_width=True,
    )

with tab_story:
    st.subheader("Why this is valuable")
    st.write(
        "The optimizer converts Greece's 15-minute DAM volatility into a feasible charge, "
        "idle, and discharge schedule while respecting power, energy, efficiency, SoC, "
        "terminal SoC, degradation, and optional cycle constraints."
    )
    st.write(
        "This is built for the realistic Greek starting point: market, system, and weather "
        "data are public, but standalone battery telemetry is scarce because BESS market "
        "participation only recently started."
    )
    st.subheader("METLEN angle")
    st.write(
        "METLEN has announced large Greek standalone and hybrid storage projects. A tool "
        "like this can support merchant dispatch planning, revenue sensitivity, and operator "
        "explainability before mature local battery histories exist."
    )
    st.subheader("Source map")
    st.markdown(
        "\n".join(
            [
                f"- [{name}]({url})"
                for name, url in {
                    **SOURCE_LINKS,
                    "METLEN standalone BESS": "https://www.metlengroup.com/news/press-releases/strategic-agreement-between-metlen-and-karatzis-group-for-the-largest-standalone-energy-storage-unit-in-greece/",
                    "METLEN hybrid project": "https://www.metlengroup.com/news/press-releases/strategic-partnership-between-metlen-and-tsakos-group-for-one-of-greece-s-largest-hybrid-power-generation-projects/",
                    "Green Tank curtailments": "https://thegreentank.gr/en/2026/02/02/admie-dec25-en/",
                }.items()
            ]
        )
    )

with tab_data:
    st.subheader("Loaded sources")
    for name, source in sources.items():
        st.write(f"**{name}:** {source}")
    st.subheader("Dispatch table")
    display = schedule.merge(
        market[
            [
                "timestamp",
                "load_forecast_mw",
                "res_forecast_mw",
                "shortwave_radiation",
                "cloud_cover",
            ]
        ],
        on="timestamp",
        how="left",
    )
    display["timestamp"] = display["timestamp"].dt.strftime("%Y-%m-%d %H:%M")
    st.dataframe(display.round(3), hide_index=True, use_container_width=True)
