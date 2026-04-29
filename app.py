from __future__ import annotations

import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).parent / "src"))

from batteryhack.analytics import (
    action_windows,
    heuristic_threshold_schedule,
    validate_market_frame,
)
from batteryhack.config import DEFAULT_DEMO_DATE, MTU_HOURS, SOURCE_LINKS
from batteryhack.comparable_projects import TOP_COMPARABLE_PROJECTS, comparable_projects_table
from batteryhack.data_sources import load_market_bundle
from batteryhack.forecasting import forecast_price_with_uncertainty
from batteryhack.optimizer import BatteryParams, optimize_battery_schedule
from batteryhack.presets import (
    BATTERY_PRESETS,
    METLEN_BASE_EFFICIENCY,
    METLEN_CYCLE_SENSITIVITIES,
    METLEN_DEGRADATION_SENSITIVITIES,
    METLEN_OPTIMISTIC_EFFICIENCY,
    METLEN_PRESET_NAME,
)
from batteryhack.signal_catalog import ranked_signal_candidates


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


def format_mw(value: float) -> str:
    return f"{value:,.0f} MW"


def settle_schedule_on_actual_prices(
    schedule: pd.DataFrame,
    market: pd.DataFrame,
    params: BatteryParams,
    optimization_price_col: str,
    settlement_price_col: str = "dam_price_eur_mwh",
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Reprice a forecast-built schedule against actual DAM for realized metrics."""
    output = schedule.copy()
    if optimization_price_col in output:
        output["optimization_price_eur_mwh"] = output[optimization_price_col]

    if settlement_price_col not in output.columns:
        output = output.merge(
            market[["timestamp", settlement_price_col]],
            on="timestamp",
            how="left",
        )
    output["settlement_price_eur_mwh"] = output[settlement_price_col]

    actual_prices = pd.to_numeric(output[settlement_price_col], errors="coerce").to_numpy(float)
    charge = output["charge_mw"].to_numpy(float)
    discharge = output["discharge_mw"].to_numpy(float)
    throughput = charge + discharge

    output["gross_revenue_eur"] = actual_prices * (discharge - charge) * MTU_HOURS
    output["degradation_cost_eur"] = params.degradation_cost_eur_mwh * throughput * MTU_HOURS
    output["net_revenue_eur"] = output["gross_revenue_eur"] - output["degradation_cost_eur"]

    charged_mwh = float(output["charge_mw"].sum() * MTU_HOURS)
    discharged_mwh = float(output["discharge_mw"].sum() * MTU_HOURS)
    avg_charge_price = (
        float((actual_prices * charge * MTU_HOURS).sum() / charged_mwh)
        if charged_mwh > 1e-9
        else 0.0
    )
    avg_discharge_price = (
        float((actual_prices * discharge * MTU_HOURS).sum() / discharged_mwh)
        if discharged_mwh > 1e-9
        else 0.0
    )

    metrics = {
        "gross_revenue_eur": float(output["gross_revenue_eur"].sum()),
        "degradation_cost_eur": float(output["degradation_cost_eur"].sum()),
        "net_revenue_eur": float(output["net_revenue_eur"].sum()),
        "charged_mwh": charged_mwh,
        "discharged_mwh": discharged_mwh,
        "equivalent_cycles": discharged_mwh / params.capacity_mwh,
        "avg_charge_price_eur_mwh": avg_charge_price,
        "avg_discharge_price_eur_mwh": avg_discharge_price,
        "captured_spread_eur_mwh": avg_discharge_price - avg_charge_price,
    }
    return output, metrics


def optimize_for_mode(
    market: pd.DataFrame,
    params: BatteryParams,
    market_mode: str,
) -> tuple[pd.DataFrame, dict[str, float], str]:
    price_col = price_column_for_market_mode(market_mode)
    output = optimize_battery_schedule(market, params, price_col=price_col)
    schedule, metrics = settle_schedule_on_actual_prices(output.schedule, market, params, price_col)
    return schedule, metrics, output.status


def price_column_for_market_mode(market_mode: str) -> str:
    return "forecast_price_eur_mwh" if market_mode.startswith("Forecast") else "dam_price_eur_mwh"


def optimize_selected_case(
    market: pd.DataFrame,
    params: BatteryParams,
    market_mode: str,
    dispatch_assumption: str,
    impact_params: object | None,
    impact_iterations: int,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float], str]:
    _ = (dispatch_assumption, impact_params, impact_iterations)
    schedule, metrics, status = optimize_for_mode(market, params, market_mode)
    metrics.update(
        {
            "price_taker_net_revenue_eur": metrics["net_revenue_eur"],
            "price_taker_gross_revenue_eur": metrics["gross_revenue_eur"],
            "revenue_haircut_eur": 0.0,
            "revenue_haircut_pct": 0.0,
        }
    )
    return schedule, market, metrics, status


def build_sensitivity_frame(
    market: pd.DataFrame,
    base_params: BatteryParams,
    market_mode: str,
    dispatch_assumption: str,
    impact_params: object | None,
    impact_iterations: int,
) -> pd.DataFrame:
    rows: list[dict[str, float | str]] = []
    for efficiency in (METLEN_BASE_EFFICIENCY, METLEN_OPTIMISTIC_EFFICIENCY):
        for cycle_limit in METLEN_CYCLE_SENSITIVITIES:
            for degradation in METLEN_DEGRADATION_SENSITIVITIES:
                case_params = replace(
                    base_params,
                    round_trip_efficiency=efficiency,
                    max_cycles_per_day=cycle_limit,
                    degradation_cost_eur_mwh=degradation,
                )
                try:
                    _, _, case_metrics, status = optimize_selected_case(
                        market,
                        case_params,
                        market_mode,
                        dispatch_assumption,
                        impact_params,
                        impact_iterations,
                    )
                    rows.append(
                        {
                            "dispatch_assumption": "Price-taker",
                            "efficiency_pct": efficiency * 100,
                            "cycle_limit": cycle_limit,
                            "degradation_eur_mwh": degradation,
                            "price_taker_net_revenue_eur": case_metrics[
                                "price_taker_net_revenue_eur"
                            ],
                            "net_revenue_eur": case_metrics["net_revenue_eur"],
                            "revenue_haircut_eur": case_metrics["revenue_haircut_eur"],
                            "gross_revenue_eur": case_metrics["gross_revenue_eur"],
                            "degradation_cost_eur": case_metrics["degradation_cost_eur"],
                            "discharged_mwh": case_metrics["discharged_mwh"],
                            "equivalent_cycles": case_metrics["equivalent_cycles"],
                            "captured_spread_eur_mwh": case_metrics["captured_spread_eur_mwh"],
                            "status": status,
                        }
                    )
                except Exception as exc:  # noqa: BLE001
                    rows.append(
                        {
                            "dispatch_assumption": "Price-taker",
                            "efficiency_pct": efficiency * 100,
                            "cycle_limit": cycle_limit,
                            "degradation_eur_mwh": degradation,
                            "price_taker_net_revenue_eur": 0.0,
                            "net_revenue_eur": 0.0,
                            "revenue_haircut_eur": 0.0,
                            "gross_revenue_eur": 0.0,
                            "degradation_cost_eur": 0.0,
                            "discharged_mwh": 0.0,
                            "equivalent_cycles": 0.0,
                            "captured_spread_eur_mwh": 0.0,
                            "status": f"failed: {exc}",
                        }
                    )
    return pd.DataFrame(rows)


def build_sensitivity_heatmap(sensitivity: pd.DataFrame, efficiency_pct: float) -> go.Figure:
    subset = sensitivity[sensitivity["efficiency_pct"] == efficiency_pct]
    pivot = subset.pivot(
        index="degradation_eur_mwh",
        columns="cycle_limit",
        values="net_revenue_eur",
    ).sort_index(ascending=False)
    fig = go.Figure(
        data=go.Heatmap(
            z=pivot.values,
            x=[f"{value:.1f}" for value in pivot.columns],
            y=[f"{value:.0f}" for value in pivot.index],
            colorscale="RdYlGn",
            colorbar=dict(title="EUR"),
            hovertemplate=(
                "Cycles %{x}/day<br>"
                "Degradation %{y} EUR/MWh<br>"
                "Net revenue EUR %{z:,.0f}<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        height=330,
        margin=dict(l=10, r=10, t=35, b=10),
        xaxis_title="Cycle budget",
        yaxis_title="Degradation cost",
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
    )
    return fig


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
    if {"forecast_low_eur_mwh", "forecast_high_eur_mwh"}.issubset(frame.columns):
        fig.add_trace(
            go.Scatter(
                x=frame["timestamp"],
                y=frame["forecast_high_eur_mwh"],
                name="Forecast band",
                mode="lines",
                line=dict(color="rgba(100,116,139,0)", width=0),
                hoverinfo="skip",
                showlegend=False,
            ),
            secondary_y=False,
        )
        fig.add_trace(
            go.Scatter(
                x=frame["timestamp"],
                y=frame["forecast_low_eur_mwh"],
                name="Forecast uncertainty",
                mode="lines",
                fill="tonexty",
                fillcolor="rgba(100,116,139,0.16)",
                line=dict(color="rgba(100,116,139,0)", width=0),
                hoverinfo="skip",
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
        list(BATTERY_PRESETS),
    )
    selected_preset = BATTERY_PRESETS[preset]

    st.caption(
        f"Duration {selected_preset.duration_hours:.2f}h | "
        f"usable energy {selected_preset.usable_energy_mwh:,.0f} MWh under "
        f"{selected_preset.min_soc_pct:.0f}-{selected_preset.max_soc_pct:.0f}% SoC."
    )

    power_mw = st.number_input(
        "Power MW",
        min_value=1.0,
        max_value=1000.0,
        value=selected_preset.power_mw,
        step=1.0,
    )
    capacity_mwh = st.number_input(
        "Capacity MWh",
        min_value=1.0,
        max_value=5000.0,
        value=selected_preset.capacity_mwh,
        step=5.0,
    )
    st.caption(f"Current duration: {capacity_mwh / power_mw:.2f} hours")

    round_trip_efficiency = st.slider(
        "Round-trip efficiency",
        0.70,
        0.98,
        selected_preset.round_trip_efficiency,
        0.01,
        help="METLEN case uses 85% base and 90% optimistic sensitivity.",
    )
    degradation_cost = st.number_input(
        "Degradation cost EUR/MWh throughput",
        min_value=0.0,
        max_value=100.0,
        value=selected_preset.degradation_cost_eur_mwh,
        step=0.5,
        help="Sensitivity assumption only; not a public fixed fact.",
    )
    min_soc, max_soc = st.slider(
        "Operating SoC range",
        0,
        100,
        (int(selected_preset.min_soc_pct), int(selected_preset.max_soc_pct)),
        5,
    )
    initial_soc = st.slider(
        "Initial SoC",
        min_soc,
        max_soc,
        int(selected_preset.initial_soc_pct),
        5,
    )
    terminal_soc = st.slider(
        "Terminal SoC",
        min_soc,
        max_soc,
        int(selected_preset.terminal_soc_pct),
        5,
    )
    cycle_options = ["No limit", "0.5 cycles/day", "1.0 cycles/day", "1.5 cycles/day", "Custom"]
    default_cycle = (
        f"{selected_preset.max_cycles_per_day:.1f} cycles/day"
        if selected_preset.max_cycles_per_day is not None
        else "No limit"
    )
    cycle_choice = st.selectbox(
        "Cycle budget",
        cycle_options,
        index=cycle_options.index(default_cycle) if default_cycle in cycle_options else 0,
    )
    if cycle_choice == "No limit":
        max_cycles = None
    elif cycle_choice == "Custom":
        max_cycles = st.slider("Custom max equivalent cycles", 0.25, 3.0, 1.0, 0.25)
    else:
        max_cycles = float(cycle_choice.split()[0])

    market_mode = st.selectbox(
        "Scheduling mode",
        ["Oracle DAM prices", "Forecast proxy schedule"],
        help=(
            "Oracle uses published DAM prices as the scheduling signal. Forecast proxy optimizes "
            "against the transparent forecast, then settles the result against actual DAM prices."
        ),
    )
    dispatch_assumption = "Price-taker"
    impact_iterations = 1
    run_sensitivity = st.checkbox(
        "Run METLEN sensitivity grid",
        value=preset == METLEN_PRESET_NAME,
    )

params = BatteryParams(
    power_mw=power_mw,
    capacity_mwh=capacity_mwh,
    round_trip_efficiency=round_trip_efficiency,
    min_soc_pct=float(min_soc),
    max_soc_pct=float(max_soc),
    initial_soc_pct=float(initial_soc),
    terminal_soc_pct=float(terminal_soc),
    degradation_cost_eur_mwh=degradation_cost,
    max_cycles_per_day=max_cycles,
)

impact_params = None

st.title("Greek Day-Ahead Battery Optimizer")
st.caption(
    "Constraint-aware BESS scheduling for Greece's 15-minute Day-Ahead Market, "
    "including a METLEN-scale 330 MW / 790 MWh case."
)

with st.spinner("Loading market, system, and weather data..."):
    market, sources, warnings = cached_bundle(delivery_date.isoformat())

market = market.copy()
forecast_output = forecast_price_with_uncertainty(pd.DataFrame(), market)
for column in [
    "forecast_price_eur_mwh",
    "forecast_low_eur_mwh",
    "forecast_high_eur_mwh",
    "forecast_model",
]:
    market[column] = forecast_output.frame[column]
validation_issues = validate_market_frame(market)

try:
    schedule, scenario_market, metrics, optimization_status = optimize_selected_case(
        market,
        params,
        market_mode,
        dispatch_assumption,
        impact_params,
        impact_iterations,
    )
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

asset_cols = st.columns(4)
asset_cols[0].metric("Power", format_mw(params.power_mw))
asset_cols[1].metric("Nameplate energy", format_mwh(params.capacity_mwh))
asset_cols[2].metric("Duration", f"{params.capacity_mwh / params.power_mw:.2f}h")
asset_cols[3].metric(
    "Usable SoC band",
    format_mwh(params.capacity_mwh * (params.max_soc_pct - params.min_soc_pct) / 100.0),
)

tab_story, tab_dispatch, tab_market_impact, tab_sensitivity, tab_trace = st.tabs(
    ["Story", "Dispatch", "Market Impact Test", "Sensitivity", "Data Trace"]
)

with tab_story:
    st.subheader("Submission Story")
    st.write(
        "Greek standalone BESS telemetry is still scarce, so the demo does not pretend to "
        "learn battery behavior from Greek history. It simulates a feasible METLEN-scale "
        "schedule from public prices, public system/weather signals, and explicit technical "
        "constraints."
    )
    story_cols = st.columns(3)
    with story_cols[0]:
        st.markdown("**1. Operating Hypothesis**")
        st.write(
            "Charge around low-price midday or high-RES intervals; discharge into late "
            "afternoon/evening scarcity when solar falls and net load rises."
        )
    with story_cols[1]:
        st.markdown("**2. Data Stack**")
        st.write(
            "HEnEx DAM prices, IPTO load/RES forecasts, and Open-Meteo weather build the "
            "15-minute market frame. Synthetic fallback exists only to keep the demo stable."
        )
    with story_cols[2]:
        st.markdown("**3. Simulation Loop**")
        st.write(
            "The MILP enforces power, SoC, terminal SoC, efficiency, degradation, cycle budget, "
            "and no simultaneous charge/discharge, then reports dispatch economics."
        )
    st.subheader("Operational Process")
    process = pd.DataFrame(
        [
            {
                "stage": "Pre-market planning",
                "what happens": "Forecast load, RES, weather, price shape, reserve headroom, and constraints.",
                "implemented": "Public market/system/weather frame and explicit battery assumptions.",
            },
            {
                "stage": "Day-ahead bidding",
                "what happens": "Choose charge/discharge windows and terminal SoC before delivery.",
                "implemented": "15-minute DAM optimization against oracle price or forecast proxy.",
            },
            {
                "stage": "Intraday re-optimization",
                "what happens": "Update for forecast errors, outages, price changes, and SoC risk.",
                "implemented": "Out of scope for v1; treated as the next market layer.",
            },
            {
                "stage": "Balancing and ancillary services",
                "what happens": "Reserve MW and SoC headroom when services beat pure arbitrage.",
                "implemented": "Documented boundary; future value-stacking extension.",
            },
            {
                "stage": "Settlement review",
                "what happens": "Calculate revenue, degradation, cycles, throughput, and realized spread.",
                "implemented": "Profit, degradation, discharged MWh, cycles, captured spread, sensitivity grid.",
            },
        ]
    )
    st.dataframe(process, hide_index=True, use_container_width=True)
    st.subheader("Assumptions That Stay Visible")
    assumption_cols = st.columns(4)
    assumption_cols[0].metric("METLEN case", "330 MW / 790 MWh")
    assumption_cols[1].metric("SoC convention", f"{params.min_soc_pct:.0f}-{params.max_soc_pct:.0f}%")
    assumption_cols[2].metric("Round-trip efficiency", f"{params.round_trip_efficiency:.0%}")
    assumption_cols[3].metric(
        "Cycle budget",
        "No limit" if params.max_cycles_per_day is None else f"{params.max_cycles_per_day:.1f}/day",
    )
    st.info(
        "Market-impact caveat: this dashboard assumes one METLEN-scale BESS is a price-taker. "
        "The separate HEnEx aggregated-curve experiment tests whether that assumption is "
        "defensible before adding any price-maker logic."
    )

with tab_dispatch:
    st.plotly_chart(build_dispatch_chart(scenario_market, schedule), use_container_width=True)
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

with tab_market_impact:
    st.subheader("Price-Taker Assumption Test")
    st.write(
        "The operating dashboard now optimizes the METLEN-scale BESS once against the selected "
        "MCP signal. Market impact is handled as an offline hypothesis test, not as a second "
        "dispatch loop."
    )
    test_cols = st.columns(4)
    test_cols[0].metric("Tested asset", "330 MW / 790 MWh")
    test_cols[1].metric("Median shift pass", "< 0.5 EUR/MWh")
    test_cols[2].metric("Revenue haircut pass", "< 2%")
    test_cols[3].metric("Valid coverage", ">= 80%")
    st.code(
        "PYTHONPATH=src python3 scripts/run_market_impact_experiment.py "
        "--start-date 2026-04-22 --curve-dir data/raw",
        language="bash",
    )
    st.write(
        "The experiment parses HEnEx `EL-DAM_AggrCurves_EN` files, re-clears each active "
        "15-minute interval after adding charge as extra buy demand or discharge as extra sell "
        "supply, and writes interval plus daily CSV summaries under `data/processed/`."
    )
    st.write(
        "If the result passes both thresholds, one METLEN-scale BESS is treated as negligible "
        "for national DAM MCP. If the median passes but p95 shift is high, the result is flagged "
        "as locally material. If fewer than 80% of active intervals validate, the result is "
        "inconclusive."
    )

with tab_sensitivity:
    st.subheader("METLEN Assumption Grid")
    st.write(
        "This grid keeps the selected power and energy fixed, using 330 MW / 790 MWh for "
        "the METLEN preset, and varies the uncertain parameters from the project brief: "
        "efficiency, cycle budget, and degradation cost. Each case is a price-taker dispatch; "
        "market impact is tested separately with HEnEx aggregated curves."
    )
    if run_sensitivity:
        with st.spinner("Running sensitivity cases..."):
            sensitivity = build_sensitivity_frame(
                market,
                params,
                market_mode,
                dispatch_assumption,
                impact_params,
                impact_iterations,
            )
        selected_efficiency = st.selectbox(
            "Heatmap efficiency",
            sorted(sensitivity["efficiency_pct"].unique()),
            index=0 if round_trip_efficiency <= 0.875 else 1,
            format_func=lambda value: f"{value:.0f}%",
        )
        st.plotly_chart(
            build_sensitivity_heatmap(sensitivity, float(selected_efficiency)),
            use_container_width=True,
        )
        st.dataframe(
            sensitivity.round(
                {
                    "efficiency_pct": 0,
                    "cycle_limit": 2,
                    "degradation_eur_mwh": 1,
                    "price_taker_net_revenue_eur": 0,
                    "net_revenue_eur": 0,
                    "revenue_haircut_eur": 0,
                    "gross_revenue_eur": 0,
                    "degradation_cost_eur": 0,
                    "discharged_mwh": 1,
                    "equivalent_cycles": 2,
                    "captured_spread_eur_mwh": 1,
                }
            ),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.info("Enable the sensitivity grid in the sidebar to run the full METLEN scenario set.")

with tab_trace:
    st.subheader("Signal And Source Traceability")
    st.plotly_chart(build_system_chart(scenario_market), use_container_width=True)
    signal_cols = st.columns(4)
    signal_cols[0].metric("Avg DAM", f"{market['dam_price_eur_mwh'].mean():.1f} EUR/MWh")
    signal_cols[1].metric("Min DAM", f"{market['dam_price_eur_mwh'].min():.1f} EUR/MWh")
    signal_cols[2].metric("Max DAM", f"{market['dam_price_eur_mwh'].max():.1f} EUR/MWh")
    signal_cols[3].metric(
        "Avg net load",
        f"{(market['load_forecast_mw'] - market['res_forecast_mw']).mean():,.0f} MW",
    )
    signal_columns = [
        "timestamp",
        "dam_price_eur_mwh",
        "forecast_price_eur_mwh",
        "forecast_low_eur_mwh",
        "forecast_high_eur_mwh",
        "load_forecast_mw",
        "res_forecast_mw",
        "shortwave_radiation",
        "cloud_cover",
        "wind_speed_10m",
    ]
    st.dataframe(
        scenario_market[signal_columns].assign(
            timestamp=scenario_market["timestamp"].dt.strftime("%H:%M")
        ).round(2),
        hide_index=True,
        use_container_width=True,
    )

    st.subheader("Research Framing")
    st.subheader("Data-Scarce Modeling Logic")
    st.write(
        "The project brief explicitly assumes scarce asset telemetry. The schedule is therefore "
        "built from public market, system, and weather signals plus hard battery constraints, "
        "instead of learning from historical Greek standalone BESS behavior."
    )
    st.subheader("METLEN-Scale Case")
    st.write(
        "The METLEN/Karatzis standalone storage project is modeled as a 330 MW / 790 MWh "
        "battery. The app treats 790 MWh as nameplate energy and reports the usable energy "
        "inside the selected SoC band separately."
    )
    st.write(
        "Round-trip efficiency, degradation cost, cycle budget, and starting/ending SoC are "
        "not treated as fixed public facts. They are exposed as assumptions because they can "
        "materially change dispatch and revenue."
    )
    st.subheader("Market Impact Hypothesis")
    st.write(
        "The production path first assumes one METLEN-scale BESS is a price-taker. That is a "
        "testable hypothesis, not a claim. Charging adds buy demand and discharging adds sell "
        "supply, so the right public test is HEnEx aggregated curve depth near each clearing price."
    )
    st.write(
        "The offline experiment re-clears each active 15-minute interval with the same dispatch "
        "schedule. It calls the BESS negligible only if median absolute MCP shift is below "
        "0.5 EUR/MWh and the revenue haircut is below 2%, with at least 80% valid interval coverage."
    )
    st.write(
        "Useful evidence base: CAISO shows large batteries charging in solar hours and discharging "
        "late afternoon/evening; NREL warns price-taker storage models can overestimate value "
        "when storage becomes price-making; Spain and California studies report spread compression "
        "as storage penetration grows. Those are framing references, while the Greek decision "
        "should come from HEnEx curve re-clearing."
    )
    st.subheader("Analogue Classification")
    analogue_classes = pd.DataFrame(
        [
            {
                "class": "Direct market/design analogues",
                "sources": "Italy/Terna, Spain/OMIE-REE",
                "how used": "Market design, storage procurement, PV-heavy price-shape context.",
            },
            {
                "class": "Storage valuation methods",
                "sources": "NREL, CAISO, public GitHub BESS optimizers",
                "how used": "Price-taker baseline, MILP structure, value-stacking boundary.",
            },
            {
                "class": "Operational regime-shift evidence",
                "sources": "AEMO Q4 2025, California/Spain storage price-impact studies",
                "how used": "Evidence that renewable/storage growth can suppress prices and compress spreads.",
            },
        ]
    )
    st.dataframe(analogue_classes, hide_index=True, use_container_width=True)
    st.subheader("Top GitHub Analogues")
    st.dataframe(
        pd.DataFrame(comparable_projects_table())[
            [
                "rank",
                "project",
                "region",
                "market_scope",
                "similarity_score",
                "what_we_can_get",
            ]
        ],
        hide_index=True,
        use_container_width=True,
    )
    for project in TOP_COMPARABLE_PROJECTS:
        with st.expander(f"{project.rank}. {project.name} - {project.similarity_score}/100"):
            st.markdown(f"[Repository]({project.url})")
            st.write(project.mental_model)
            st.write("Reusable patterns: " + " ".join(project.reusable_patterns))
            st.write("Embedded here: " + " ".join(project.embedded_decisions))
            st.write("Caution: " + project.caution)
    st.subheader("Model Boundaries")
    st.write(
        "The default model remains price-taker DAM arbitrage. Market impact is an offline "
        "HEnEx curve experiment, not a second optimization loop. The app still does not "
        "model balancing-market revenue, ancillary services, network constraints, tax effects, "
        "or vendor-specific thermal derating."
    )
    st.subheader("Source map")
    candidates = ranked_signal_candidates()
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "segment": candidate.segment,
                    "signal": candidate.signal,
                    "source": candidate.source,
                    "timing": candidate.timing_class,
                    "score": candidate.total_score,
                    "live": candidate.live_eligible,
                    "influence": candidate.influence,
                }
                for candidate in candidates
            ]
        ),
        hide_index=True,
        use_container_width=True,
    )
    st.markdown(
        "\n".join(
            [
                f"- [{name}]({url})"
                for name, url in {
                    **SOURCE_LINKS,
                    "METLEN standalone BESS": (
                        "https://www.metlengroup.com/news/press-releases/"
                        "strategic-agreement-between-metlen-and-karatzis-group-for-the-"
                        "largest-standalone-energy-storage-unit-in-greece/"
                    ),
                    "METLEN hybrid project": (
                        "https://www.metlengroup.com/news/press-releases/"
                        "strategic-partnership-between-metlen-and-tsakos-group-for-one-"
                        "of-greece-s-largest-hybrid-power-generation-projects/"
                    ),
                    "Terna storage reference study": (
                        "https://download.terna.it/terna/"
                        "Study_on_reference_technologies_for_electricity_storage_"
                        "January_2025_8de0262c6cf17ee.pdf"
                    ),
                    "Green Tank curtailments": (
                        "https://thegreentank.gr/en/2026/02/02/admie-dec25-en/"
                    ),
                    "CAISO 2024 battery report": (
                        "https://www.caiso.com/documents/2024-special-report-on-battery-storage-may-29-2025.pdf"
                    ),
                    "NREL storage price impact summary": "https://www.osti.gov/biblio/1845688",
                    "Spain BESS spread-compression study": (
                        "https://www.sciencedirect.com/science/article/pii/S2352484725008674"
                    ),
                    "California storage spread study": (
                        "https://www.sciencedirect.com/science/article/pii/S0140988321006241"
                    ),
                    "AEMO Q4 2025 renewable/storage note": (
                        "https://www.aemo.com.au/newsroom/media-release/"
                        "renewables-supply-more-than-half-of-quarterly-energy-supply"
                    ),
                }.items()
            ]
        )
    )
    st.subheader("Loaded sources")
    for name, source in sources.items():
        st.write(f"**{name}:** {source}")
    st.write(f"**Scheduling mode:** {market_mode}")
    st.write("**Market impact:** offline HEnEx curve experiment only")
    st.write(f"**Optimizer status:** {optimization_status}")
    st.subheader("Dispatch table")
    display = schedule.merge(
        scenario_market[
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
