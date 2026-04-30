from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from math import isfinite
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import numpy as np
import pandas as pd

from .config import DEFAULT_DEMO_DATE, MTU_HOURS
from .data_sources import load_market_bundle
from .optimizer import BatteryParams, optimize_battery_schedule
from .production_forecast import build_price_taker_forecast, registry_to_dict


PROCESSED_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"

DEFAULT_ASSET = BatteryParams(
    power_mw=330.0,
    capacity_mwh=790.0,
    round_trip_efficiency=0.85,
    min_soc_pct=10.0,
    max_soc_pct=90.0,
    initial_soc_pct=50.0,
    terminal_soc_pct=50.0,
    degradation_cost_eur_mwh=4.0,
    max_cycles_per_day=1.5,
)


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _round(value: Any, digits: int = 2) -> float | None:
    number = _safe_float(value)
    return round(number, digits) if number is not None else None


def _parse_date(value: str | None) -> date:
    if not value:
        return DEFAULT_DEMO_DATE
    return date.fromisoformat(value)


def _param_float(query: dict[str, list[str]], key: str, default: float) -> float:
    raw = query.get(key, [None])[0]
    if raw in (None, ""):
        return default
    return float(raw)


def _param_optional_float(query: dict[str, list[str]], key: str, default: float | None) -> float | None:
    raw = query.get(key, [None])[0]
    if raw in (None, ""):
        return default
    lowered = str(raw).lower()
    if lowered in {"none", "null", "off"}:
        return None
    return float(raw)


def _param_int(query: dict[str, list[str]], key: str, default: int) -> int:
    raw = query.get(key, [None])[0]
    if raw in (None, ""):
        return default
    return int(raw)


def _params_from_query(query: dict[str, list[str]]) -> BatteryParams:
    return BatteryParams(
        power_mw=_param_float(query, "power_mw", DEFAULT_ASSET.power_mw),
        capacity_mwh=_param_float(query, "capacity_mwh", DEFAULT_ASSET.capacity_mwh),
        round_trip_efficiency=_param_float(
            query,
            "round_trip_efficiency",
            DEFAULT_ASSET.round_trip_efficiency,
        ),
        min_soc_pct=_param_float(query, "min_soc_pct", DEFAULT_ASSET.min_soc_pct),
        max_soc_pct=_param_float(query, "max_soc_pct", DEFAULT_ASSET.max_soc_pct),
        initial_soc_pct=_param_float(query, "initial_soc_pct", DEFAULT_ASSET.initial_soc_pct),
        terminal_soc_pct=_param_float(query, "terminal_soc_pct", DEFAULT_ASSET.terminal_soc_pct),
        degradation_cost_eur_mwh=_param_float(
            query,
            "degradation_cost_eur_mwh",
            DEFAULT_ASSET.degradation_cost_eur_mwh,
        ),
        max_cycles_per_day=_param_optional_float(
            query,
            "max_cycles_per_day",
            DEFAULT_ASSET.max_cycles_per_day,
        ),
    )


def _hourly_sparkline(frame: pd.DataFrame, column: str, reducer: str = "mean") -> list[float]:
    hourly = frame.copy()
    hourly["hour"] = pd.to_datetime(hourly["timestamp"]).dt.hour
    grouped = hourly.groupby("hour")[column]
    values = grouped.sum() if reducer == "sum" else grouped.mean()
    return [_round(value, 2) or 0.0 for value in values.iloc[:24]]


def _action_windows(series: pd.DataFrame) -> list[dict[str, Any]]:
    windows: list[dict[str, Any]] = []
    active_kind: str | None = None
    start_time: str | None = None
    last_time: str | None = None

    for row in series.itertuples(index=False):
        kind = None
        if row.charge_mw > 1e-4:
            kind = "Charging"
        elif row.discharge_mw > 1e-4:
            kind = "Discharging"

        time_label = row.time
        if kind != active_kind:
            if active_kind and start_time and last_time:
                windows.append({"kind": active_kind, "start": start_time, "end": last_time})
            active_kind = kind
            start_time = time_label if kind else None
        last_time = time_label

    if active_kind and start_time and last_time:
        windows.append({"kind": active_kind, "start": start_time, "end": last_time})
    return windows


def _load_json_artifact(processed_dir: Path, filename: str) -> tuple[Any | None, str | None]:
    path = processed_dir / filename
    if not path.exists():
        return None, "missing"
    try:
        with path.open("r", encoding="utf-8") as handle:
            return _json_safe(json.load(handle)), None
    except Exception as exc:  # noqa: BLE001 - dashboard evidence is optional
        return None, str(exc)


def _load_csv_artifact(
    processed_dir: Path,
    filename: str,
    max_rows: int = 12,
) -> tuple[list[dict[str, Any]] | None, str | None]:
    path = processed_dir / filename
    if not path.exists():
        return None, "missing"
    try:
        frame = pd.read_csv(path).head(max_rows)
        return _records(frame), None
    except Exception as exc:  # noqa: BLE001 - dashboard evidence is optional
        return None, str(exc)


def _load_cumulative_pnl_artifact(
    processed_dir: Path,
    filename: str = "strategy_comparison_daily.csv",
    ml_strategy: str = "ml_scarcity_ensemble",
    baseline_strategy: str = "uk_naive_baseline",
) -> tuple[list[dict[str, Any]] | None, str | None]:
    path = processed_dir / filename
    if not path.exists():
        return None, "missing"
    try:
        frame = pd.read_csv(path)
        required = {"delivery_date", "strategy", "realized_net_revenue_eur"}
        missing_columns = required - set(frame.columns)
        if missing_columns:
            return None, f"missing columns: {', '.join(sorted(missing_columns))}"

        daily = frame[["delivery_date", "strategy", "realized_net_revenue_eur"]].copy()
        daily["realized_net_revenue_eur"] = pd.to_numeric(
            daily["realized_net_revenue_eur"],
            errors="coerce",
        )

        ml_daily = (
            daily[daily["strategy"] == ml_strategy]
            .groupby("delivery_date", as_index=False)["realized_net_revenue_eur"]
            .sum()
            .rename(columns={"realized_net_revenue_eur": "ml_daily_pnl_eur"})
        )
        baseline_daily = (
            daily[daily["strategy"] == baseline_strategy]
            .groupby("delivery_date", as_index=False)["realized_net_revenue_eur"]
            .sum()
            .rename(columns={"realized_net_revenue_eur": "baseline_daily_pnl_eur"})
        )
        cumulative = ml_daily.merge(baseline_daily, on="delivery_date", how="inner").sort_values(
            "delivery_date"
        )
        if cumulative.empty:
            return [], None

        cumulative["ml_cumulative_pnl_eur"] = cumulative["ml_daily_pnl_eur"].cumsum()
        cumulative["baseline_cumulative_pnl_eur"] = cumulative[
            "baseline_daily_pnl_eur"
        ].cumsum()
        cumulative["daily_uplift_eur"] = (
            cumulative["ml_daily_pnl_eur"] - cumulative["baseline_daily_pnl_eur"]
        )
        cumulative["cumulative_uplift_eur"] = cumulative["daily_uplift_eur"].cumsum()

        columns = [
            "delivery_date",
            "ml_daily_pnl_eur",
            "baseline_daily_pnl_eur",
            "ml_cumulative_pnl_eur",
            "baseline_cumulative_pnl_eur",
            "daily_uplift_eur",
            "cumulative_uplift_eur",
        ]
        return _records(cumulative[columns].round(2)), None
    except Exception as exc:  # noqa: BLE001 - dashboard evidence is optional
        return None, str(exc)


def _compact_future_market_impact(
    headline: dict[str, Any] | None,
    strategy_headline: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not headline:
        return None

    rows = headline.get("rows") or []
    available_models = [
        str(row.get("strategy_model")) for row in rows if row.get("strategy_model")
    ]
    preferred_candidates = [
        strategy_headline.get("best_ml_strategy") if strategy_headline else None,
        "ml_scarcity_ensemble",
        available_models[0] if available_models else None,
    ]
    preferred_model = next(
        (candidate for candidate in preferred_candidates if candidate in available_models),
        None,
    )
    if preferred_model is None:
        return None
    selected_rows = [row for row in rows if row.get("strategy_model") == preferred_model]

    scenario_order = {"conservative": 0, "base": 1, "aggressive": 2}
    scenarios = sorted(
        [
            {
                "scenario": row.get("scenario"),
                "fixed_schedule_degradation_pct": row.get("fixed_schedule_degradation_pct"),
                "reoptimized_degradation_pct": row.get("reoptimized_degradation_pct"),
                "reoptimization_recovery_eur": row.get("reoptimization_recovery_eur"),
                "interpretation_label": row.get("interpretation_label"),
                "sample_days": row.get("sample_days"),
            }
            for row in selected_rows
            if row.get("scenario") in scenario_order
        ],
        key=lambda row: scenario_order.get(str(row.get("scenario")), 99),
    )

    return _json_safe(
        {
            "generated_at": headline.get("generated_at"),
            "notice": headline.get(
                "notice",
                "Strategic spread-compression stress test only; not a Greek price forecast.",
            ),
            "strategy_model": preferred_model,
            "scenarios": scenarios,
            "available_models": sorted(set(available_models)),
        }
    )


def _evidence_payload(processed_dir: Path | None = None) -> dict[str, Any]:
    processed_dir = processed_dir or PROCESSED_DATA_DIR
    missing: list[str] = []
    errors: dict[str, str] = {}

    def remember(filename: str, error: str | None) -> None:
        if error == "missing":
            missing.append(filename)
        elif error:
            errors[filename] = error

    strategy_headline, error = _load_json_artifact(
        processed_dir,
        "strategy_comparison_headline.json",
    )
    remember("strategy_comparison_headline.json", error)
    strategy_summary, error = _load_csv_artifact(
        processed_dir,
        "strategy_comparison_summary.csv",
    )
    remember("strategy_comparison_summary.csv", error)
    cumulative_pnl, error = _load_cumulative_pnl_artifact(processed_dir)
    remember("strategy_comparison_daily.csv", error)
    model_stability, error = _load_csv_artifact(
        processed_dir,
        "ml_research_model_stability.csv",
    )
    remember("ml_research_model_stability.csv", error)
    paired_uplift, error = _load_csv_artifact(
        processed_dir,
        "ml_research_paired_uplift.csv",
    )
    remember("ml_research_paired_uplift.csv", error)
    future_headline, error = _load_json_artifact(
        processed_dir,
        "future_market_impact_headline.json",
    )
    remember("future_market_impact_headline.json", error)

    evidence: dict[str, Any] = {
        "available": False,
        "partial": False,
        "missing_artifacts": missing,
        "artifact_errors": errors,
    }

    if strategy_headline or strategy_summary or cumulative_pnl:
        evidence["strategy_comparison"] = {
            "headline": strategy_headline,
            "summary": strategy_summary or [],
            "cumulative_pnl": cumulative_pnl or [],
        }
    if model_stability:
        evidence["model_stability"] = model_stability
    if paired_uplift:
        evidence["paired_uplift"] = paired_uplift

    compact_future = _compact_future_market_impact(future_headline, strategy_headline)
    if compact_future:
        evidence["future_market_impact"] = compact_future

    available_sections = [
        key
        for key in (
            "strategy_comparison",
            "model_stability",
            "paired_uplift",
            "future_market_impact",
        )
        if key in evidence
    ]
    evidence["available"] = bool(available_sections)
    evidence["partial"] = bool(available_sections and (missing or errors))
    return _json_safe(evidence)


def build_dashboard_payload(
    delivery_date: date,
    params: BatteryParams,
    include_forecast: bool = True,
    forecast_history_days: int = 21,
    validation_days: int = 3,
) -> dict[str, Any]:
    bundle = load_market_bundle(delivery_date)
    market = bundle.frame.copy()
    market["timestamp"] = pd.to_datetime(market["timestamp"])
    market["net_load_mw"] = market["load_forecast_mw"] - market["res_forecast_mw"]

    output = optimize_battery_schedule(market, params)
    schedule_cols = [
        "timestamp",
        "interval",
        "charge_mw",
        "discharge_mw",
        "net_power_mw",
        "soc_pct_end",
        "gross_revenue_eur",
        "degradation_cost_eur",
        "net_revenue_eur",
        "action",
    ]
    series = market.merge(output.schedule[schedule_cols], on=["timestamp", "interval"], how="left")
    series["time"] = series["timestamp"].dt.strftime("%H:%M")
    series["battery_abs_mw"] = series[["charge_mw", "discharge_mw"]].max(axis=1)
    series["net_system_after_battery_mw"] = series["net_load_mw"] + series["charge_mw"] - series["discharge_mw"]
    series["res_share_pct"] = np.where(
        series["load_forecast_mw"] > 0,
        series["res_forecast_mw"] / series["load_forecast_mw"] * 100.0,
        np.nan,
    )

    total_load_mwh = float(series["load_forecast_mw"].sum() * MTU_HOURS)
    total_res_mwh = float(series["res_forecast_mw"].sum() * MTU_HOURS)
    res_share_pct = total_res_mwh / total_load_mwh * 100.0 if total_load_mwh else 0.0
    low_price = float(series["dam_price_eur_mwh"].min())
    high_price = float(series["dam_price_eur_mwh"].max())
    avg_price = float(series["dam_price_eur_mwh"].mean())
    charge_intervals = int((series["charge_mw"] > 1e-4).sum())
    discharge_intervals = int((series["discharge_mw"] > 1e-4).sum())
    public_price = bundle.sources.get("DAM prices", "").startswith("https://")

    metrics = {
        **{key: _round(value, 2) for key, value in output.metrics.items()},
        "total_load_mwh": _round(total_load_mwh, 2),
        "total_res_mwh": _round(total_res_mwh, 2),
        "res_share_pct": _round(res_share_pct, 2),
        "avg_price_eur_mwh": _round(avg_price, 2),
        "low_price_eur_mwh": _round(low_price, 2),
        "high_price_eur_mwh": _round(high_price, 2),
        "price_range_eur_mwh": _round(high_price - low_price, 2),
        "charge_intervals": charge_intervals,
        "discharge_intervals": discharge_intervals,
        "public_price_data": public_price,
    }

    kpis = [
        {
            "label": "Net Revenue",
            "value": f"EUR {metrics['net_revenue_eur']:,.0f}",
            "badge": "DAM",
            "detail": "After degradation cost",
            "sparkline": _hourly_sparkline(series, "net_revenue_eur", "sum"),
        },
        {
            "label": "Captured Spread",
            "value": f"EUR {metrics['captured_spread_eur_mwh']:,.2f}/MWh",
            "badge": "Dispatch",
            "detail": "Discharge minus charge price",
            "sparkline": _hourly_sparkline(series, "dam_price_eur_mwh"),
        },
        {
            "label": "Energy Shifted",
            "value": f"{metrics['discharged_mwh']:,.1f} MWh",
            "badge": "Discharged",
            "detail": f"{metrics['charged_mwh']:,.1f} MWh charged",
            "sparkline": _hourly_sparkline(series, "discharge_mw"),
        },
        {
            "label": "Equivalent Cycles",
            "value": f"{metrics['equivalent_cycles']:,.2f}",
            "badge": "Constraint",
            "detail": f"Limit {params.max_cycles_per_day or 'off'} / day",
            "sparkline": _hourly_sparkline(series, "soc_pct_end"),
            "active": True,
        },
    ]

    forecasting = {"available": False, "error": None}
    if include_forecast:
        try:
            production = build_price_taker_forecast(
                target_date=delivery_date,
                battery_params=params,
                history_start=delivery_date - timedelta(days=forecast_history_days),
                validation_days=validation_days,
            )
            forecast_metrics = _metrics_with_oracle(production.metrics, output.metrics)
            forecasting = _forecasting_payload(production, forecast_metrics)
            series = _merge_forecast_outputs(series, production)
            kpis = _forecast_kpis(production, forecast_metrics, series)
        except Exception as exc:  # noqa: BLE001 - dashboard should degrade gracefully
            forecasting = {
                "available": False,
                "error": str(exc),
                "status": "forecast pipeline unavailable; showing DAM optimizer only",
            }

    rows = []
    for row in series.itertuples(index=False):
        rows.append(
            {
                "timestamp": row.timestamp.isoformat(),
                "time": row.time,
                "interval": int(row.interval),
                "dam_price_eur_mwh": _round(row.dam_price_eur_mwh, 2),
                "load_forecast_mw": _round(row.load_forecast_mw, 2),
                "res_forecast_mw": _round(row.res_forecast_mw, 2),
                "net_load_mw": _round(row.net_load_mw, 2),
                "charge_mw": _round(row.charge_mw, 4),
                "discharge_mw": _round(row.discharge_mw, 4),
                "battery_net_mw": _round(row.net_power_mw, 4),
                "battery_abs_mw": _round(row.battery_abs_mw, 4),
                "soc_pct": _round(row.soc_pct_end, 2),
                "net_system_after_battery_mw": _round(row.net_system_after_battery_mw, 2),
                "res_share_pct": _round(row.res_share_pct, 2),
                "net_revenue_eur": _round(row.net_revenue_eur, 2),
                "action": row.action,
                "forecast_price_eur_mwh": _round(
                    getattr(row, "forecast_price_eur_mwh", None),
                    2,
                ),
                "forecast_low_eur_mwh": _round(getattr(row, "forecast_low_eur_mwh", None), 2),
                "forecast_high_eur_mwh": _round(getattr(row, "forecast_high_eur_mwh", None), 2),
                "forecast_charge_mw": _round(getattr(row, "forecast_charge_mw", None), 4),
                "forecast_discharge_mw": _round(
                    getattr(row, "forecast_discharge_mw", None),
                    4,
                ),
                "forecast_soc_pct": _round(getattr(row, "forecast_soc_pct", None), 2),
            }
        )

    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "delivery_date": delivery_date.isoformat(),
        "asset": {
            "name": "METLEN Thessaly BESS",
            "region": "Thessaly, Greece",
            "market": "HEnEx Day-Ahead Market",
            "mode": "DAM optimizer",
            "params": asdict(params),
            "duration_hours": _round(params.capacity_mwh / params.power_mw, 2),
            "usable_energy_mwh": _round(
                params.capacity_mwh * (params.max_soc_pct - params.min_soc_pct) / 100.0,
                2,
            ),
        },
        "data_quality": "public DAM price data" if public_price else "synthetic price fallback",
        "sources": bundle.sources,
        "warnings": bundle.warnings,
        "optional_unavailable": bundle.optional_unavailable,
        "optimizer_status": output.status,
        "metrics": metrics,
        "forecasting": forecasting,
        "evidence": _evidence_payload(),
        "kpis": kpis,
        "windows": _action_windows(series[["time", "charge_mw", "discharge_mw"]]),
        "series": rows,
    }


def _merge_forecast_outputs(series: pd.DataFrame, production) -> pd.DataFrame:
    base = production.forecast_frame[
        [
            "timestamp",
            "forecast_price_eur_mwh",
            "forecast_low_eur_mwh",
            "forecast_high_eur_mwh",
        ]
    ].copy()
    schedule = production.schedule[
        ["timestamp", "charge_mw", "discharge_mw", "soc_pct_end"]
    ].rename(
        columns={
            "charge_mw": "forecast_charge_mw",
            "discharge_mw": "forecast_discharge_mw",
            "soc_pct_end": "forecast_soc_pct",
        }
    )
    forecast_series = base.merge(schedule, on="timestamp", how="left")
    return series.merge(forecast_series, on="timestamp", how="left")


def _forecasting_payload(production, metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "available": True,
        "registry": _json_safe(registry_to_dict(production.registry)),
        "metrics": _json_safe(metrics),
        "assumptions": _json_safe(production.assumptions),
        "model_performance": _records(production.model_performance),
        "daily_model_performance": _records(production.daily_model_performance),
    }


def _metrics_with_oracle(
    forecast_metrics: dict[str, Any],
    oracle_metrics: dict[str, Any],
) -> dict[str, Any]:
    metrics = dict(forecast_metrics)
    oracle_net = oracle_metrics.get("net_revenue_eur")
    metrics["oracle_net_revenue_eur"] = oracle_net
    realized_net = metrics.get("price_taker_realized_net_revenue_eur")
    metrics["price_taker_capture_ratio_vs_oracle"] = (
        realized_net / oracle_net
        if oracle_net is not None and realized_net is not None and abs(oracle_net) > 1e-9
        else None
    )
    return metrics


def _forecast_kpis(production, metrics: dict[str, Any], series: pd.DataFrame) -> list[dict[str, Any]]:
    registry = production.registry
    capture = metrics.get("price_taker_capture_ratio_vs_oracle")
    return [
        {
            "label": "Forecast MAE",
            "value": f"EUR {metrics['base_forecast_mae_eur_mwh']:,.2f}/MWh",
            "badge": registry.selected_model,
            "detail": "Base forecast vs published DAM",
            "sparkline": _hourly_sparkline(series, "forecast_price_eur_mwh"),
        },
        {
            "label": "Forecast Dispatch Net",
            "value": f"EUR {metrics['price_taker_objective_net_revenue_eur']:,.0f}",
            "badge": "Price-taker",
            "detail": "One optimizer pass on forecast MCP",
            "sparkline": _hourly_sparkline(series, "forecast_charge_mw"),
        },
        {
            "label": "Realized Backtest",
            "value": f"EUR {metrics['price_taker_realized_net_revenue_eur']:,.0f}",
            "badge": "Published DAM",
            "detail": "Same schedule settled on actual MCP",
            "sparkline": _hourly_sparkline(series, "forecast_discharge_mw"),
        },
        {
            "label": "Capture vs Oracle",
            "value": f"{(capture or 0) * 100:,.1f}%",
            "badge": "Backtest",
            "detail": "Settled against published DAM",
            "sparkline": _hourly_sparkline(series, "forecast_soc_pct"),
            "active": True,
        },
    ]


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    return [_json_safe(record) for record in frame.to_dict(orient="records")]


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if pd.isna(value):
        return None
    return value


class DashboardRequestHandler(BaseHTTPRequestHandler):
    server_version = "BatteryHackAPI/0.1"

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802 - stdlib handler name
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler name
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        try:
            if parsed.path == "/api/health":
                self._send_json({"ok": True, "service": "batteryhack-api"})
                return

            if parsed.path == "/api/dashboard":
                include_forecast = query.get("include_forecast", ["true"])[0].lower() != "false"
                payload = build_dashboard_payload(
                    delivery_date=_parse_date(query.get("date", [None])[0]),
                    params=_params_from_query(query),
                    include_forecast=include_forecast,
                    forecast_history_days=_param_int(query, "forecast_history_days", 21),
                    validation_days=_param_int(query, "validation_days", 3),
                )
                self._send_json(payload)
                return

            self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:  # noqa: BLE001 - API should return JSON errors
            self._send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the ETW battery dashboard JSON API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), DashboardRequestHandler)
    print(f"BatteryHack API listening on http://{args.host}:{args.port}")  # noqa: T201
    server.serve_forever()


if __name__ == "__main__":
    main()
