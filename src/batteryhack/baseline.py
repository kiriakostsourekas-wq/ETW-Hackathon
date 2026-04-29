from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

from .forecasting import forecast_quality_metrics
from .optimizer import BatteryParams, optimize_battery_schedule
from .simulation import daterange, settle_schedule_on_actual_prices
from .synthetic import day_index


BASELINE_PRICE_COL = "baseline_forecast_price_eur_mwh"


@dataclass(frozen=True)
class BaselineForecast:
    frame: pd.DataFrame
    method: str
    source_dates: tuple[str, ...]


@dataclass(frozen=True)
class BaselineDispatch:
    forecast: BaselineForecast
    schedule: pd.DataFrame
    metrics: dict[str, float | str | bool | None]


def build_persistence_price_forecast(
    history: pd.DataFrame,
    target_date: date,
    fallback_days: int = 7,
) -> BaselineForecast:
    """Build a no-lookahead persistence price forecast for one delivery day.

    Normal case: copy the previous calendar day's 96 public DAM prices interval-by-interval.
    Fallback: if that previous day is unavailable or malformed, use the interval median over
    the last ``fallback_days`` valid public-price days before the target.
    """
    if fallback_days < 1:
        raise ValueError("fallback_days must be at least 1")

    prior = _prior_public_history(history, target_date)
    previous_day = target_date - timedelta(days=1)
    previous = _valid_day(prior, previous_day)
    target_index = day_index(target_date)

    if previous is not None:
        prices = previous.set_index("interval")["dam_price_eur_mwh"]
        output = target_index.copy()
        output[BASELINE_PRICE_COL] = output["interval"].map(prices).to_numpy(float)
        output["baseline_method"] = "previous_day_persistence"
        output["baseline_source_dates"] = previous_day.isoformat()
        return BaselineForecast(
            frame=output,
            method="previous_day_persistence",
            source_dates=(previous_day.isoformat(),),
        )

    fallback = _fallback_interval_median(prior, target_date, fallback_days)
    output = target_index.copy()
    output[BASELINE_PRICE_COL] = output["interval"].map(fallback["prices"]).to_numpy(float)
    output["baseline_method"] = "prior_7_day_interval_median"
    output["baseline_source_dates"] = ",".join(fallback["source_dates"])
    return BaselineForecast(
        frame=output,
        method="prior_7_day_interval_median",
        source_dates=tuple(fallback["source_dates"]),
    )


def run_persistence_self_schedule_baseline(
    history: pd.DataFrame,
    target_frame: pd.DataFrame,
    battery_params: BatteryParams,
) -> BaselineDispatch:
    target_date = _single_target_date(target_frame)
    forecast = build_persistence_price_forecast(history, target_date)
    forecast_frame = target_frame.drop(columns=[BASELINE_PRICE_COL], errors="ignore").merge(
        forecast.frame[["timestamp", "interval", BASELINE_PRICE_COL]],
        on=["timestamp", "interval"],
        how="left",
    )
    if forecast_frame[BASELINE_PRICE_COL].isna().any():
        raise ValueError(f"Baseline forecast is incomplete for {target_date}")

    optimized = optimize_battery_schedule(
        forecast_frame,
        battery_params,
        price_col=BASELINE_PRICE_COL,
    )
    realized = settle_schedule_on_actual_prices(optimized.schedule, target_frame, battery_params)
    quality = forecast_quality_metrics(
        target_frame["dam_price_eur_mwh"],
        forecast_frame[BASELINE_PRICE_COL],
    )

    oracle_net: float | None = None
    oracle_capture: float | None = None
    if "dam_price_eur_mwh" in target_frame and target_frame["dam_price_eur_mwh"].notna().all():
        oracle = optimize_battery_schedule(
            target_frame,
            battery_params,
            price_col="dam_price_eur_mwh",
        )
        oracle_net = oracle.metrics["net_revenue_eur"]
        oracle_capture = (
            realized["net_revenue_eur"] / oracle_net if abs(oracle_net) > 1e-9 else np.nan
        )

    metrics: dict[str, float | str | bool | None] = {
        "delivery_date": target_date.isoformat(),
        "baseline_method": forecast.method,
        "baseline_source_dates": ",".join(forecast.source_dates),
        "public_price_data": (
            str(target_frame["data_quality"].iloc[0]) == "public price data"
            if "data_quality" in target_frame
            else True
        ),
        "baseline_forecast_mae_eur_mwh": quality["mae_eur_mwh"],
        "baseline_forecast_rmse_eur_mwh": quality["rmse_eur_mwh"],
        "baseline_spread_direction_accuracy": quality["spread_direction_accuracy"],
        "baseline_objective_net_revenue_eur": optimized.metrics["net_revenue_eur"],
        "baseline_realized_net_revenue_eur": realized["net_revenue_eur"],
        "oracle_net_revenue_eur": oracle_net,
        "baseline_capture_ratio_vs_oracle": oracle_capture,
        "baseline_charged_mwh": realized["charged_mwh"],
        "baseline_discharged_mwh": realized["discharged_mwh"],
        "baseline_equivalent_cycles": realized["equivalent_cycles"],
        "baseline_captured_spread_eur_mwh": realized["captured_spread_eur_mwh"],
    }
    return BaselineDispatch(forecast=forecast, schedule=optimized.schedule, metrics=metrics)


def run_persistence_baseline_backtest(
    history: pd.DataFrame,
    start_date: date,
    end_date: date,
    battery_params: BatteryParams,
    drop_synthetic_targets: bool = True,
) -> pd.DataFrame:
    rows: list[dict[str, float | str | bool | None]] = []
    frame = history.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])

    for target_date in daterange(start_date, end_date):
        target = frame[frame["timestamp"].dt.date == target_date].copy().reset_index(drop=True)
        if target.empty:
            continue
        if (
            drop_synthetic_targets
            and "data_quality" in target
            and str(target["data_quality"].iloc[0]) != "public price data"
        ):
            continue
        rows.append(
            run_persistence_self_schedule_baseline(
                frame,
                target,
                battery_params,
            ).metrics
        )

    return pd.DataFrame(rows)


def _prior_public_history(history: pd.DataFrame, target_date: date) -> pd.DataFrame:
    if history.empty:
        raise ValueError("history is empty")
    required = {"timestamp", "interval", "dam_price_eur_mwh"}
    missing = required - set(history.columns)
    if missing:
        raise ValueError(f"history is missing required columns: {sorted(missing)}")

    frame = history.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    frame = frame[frame["timestamp"].dt.date < target_date].copy()
    if "data_quality" in frame:
        frame = frame[frame["data_quality"] == "public price data"].copy()
    return frame


def _valid_day(frame: pd.DataFrame, delivery_date: date) -> pd.DataFrame | None:
    day = frame[frame["timestamp"].dt.date == delivery_date].copy()
    if len(day) != 96:
        return None
    if day["interval"].nunique() != 96:
        return None
    if day["dam_price_eur_mwh"].isna().any():
        return None
    return day.sort_values("interval").reset_index(drop=True)


def _fallback_interval_median(
    prior: pd.DataFrame,
    target_date: date,
    fallback_days: int,
) -> dict[str, pd.Series | list[str]]:
    valid_days: list[pd.DataFrame] = []
    source_dates: list[str] = []
    candidate_dates = sorted(
        (day for day in prior["timestamp"].dt.date.unique() if day < target_date),
        reverse=True,
    )
    for candidate in candidate_dates:
        valid = _valid_day(prior, candidate)
        if valid is None:
            continue
        valid_days.append(valid)
        source_dates.append(candidate.isoformat())
        if len(valid_days) == fallback_days:
            break

    if not valid_days:
        raise ValueError(f"No valid public-price history before {target_date}")

    combined = pd.concat(valid_days, ignore_index=True)
    prices = combined.groupby("interval")["dam_price_eur_mwh"].median()
    if len(prices) != 96 or prices.isna().any():
        raise ValueError(f"Could not build complete fallback persistence forecast for {target_date}")
    return {"prices": prices, "source_dates": source_dates}


def _single_target_date(target_frame: pd.DataFrame) -> date:
    if target_frame.empty or "timestamp" not in target_frame:
        raise ValueError("target_frame must contain timestamp rows")
    dates = pd.to_datetime(target_frame["timestamp"]).dt.date.unique()
    if len(dates) != 1:
        raise ValueError("target_frame must contain exactly one delivery date")
    return dates[0]
