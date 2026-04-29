from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from math import isfinite
from typing import Any
from urllib.parse import parse_qs, urlparse

import numpy as np
import pandas as pd

from .config import DEFAULT_DEMO_DATE, MTU_HOURS
from .data_sources import load_market_bundle
from .optimizer import BatteryParams, optimize_battery_schedule
from .price_impact import PRICE_IMPACT_SCENARIOS, StorageImpactParams
from .production_forecast import build_storage_aware_forecast, registry_to_dict


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


def _impact_params_from_query(query: dict[str, list[str]]) -> StorageImpactParams:
    scenario_name = query.get("impact_scenario", ["Storage-aware medium impact"])[0]
    base = PRICE_IMPACT_SCENARIOS.get(scenario_name, PRICE_IMPACT_SCENARIOS["Storage-aware medium impact"])
    return StorageImpactParams(
        fleet_power_mw=_param_float(query, "fleet_power_mw", base.fleet_power_mw),
        fleet_energy_mwh=_param_float(query, "fleet_energy_mwh", base.fleet_energy_mwh),
        charge_price_elasticity_eur_mwh_per_gw=_param_float(
            query,
            "charge_price_elasticity_eur_mwh_per_gw",
            base.charge_price_elasticity_eur_mwh_per_gw,
        ),
        discharge_price_elasticity_eur_mwh_per_gw=_param_float(
            query,
            "discharge_price_elasticity_eur_mwh_per_gw",
            base.discharge_price_elasticity_eur_mwh_per_gw,
        ),
        spread_compression_factor=_param_float(
            query,
            "spread_compression_factor",
            base.spread_compression_factor,
        ),
        reference_power_mw=base.reference_power_mw,
        scenario_name=base.scenario_name,
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


def build_dashboard_payload(
    delivery_date: date,
    params: BatteryParams,
    include_forecast: bool = True,
    forecast_history_days: int = 21,
    validation_days: int = 3,
    impact_params: StorageImpactParams | None = None,
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
            production = build_storage_aware_forecast(
                target_date=delivery_date,
                battery_params=params,
                history_start=delivery_date - timedelta(days=forecast_history_days),
                validation_days=validation_days,
                impact_params=impact_params,
            )
            forecasting = _forecasting_payload(production)
            series = _merge_forecast_outputs(series, production)
            kpis = _forecast_kpis(production, series)
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
                "storage_adjusted_forecast_eur_mwh": _round(
                    getattr(row, "storage_adjusted_forecast_eur_mwh", None),
                    2,
                ),
                "storage_price_adjustment_eur_mwh": _round(
                    getattr(row, "storage_price_adjustment_eur_mwh", None),
                    2,
                ),
                "forecast_charge_mw": _round(getattr(row, "forecast_charge_mw", None), 4),
                "forecast_discharge_mw": _round(
                    getattr(row, "forecast_discharge_mw", None),
                    4,
                ),
                "storage_charge_mw": _round(getattr(row, "storage_charge_mw", None), 4),
                "storage_discharge_mw": _round(
                    getattr(row, "storage_discharge_mw", None),
                    4,
                ),
                "storage_soc_pct": _round(getattr(row, "storage_soc_pct", None), 2),
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
        "optimizer_status": output.status,
        "metrics": metrics,
        "forecasting": forecasting,
        "kpis": kpis,
        "windows": _action_windows(series[["time", "charge_mw", "discharge_mw"]]),
        "series": rows,
    }


def _merge_forecast_outputs(series: pd.DataFrame, production) -> pd.DataFrame:
    base = production.base_forecast_frame[
        [
            "timestamp",
            "forecast_price_eur_mwh",
            "forecast_low_eur_mwh",
            "forecast_high_eur_mwh",
        ]
    ].copy()
    adjusted = production.storage_adjusted_frame[
        [
            "timestamp",
            "storage_adjusted_forecast_eur_mwh",
            "storage_price_adjustment_eur_mwh",
        ]
    ].copy()
    base_schedule = production.base_schedule[
        ["timestamp", "charge_mw", "discharge_mw", "soc_pct_end"]
    ].rename(
        columns={
            "charge_mw": "forecast_charge_mw",
            "discharge_mw": "forecast_discharge_mw",
            "soc_pct_end": "forecast_soc_pct",
        }
    )
    storage_schedule = production.storage_schedule[
        ["timestamp", "charge_mw", "discharge_mw", "soc_pct_end"]
    ].rename(
        columns={
            "charge_mw": "storage_charge_mw",
            "discharge_mw": "storage_discharge_mw",
            "soc_pct_end": "storage_soc_pct",
        }
    )
    forecast_series = (
        base.merge(adjusted, on="timestamp", how="left")
        .merge(base_schedule, on="timestamp", how="left")
        .merge(storage_schedule, on="timestamp", how="left")
    )
    return series.merge(forecast_series, on="timestamp", how="left")


def _forecasting_payload(production) -> dict[str, Any]:
    return {
        "available": True,
        "registry": _json_safe(registry_to_dict(production.registry)),
        "metrics": _json_safe(production.metrics),
        "assumptions": _json_safe(production.assumptions),
        "model_performance": _records(production.model_performance),
        "daily_model_performance": _records(production.daily_model_performance),
    }


def _forecast_kpis(production, series: pd.DataFrame) -> list[dict[str, Any]]:
    metrics = production.metrics
    registry = production.registry
    return [
        {
            "label": "Forecast MAE",
            "value": f"EUR {metrics['base_forecast_mae_eur_mwh']:,.2f}/MWh",
            "badge": registry.selected_model,
            "detail": "Base forecast vs published DAM",
            "sparkline": _hourly_sparkline(series, "forecast_price_eur_mwh"),
        },
        {
            "label": "Storage-Aware Net",
            "value": f"EUR {metrics['storage_aware_objective_net_revenue_eur']:,.0f}",
            "badge": "Regime",
            "detail": "Objective after price feedback",
            "sparkline": _hourly_sparkline(series, "storage_price_adjustment_eur_mwh"),
        },
        {
            "label": "Spread Compression",
            "value": f"{metrics['impact_spread_compression_pct']:,.1f}%",
            "badge": "Scenario",
            "detail": f"{metrics['impact_average_spread_compression_eur_mwh']:,.1f} EUR/MWh",
            "sparkline": _hourly_sparkline(series, "storage_adjusted_forecast_eur_mwh"),
        },
        {
            "label": "Capture vs Oracle",
            "value": f"{(metrics['storage_aware_capture_ratio_vs_oracle'] or 0) * 100:,.1f}%",
            "badge": "Backtest",
            "detail": "Settled against published DAM",
            "sparkline": _hourly_sparkline(series, "storage_soc_pct"),
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
                    impact_params=_impact_params_from_query(query),
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
