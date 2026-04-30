from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .config import MTU_HOURS
from .optimizer import BatteryParams, optimize_battery_schedule

DEFAULT_PRICE_COL = "dam_price_eur_mwh"
ACTUAL_PRICE_COL = "actual_price_eur_mwh"
STRATEGY_COLUMNS = ("strategy", "model", "benchmark", "baseline_method")
HEADLINE_NOTICE = (
    "Strategic spread-compression stress test only; not a Greek price forecast."
)
SPREAD_COMPRESSION_RISK = "spread compression risk"
REDISPATCH_PARTIAL_OFFSET = "redispatch partially offsets compression"
REDISPATCH_IMPROVES_SAMPLE = "redispatch improves this sample day"
SEVERE_COMPRESSION_STRESS = "severe compression stress"


@dataclass(frozen=True)
class FutureBessScenario:
    name: str
    target_year: int
    installed_power_mw: float
    installed_energy_mwh: float
    spread_compression_pct: float
    responsive_fleet_share: float
    market_depth_mw_per_eur_mwh: float
    source_fields: tuple[str, ...]
    inference_fields: tuple[str, ...]
    low_price_quantile: float = 0.25
    high_price_quantile: float = 0.75
    max_fleet_shift_eur_mwh: float = 30.0

    @property
    def duration_hours(self) -> float:
        return self.installed_energy_mwh / self.installed_power_mw

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["duration_hours"] = self.duration_hours
        return data


@dataclass(frozen=True)
class FutureMarketImpactResult:
    interval_impacts: pd.DataFrame
    scenario_summary: pd.DataFrame
    scenarios: tuple[FutureBessScenario, ...]


CONSERVATIVE_SCENARIO = FutureBessScenario(
    name="conservative",
    target_year=2031,
    installed_power_mw=1230.0,
    installed_energy_mwh=4400.0,
    spread_compression_pct=0.12,
    responsive_fleet_share=0.25,
    market_depth_mw_per_eur_mwh=1200.0,
    max_fleet_shift_eur_mwh=8.0,
    source_fields=(
        "METLEN/Karatzis announced 330 MW / 790 MWh in Thessaly for Q2 2026.",
        "Greece awarded roughly 900 MW through three supported standalone BESS auctions.",
    ),
    inference_fields=(
        "Assumes awarded projects plus METLEN connect, with limited extra merchant buildout.",
        "Uses about 3.6 h average duration after combining auctioned projects and METLEN.",
    ),
)

BASE_SCENARIO = FutureBessScenario(
    name="base",
    target_year=2031,
    installed_power_mw=3000.0,
    installed_energy_mwh=9500.0,
    spread_compression_pct=0.28,
    responsive_fleet_share=0.35,
    market_depth_mw_per_eur_mwh=1000.0,
    max_fleet_shift_eur_mwh=18.0,
    source_fields=(
        "Greek standalone BESS priority-connection program targets 4.7 GW of merchant projects.",
        "METLEN reports BESS developments underway in Greece and other markets.",
    ),
    inference_fields=(
        "Assumes about half of the merchant priority-connection program reaches operation by 2031.",
        "Uses roughly 3.2 h average duration and medium solar/evening fleet coordination.",
    ),
)

AGGRESSIVE_SCENARIO = FutureBessScenario(
    name="aggressive",
    target_year=2031,
    installed_power_mw=5600.0,
    installed_energy_mwh=18000.0,
    spread_compression_pct=0.45,
    responsive_fleet_share=0.45,
    market_depth_mw_per_eur_mwh=900.0,
    max_fleet_shift_eur_mwh=32.0,
    source_fields=(
        "Greek policy pipeline combines the 4.7 GW merchant program with auctioned capacity.",
        "Spain and Italy evidence shows multi-GWh BESS procurement can scale quickly.",
    ),
    inference_fields=(
        "Assumes most Greek merchant and auctioned standalone BESS operates by 2031.",
        "Uses a Spain-style spread-compression warning case, not an observed Greek outcome.",
    ),
)

DEFAULT_FUTURE_BESS_SCENARIOS: tuple[FutureBessScenario, ...] = (
    CONSERVATIVE_SCENARIO,
    BASE_SCENARIO,
    AGGRESSIVE_SCENARIO,
)


def get_future_bess_scenarios(
    names: Iterable[str] | None = None,
) -> tuple[FutureBessScenario, ...]:
    scenarios = DEFAULT_FUTURE_BESS_SCENARIOS
    if names is None:
        return scenarios
    wanted = {name.strip().lower() for name in names}
    selected = tuple(scenario for scenario in scenarios if scenario.name in wanted)
    missing = wanted - {scenario.name for scenario in selected}
    if missing:
        raise ValueError(f"Unknown future BESS scenario(s): {', '.join(sorted(missing))}")
    return selected


def interpretation_label_for_future_impact(
    fixed_schedule_degradation_pct: float | None,
    reoptimized_degradation_pct: float | None = None,
    reoptimization_recovery_eur: float | None = None,
) -> str:
    """Return a conservative presentation label for a future scenario row."""
    fixed = _finite_or_none(fixed_schedule_degradation_pct)
    reoptimized = _finite_or_none(reoptimized_degradation_pct)
    recovery = _finite_or_none(reoptimization_recovery_eur)

    if (fixed is not None and fixed >= 60.0) or (
        reoptimized is not None and reoptimized >= 35.0
    ):
        return SEVERE_COMPRESSION_STRESS
    if reoptimized is not None and reoptimized <= -1.0:
        return REDISPATCH_IMPROVES_SAMPLE
    if (
        fixed is not None
        and reoptimized is not None
        and recovery is not None
        and recovery > 0.0
        and fixed - reoptimized >= 5.0
    ):
        return REDISPATCH_PARTIAL_OFFSET
    return SPREAD_COMPRESSION_RISK


def build_future_headline_artifact(
    scenario_summary: pd.DataFrame,
    input_path: str | Path | None = None,
    generated_at: str | None = None,
) -> dict[str, object]:
    """Build compact JSON-serializable headline rows for final presentation."""
    generated_at = generated_at or _utc_now_iso()
    rows = _future_headline_rows(scenario_summary)
    return {
        "generated_at": generated_at,
        "input_file": str(input_path) if input_path is not None else None,
        "preferred_input_file": "data/processed/strategy_comparison_intervals.csv",
        "fallback_input_files": [
            "data/processed/ml_research_predictions.csv",
            "data/processed/price_taker_forecast.csv",
        ],
        "notice": HEADLINE_NOTICE,
        "rows": rows,
    }


def write_future_headline_json(
    scenario_summary: pd.DataFrame,
    output_path: str | Path,
    input_path: str | Path | None = None,
    generated_at: str | None = None,
) -> dict[str, object]:
    """Write the compact headline artifact and return its contents."""
    artifact = build_future_headline_artifact(
        scenario_summary,
        input_path=input_path,
        generated_at=generated_at,
    )
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(artifact, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return artifact


def simulate_future_market_impact(
    market_or_backtest: pd.DataFrame,
    scenarios: Iterable[FutureBessScenario] | None = None,
    battery_params: BatteryParams | None = None,
    schedule: pd.DataFrame | None = None,
    price_col: str | None = DEFAULT_PRICE_COL,
    dt_hours: float = MTU_HOURS,
) -> FutureMarketImpactResult:
    scenario_tuple = tuple(scenarios or DEFAULT_FUTURE_BESS_SCENARIOS)
    for scenario in scenario_tuple:
        _validate_scenario(scenario)

    if _can_use_backtest_summary_proxy(market_or_backtest, price_col):
        return _simulate_backtest_summary_proxy(market_or_backtest, scenario_tuple)

    params = battery_params or BatteryParams(power_mw=330.0, capacity_mwh=790.0)
    market = _prepare_market(market_or_backtest, price_col)
    interval_frames: list[pd.DataFrame] = []
    summaries: list[dict[str, object]] = []

    group_columns = ["_input_strategy", "_delivery_date"]
    for (_input_strategy, _delivery_date), market_day in market.groupby(
        group_columns,
        sort=False,
    ):
        market_day = market_day.reset_index(drop=True)
        base_schedule = _base_schedule(market_day, params, schedule, DEFAULT_PRICE_COL, dt_hours)
        base_settlement = settle_schedule_on_prices(
            base_schedule,
            market_day[DEFAULT_PRICE_COL],
            params,
            dt_hours,
        )
        base_net_revenue = float(base_settlement.sum())

        for scenario in scenario_tuple:
            future_prices = apply_future_price_scenario(
                market_day,
                scenario,
                DEFAULT_PRICE_COL,
            )
            future_market = market_day.copy()
            future_market["future_price_eur_mwh"] = future_prices["future_price_eur_mwh"]
            future_output = optimize_battery_schedule(
                future_market,
                params,
                price_col="future_price_eur_mwh",
                dt_hours=dt_hours,
            )
            future_schedule = future_output.schedule
            fixed_future_settlement = settle_schedule_on_prices(
                base_schedule,
                future_prices["future_price_eur_mwh"],
                params,
                dt_hours,
            )
            reoptimized_settlement = settle_schedule_on_prices(
                future_schedule,
                future_prices["future_price_eur_mwh"],
                params,
                dt_hours,
            )

            intervals = _scenario_interval_frame(
                market=market_day,
                price_projection=future_prices,
                base_schedule=base_schedule,
                future_schedule=future_schedule,
                base_settlement=base_settlement,
                fixed_future_settlement=fixed_future_settlement,
                reoptimized_settlement=reoptimized_settlement,
                scenario=scenario,
                dt_hours=dt_hours,
            )
            interval_frames.append(intervals)
            summaries.append(
                _scenario_summary(
                    intervals,
                    scenario,
                    base_net_revenue,
                    float(fixed_future_settlement.sum()),
                    float(reoptimized_settlement.sum()),
                    base_schedule,
                    future_schedule,
                    dt_hours,
                    method="interval_price_reoptimized",
                )
            )

    return FutureMarketImpactResult(
        interval_impacts=(
            pd.concat(interval_frames, ignore_index=True)
            if interval_frames
            else pd.DataFrame()
        ),
        scenario_summary=pd.DataFrame(summaries),
        scenarios=scenario_tuple,
    )


def apply_future_price_scenario(
    market: pd.DataFrame,
    scenario: FutureBessScenario,
    price_col: str | None = DEFAULT_PRICE_COL,
) -> pd.DataFrame:
    _validate_scenario(scenario)
    prepared = _prepare_market(market, price_col)
    frames: list[pd.DataFrame] = []

    group_columns = ["_input_strategy", "_delivery_date"]
    for (input_strategy, delivery_date), day in prepared.groupby(group_columns, sort=False):
        prices = pd.to_numeric(day[DEFAULT_PRICE_COL], errors="coerce").to_numpy(dtype=float)
        median = float(np.median(prices))
        compressed = median + prices * (1.0 - scenario.spread_compression_pct) - (
            median * (1.0 - scenario.spread_compression_pct)
        )
        fleet_shift, mode = _fleet_response_shift(day, prices, scenario)
        future = compressed + fleet_shift
        projected = day[["timestamp", "interval"]].copy()
        projected["delivery_date"] = delivery_date
        projected["input_strategy"] = input_strategy
        projected["scenario"] = scenario.name
        projected["base_price_eur_mwh"] = prices
        projected["daily_median_price_eur_mwh"] = median
        projected["spread_compressed_price_eur_mwh"] = compressed
        projected["fleet_response_shift_eur_mwh"] = fleet_shift
        projected["future_price_eur_mwh"] = future
        projected["price_change_eur_mwh"] = future - prices
        projected["storage_response_mode"] = mode
        frames.append(projected)

    return pd.concat(frames, ignore_index=True)


def normalize_future_market_input(
    frame: pd.DataFrame,
    price_col: str | None = DEFAULT_PRICE_COL,
) -> pd.DataFrame:
    """Normalize ML/comparison interval outputs into simulator input columns.

    Accepted price columns include `dam_price_eur_mwh` and
    `actual_price_eur_mwh`. If a strategy column such as `strategy`, `model`,
    or `benchmark` exists, each value is simulated independently.
    """
    if frame.empty:
        raise ValueError("future market input is empty")

    resolved_price_col = _resolve_price_column(frame, price_col)
    output = frame.copy()

    if "timestamp" not in output.columns:
        if {"delivery_date", "interval"}.issubset(output.columns):
            output["timestamp"] = _timestamp_from_delivery_interval(output)
        else:
            raise ValueError("market is missing timestamp or delivery_date + interval")
    output["timestamp"] = pd.to_datetime(output["timestamp"]).dt.tz_localize(None)

    if "delivery_date" not in output.columns:
        output["delivery_date"] = output["timestamp"].dt.date.astype(str)
    else:
        output["delivery_date"] = output["delivery_date"].astype(str)

    if "interval" not in output.columns:
        output["interval"] = _interval_from_timestamp(output["timestamp"])
    output["interval"] = pd.to_numeric(output["interval"], errors="coerce").astype("Int64")
    if output["interval"].isna().any():
        raise ValueError("interval contains missing or non-numeric values")
    output["interval"] = output["interval"].astype(int)

    output[DEFAULT_PRICE_COL] = pd.to_numeric(output[resolved_price_col], errors="coerce")
    if output[DEFAULT_PRICE_COL].isna().any():
        raise ValueError(f"{resolved_price_col} contains missing or non-numeric values")

    if {"charge_mw", "discharge_mw"} & set(output.columns):
        for column in ("charge_mw", "discharge_mw"):
            if column not in output.columns:
                output[column] = 0.0
            output[column] = pd.to_numeric(output[column], errors="coerce").fillna(0.0)

    strategy_col = _strategy_column(output)
    output["_input_strategy"] = (
        output[strategy_col].fillna("input").astype(str) if strategy_col else "input"
    )
    output["_delivery_date"] = output["delivery_date"].astype(str)
    return output.sort_values(["_input_strategy", "timestamp", "interval"]).reset_index(drop=True)


def settle_schedule_on_prices(
    schedule: pd.DataFrame,
    prices: pd.Series | np.ndarray,
    params: BatteryParams,
    dt_hours: float = MTU_HOURS,
) -> pd.Series:
    required = {"charge_mw", "discharge_mw"}
    missing = required - set(schedule.columns)
    if missing:
        raise ValueError(f"schedule is missing required columns: {', '.join(sorted(missing))}")
    price_values = pd.to_numeric(pd.Series(prices), errors="coerce").to_numpy(dtype=float)
    charge = pd.to_numeric(schedule["charge_mw"], errors="coerce").fillna(0.0).to_numpy(float)
    discharge = pd.to_numeric(schedule["discharge_mw"], errors="coerce").fillna(0.0).to_numpy(float)
    if len(price_values) != len(schedule):
        raise ValueError("prices and schedule must have the same number of rows")
    gross = price_values * (discharge - charge) * dt_hours
    degradation = params.degradation_cost_eur_mwh * (charge + discharge) * dt_hours
    return pd.Series(gross - degradation, index=schedule.index, dtype=float)


def _scenario_interval_frame(
    market: pd.DataFrame,
    price_projection: pd.DataFrame,
    base_schedule: pd.DataFrame,
    future_schedule: pd.DataFrame,
    base_settlement: pd.Series,
    fixed_future_settlement: pd.Series,
    reoptimized_settlement: pd.Series,
    scenario: FutureBessScenario,
    dt_hours: float,
) -> pd.DataFrame:
    frame = price_projection.copy()
    frame["scenario_target_year"] = scenario.target_year
    frame["scenario_installed_power_mw"] = scenario.installed_power_mw
    frame["scenario_installed_energy_mwh"] = scenario.installed_energy_mwh
    frame["base_charge_mw"] = base_schedule["charge_mw"].to_numpy(float)
    frame["base_discharge_mw"] = base_schedule["discharge_mw"].to_numpy(float)
    frame["future_charge_mw"] = future_schedule["charge_mw"].to_numpy(float)
    frame["future_discharge_mw"] = future_schedule["discharge_mw"].to_numpy(float)
    frame["base_net_power_mw"] = frame["base_discharge_mw"] - frame["base_charge_mw"]
    frame["future_net_power_mw"] = frame["future_discharge_mw"] - frame["future_charge_mw"]
    frame["dispatch_change_mwh"] = (
        (frame["future_net_power_mw"] - frame["base_net_power_mw"]).abs() * dt_hours
    )
    frame["base_schedule_net_revenue_eur"] = base_settlement.to_numpy(float)
    frame["fixed_schedule_future_net_revenue_eur"] = fixed_future_settlement.to_numpy(float)
    frame["reoptimized_future_net_revenue_eur"] = reoptimized_settlement.to_numpy(float)
    if "load_forecast_mw" in market.columns:
        frame["scenario_power_pct_of_peak_load"] = (
            scenario.installed_power_mw
            / pd.to_numeric(market["load_forecast_mw"], errors="coerce").max()
            * 100.0
        )
    return frame


def _scenario_summary(
    intervals: pd.DataFrame,
    scenario: FutureBessScenario,
    base_net_revenue: float,
    fixed_future_net_revenue: float,
    reoptimized_future_net_revenue: float,
    base_schedule: pd.DataFrame,
    future_schedule: pd.DataFrame,
    dt_hours: float,
    method: str,
) -> dict[str, object]:
    delivery_date = str(intervals["delivery_date"].iloc[0]) if "delivery_date" in intervals else ""
    input_strategy = (
        str(intervals["input_strategy"].iloc[0]) if "input_strategy" in intervals else "input"
    )
    base_spread = _price_spread(intervals["base_price_eur_mwh"])
    future_spread = _price_spread(intervals["future_price_eur_mwh"])
    fixed_degradation = _degradation_pct(base_net_revenue, fixed_future_net_revenue)
    reoptimized_degradation = _degradation_pct(base_net_revenue, reoptimized_future_net_revenue)
    summary: dict[str, object] = {
        "delivery_date": delivery_date,
        "input_strategy": input_strategy,
        "scenario": scenario.name,
        "target_year": scenario.target_year,
        "method": method,
        "installed_power_mw": scenario.installed_power_mw,
        "installed_energy_mwh": scenario.installed_energy_mwh,
        "duration_hours": scenario.duration_hours,
        "source_fields": " | ".join(scenario.source_fields),
        "inference_fields": " | ".join(scenario.inference_fields),
        "assumed_spread_compression_pct": scenario.spread_compression_pct * 100.0,
        "modelled_spread_compression_pct": _degradation_pct(base_spread, future_spread),
        "responsive_fleet_share": scenario.responsive_fleet_share,
        "market_depth_mw_per_eur_mwh": scenario.market_depth_mw_per_eur_mwh,
        "base_daily_spread_eur_mwh": base_spread,
        "future_daily_spread_eur_mwh": future_spread,
        "avg_price_change_eur_mwh": float(intervals["price_change_eur_mwh"].mean()),
        "avg_abs_price_change_eur_mwh": float(intervals["price_change_eur_mwh"].abs().mean()),
        "base_schedule_net_revenue_eur": base_net_revenue,
        "fixed_schedule_future_net_revenue_eur": fixed_future_net_revenue,
        "reoptimized_future_net_revenue_eur": reoptimized_future_net_revenue,
        "fixed_schedule_pnl_degradation_pct": fixed_degradation,
        "reoptimized_pnl_degradation_pct": reoptimized_degradation,
        "reoptimization_recovery_eur": reoptimized_future_net_revenue - fixed_future_net_revenue,
        "total_dispatch_change_mwh": float(intervals["dispatch_change_mwh"].sum()),
        "base_charged_mwh": _schedule_mwh(base_schedule, "charge_mw", dt_hours),
        "base_discharged_mwh": _schedule_mwh(base_schedule, "discharge_mw", dt_hours),
        "future_charged_mwh": _schedule_mwh(future_schedule, "charge_mw", dt_hours),
        "future_discharged_mwh": _schedule_mwh(future_schedule, "discharge_mw", dt_hours),
    }
    return summary


def _fleet_response_shift(
    day: pd.DataFrame,
    prices: np.ndarray,
    scenario: FutureBessScenario,
) -> tuple[np.ndarray, np.ndarray]:
    low_cut = float(np.quantile(prices, scenario.low_price_quantile))
    high_cut = float(np.quantile(prices, scenario.high_price_quantile))
    min_price = float(np.min(prices))
    max_price = float(np.max(prices))
    low_denominator = max(low_cut - min_price, 1e-9)
    high_denominator = max(max_price - high_cut, 1e-9)

    charge_intensity = np.where(
        prices <= low_cut,
        np.clip((low_cut - prices) / low_denominator, 0.0, 1.0),
        0.0,
    )
    discharge_intensity = np.where(
        prices >= high_cut,
        np.clip((prices - high_cut) / high_denominator, 0.0, 1.0),
        0.0,
    )
    depth = _depth_values(day, scenario)
    raw_shift = scenario.installed_power_mw * scenario.responsive_fleet_share / depth
    charge_shift = np.clip(raw_shift * charge_intensity, 0.0, scenario.max_fleet_shift_eur_mwh)
    discharge_shift = np.clip(
        raw_shift * discharge_intensity,
        0.0,
        scenario.max_fleet_shift_eur_mwh,
    )
    shift = charge_shift - discharge_shift
    mode = np.select(
        [charge_shift > 1e-9, discharge_shift > 1e-9],
        ["fleet_charging", "fleet_discharging"],
        default="neutral",
    )
    return shift.astype(float), mode


def _depth_values(day: pd.DataFrame, scenario: FutureBessScenario) -> np.ndarray:
    if "market_depth_mw_per_eur_mwh" in day.columns:
        values = pd.to_numeric(day["market_depth_mw_per_eur_mwh"], errors="coerce")
        values = values.where(values > 1e-9, np.nan).fillna(scenario.market_depth_mw_per_eur_mwh)
        return values.to_numpy(float)
    return np.full(len(day), scenario.market_depth_mw_per_eur_mwh, dtype=float)


def _base_schedule(
    market: pd.DataFrame,
    params: BatteryParams,
    schedule: pd.DataFrame | None,
    price_col: str,
    dt_hours: float,
) -> pd.DataFrame:
    if schedule is not None:
        return _align_schedule(market, schedule)
    if {"charge_mw", "discharge_mw"}.issubset(market.columns):
        return _align_schedule(market, market)
    return optimize_battery_schedule(
        market,
        params,
        price_col=price_col,
        dt_hours=dt_hours,
    ).schedule


def _align_schedule(market: pd.DataFrame, schedule: pd.DataFrame) -> pd.DataFrame:
    required = {"charge_mw", "discharge_mw"}
    missing = required - set(schedule.columns)
    if missing:
        raise ValueError(f"schedule is missing required columns: {', '.join(sorted(missing))}")
    strategy_col = _strategy_column(schedule)
    if strategy_col and "_input_strategy" in market.columns and not market.empty:
        input_strategy = str(market["_input_strategy"].iloc[0])
        schedule = schedule[schedule[strategy_col].fillna("input").astype(str) == input_strategy]
    if "timestamp" in schedule.columns and "timestamp" in market.columns:
        aligned = market[["timestamp", "interval"]].merge(
            schedule[["timestamp", "charge_mw", "discharge_mw"]],
            on="timestamp",
            how="left",
        )
    elif len(schedule) == len(market):
        aligned = market[["timestamp", "interval"]].copy()
        aligned["charge_mw"] = schedule["charge_mw"].to_numpy()
        aligned["discharge_mw"] = schedule["discharge_mw"].to_numpy()
    else:
        raise ValueError("schedule must align by timestamp or have the same row count as market")
    aligned[["charge_mw", "discharge_mw"]] = aligned[["charge_mw", "discharge_mw"]].fillna(0.0)
    aligned["net_power_mw"] = aligned["discharge_mw"] - aligned["charge_mw"]
    return aligned


def _prepare_market(market: pd.DataFrame, price_col: str | None) -> pd.DataFrame:
    prepared = normalize_future_market_input(market, price_col)
    required = {"timestamp", "interval", DEFAULT_PRICE_COL}
    missing = required - set(prepared.columns)
    if missing:
        raise ValueError(f"market is missing required columns: {', '.join(sorted(missing))}")
    return prepared.reset_index(drop=True)


def _simulate_backtest_summary_proxy(
    backtest: pd.DataFrame,
    scenarios: tuple[FutureBessScenario, ...],
) -> FutureMarketImpactResult:
    rows: list[dict[str, object]] = []
    for record in backtest.to_dict(orient="records"):
        base_revenue = float(record.get("net_revenue_eur", 0.0) or 0.0)
        base_spread = float(record.get("captured_spread_eur_mwh", 0.0) or 0.0)
        delivery_date = record.get("delivery_date", "unknown")
        input_strategy = _record_strategy(record)
        for scenario in scenarios:
            future_spread = base_spread * (1.0 - scenario.spread_compression_pct)
            future_revenue = base_revenue * (
                future_spread / base_spread if abs(base_spread) > 1e-9 else 0.0
            )
            rows.append(
                {
                    "delivery_date": delivery_date,
                    "input_strategy": input_strategy,
                    "scenario": scenario.name,
                    "target_year": scenario.target_year,
                    "method": "backtest_summary_proxy",
                    "installed_power_mw": scenario.installed_power_mw,
                    "installed_energy_mwh": scenario.installed_energy_mwh,
                    "duration_hours": scenario.duration_hours,
                    "source_fields": " | ".join(scenario.source_fields),
                    "inference_fields": " | ".join(scenario.inference_fields),
                    "base_captured_spread_eur_mwh": base_spread,
                    "future_captured_spread_eur_mwh": future_spread,
                    "base_schedule_net_revenue_eur": base_revenue,
                    "fixed_schedule_future_net_revenue_eur": future_revenue,
                    "reoptimized_future_net_revenue_eur": np.nan,
                    "fixed_schedule_pnl_degradation_pct": _degradation_pct(
                        base_revenue,
                        future_revenue,
                    ),
                    "reoptimized_pnl_degradation_pct": np.nan,
                    "limitation": (
                        "Backtest summary proxy cannot estimate interval dispatch changes; "
                        "use interval prices for re-optimization."
                    ),
                }
            )
    return FutureMarketImpactResult(
        interval_impacts=pd.DataFrame(),
        scenario_summary=pd.DataFrame(rows),
        scenarios=scenarios,
    )


def _looks_like_backtest_summary(frame: pd.DataFrame) -> bool:
    return {"net_revenue_eur", "captured_spread_eur_mwh"}.issubset(frame.columns)


def _can_use_backtest_summary_proxy(
    frame: pd.DataFrame,
    price_col: str | None,
) -> bool:
    if not _looks_like_backtest_summary(frame):
        return False
    try:
        _resolve_price_column(frame, price_col)
    except ValueError:
        return True
    return False


def _resolve_price_column(frame: pd.DataFrame, price_col: str | None) -> str:
    if price_col and price_col != "auto":
        if price_col in frame.columns:
            return price_col
        if price_col != DEFAULT_PRICE_COL:
            raise ValueError(f"market is missing requested price column: {price_col}")

    for candidate in (
        DEFAULT_PRICE_COL,
        ACTUAL_PRICE_COL,
        "realized_price_eur_mwh",
        "price_eur_mwh",
    ):
        if candidate in frame.columns:
            return candidate
    raise ValueError(
        "market is missing a price column; expected dam_price_eur_mwh "
        "or actual_price_eur_mwh"
    )


def _strategy_column(frame: pd.DataFrame) -> str | None:
    for column in STRATEGY_COLUMNS:
        if column in frame.columns:
            return column
    return None


def _record_strategy(record: dict[str, object]) -> str:
    for column in STRATEGY_COLUMNS:
        value = record.get(column)
        if value is not None and not pd.isna(value):
            return str(value)
    return "summary"


def _future_headline_rows(scenario_summary: pd.DataFrame) -> list[dict[str, object]]:
    if scenario_summary.empty:
        return []
    required = {"input_strategy", "scenario"}
    missing = required - set(scenario_summary.columns)
    if missing:
        raise ValueError(
            "scenario_summary is missing required headline columns: "
            f"{', '.join(sorted(missing))}"
        )

    rows: list[dict[str, object]] = []
    for (strategy, scenario), group in scenario_summary.groupby(
        ["input_strategy", "scenario"],
        sort=True,
        dropna=False,
    ):
        fixed_degradation = _headline_degradation(
            group,
            future_revenue_col="fixed_schedule_future_net_revenue_eur",
            fallback_pct_col="fixed_schedule_pnl_degradation_pct",
        )
        reoptimized_degradation = _headline_degradation(
            group,
            future_revenue_col="reoptimized_future_net_revenue_eur",
            fallback_pct_col="reoptimized_pnl_degradation_pct",
        )
        recovery = _headline_recovery(group)
        rows.append(
            {
                "strategy_model": str(strategy),
                "scenario": str(scenario),
                "fixed_schedule_degradation_pct": _json_metric(fixed_degradation),
                "reoptimized_degradation_pct": _json_metric(reoptimized_degradation),
                "reoptimization_recovery_eur": _json_metric(recovery),
                "interpretation_label": interpretation_label_for_future_impact(
                    fixed_degradation,
                    reoptimized_degradation,
                    recovery,
                ),
                "sample_days": _sample_days(group),
            }
        )
    return rows


def _headline_degradation(
    group: pd.DataFrame,
    *,
    future_revenue_col: str,
    fallback_pct_col: str,
) -> float | None:
    if {"base_schedule_net_revenue_eur", future_revenue_col}.issubset(group.columns):
        base = _sum_finite(group["base_schedule_net_revenue_eur"])
        future = _sum_finite(group[future_revenue_col])
        if base is not None and future is not None:
            return _degradation_pct(base, future)
    if fallback_pct_col in group.columns:
        return _mean_finite(group[fallback_pct_col])
    return None


def _headline_recovery(group: pd.DataFrame) -> float | None:
    required = {
        "fixed_schedule_future_net_revenue_eur",
        "reoptimized_future_net_revenue_eur",
    }
    if required.issubset(group.columns):
        fixed = _sum_finite(group["fixed_schedule_future_net_revenue_eur"])
        reoptimized = _sum_finite(group["reoptimized_future_net_revenue_eur"])
        if fixed is not None and reoptimized is not None:
            return float(reoptimized - fixed)
    if "reoptimization_recovery_eur" in group.columns:
        return _sum_finite(group["reoptimization_recovery_eur"])
    return None


def _sample_days(group: pd.DataFrame) -> int:
    if "delivery_date" not in group.columns:
        return int(len(group))
    return int(group["delivery_date"].astype(str).nunique())


def _sum_finite(values: pd.Series) -> float | None:
    numeric = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if numeric.empty:
        return None
    return float(numeric.sum())


def _mean_finite(values: pd.Series) -> float | None:
    numeric = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if numeric.empty:
        return None
    return float(numeric.mean())


def _finite_or_none(value: float | None) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(numeric):
        return None
    return numeric


def _json_metric(value: float | None) -> float | None:
    numeric = _finite_or_none(value)
    return round(numeric, 6) if numeric is not None else None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _timestamp_from_delivery_interval(frame: pd.DataFrame) -> pd.Series:
    delivery_dates = pd.to_datetime(frame["delivery_date"])
    intervals = pd.to_numeric(frame["interval"], errors="coerce")
    if intervals.isna().any():
        raise ValueError("interval contains missing or non-numeric values")
    return delivery_dates + pd.to_timedelta((intervals.astype(int) - 1) * MTU_HOURS, unit="h")


def _interval_from_timestamp(timestamps: pd.Series) -> pd.Series:
    return timestamps.dt.hour * 4 + (timestamps.dt.minute // 15) + 1


def _validate_scenario(scenario: FutureBessScenario) -> None:
    if scenario.installed_power_mw <= 0 or scenario.installed_energy_mwh <= 0:
        raise ValueError("scenario installed power and energy must be positive")
    if not 0.0 <= scenario.spread_compression_pct < 1.0:
        raise ValueError("spread_compression_pct must be in [0, 1)")
    if not 0.0 <= scenario.responsive_fleet_share <= 1.0:
        raise ValueError("responsive_fleet_share must be in [0, 1]")
    if scenario.market_depth_mw_per_eur_mwh <= 0:
        raise ValueError("market_depth_mw_per_eur_mwh must be positive")
    if not 0.0 < scenario.low_price_quantile < scenario.high_price_quantile < 1.0:
        raise ValueError("price quantiles must satisfy 0 < low < high < 1")
    if scenario.max_fleet_shift_eur_mwh < 0:
        raise ValueError("max_fleet_shift_eur_mwh must be non-negative")


def _schedule_mwh(schedule: pd.DataFrame, column: str, dt_hours: float) -> float:
    return float(pd.to_numeric(schedule[column], errors="coerce").fillna(0.0).sum() * dt_hours)


def _price_spread(values: pd.Series) -> float:
    prices = pd.to_numeric(values, errors="coerce").dropna()
    if prices.empty:
        return 0.0
    return float(prices.max() - prices.min())


def _degradation_pct(base: float, future: float) -> float:
    if abs(base) <= 1e-9:
        return 0.0
    return float((base - future) / abs(base) * 100.0)
