from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

import numpy as np
import pandas as pd

from .config import MTU_HOURS
from .data_sources import load_market_bundle
from .forecasting import (
    ForecastingError,
    forecast_price_with_model,
    forecast_quality_metrics,
    minimum_training_rows_for_model,
)
from .optimizer import BatteryParams, optimize_battery_schedule


DEFAULT_MODEL_CANDIDATES = (
    "structural_proxy",
    "interval_profile",
    "ridge",
    "hist_gradient_boosting",
)
DEFAULT_ML_MODEL_CANDIDATES = ("ridge", "hist_gradient_boosting")


@dataclass(frozen=True)
class MarketHistory:
    frame: pd.DataFrame
    source_summary: dict[str, int]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class SmokeSimulationResult:
    model_performance: pd.DataFrame
    daily_model_performance: pd.DataFrame
    dispatch: pd.DataFrame
    selected_model: str
    source_summary: dict[str, int]


def daterange(start_date: date, end_date: date) -> Iterable[date]:
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def load_market_history(
    start_date: date,
    end_date: date,
    allow_synthetic: bool = True,
) -> MarketHistory:
    frames: list[pd.DataFrame] = []
    warnings: list[str] = []
    public_price_days = 0
    synthetic_price_days = 0

    for delivery_date in daterange(start_date, end_date):
        bundle = load_market_bundle(delivery_date, allow_synthetic=allow_synthetic)
        frame = bundle.frame.copy()
        frame["delivery_date"] = delivery_date
        frames.append(frame)
        warnings.extend(f"{delivery_date}: {warning}" for warning in bundle.warnings)
        if frame["data_quality"].iloc[0] == "public price data":
            public_price_days += 1
        else:
            synthetic_price_days += 1

    history = pd.concat(frames, ignore_index=True).sort_values("timestamp").reset_index(drop=True)
    return MarketHistory(
        frame=history,
        source_summary={
            "days": len(frames),
            "public_price_days": public_price_days,
            "synthetic_price_days": synthetic_price_days,
            "warnings": len(warnings),
        },
        warnings=tuple(warnings),
    )


def compare_forecast_models_walk_forward(
    frame: pd.DataFrame,
    validation_start: date,
    validation_end: date,
    model_candidates: tuple[str, ...] = DEFAULT_MODEL_CANDIDATES,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    predictions: dict[str, list[pd.DataFrame]] = {model: [] for model in model_candidates}
    daily_rows: list[dict[str, float | str]] = []

    for delivery_date in daterange(validation_start, validation_end):
        train = _training_frame(frame, delivery_date)
        target = _target_frame(frame, delivery_date)
        if target.empty:
            continue

        for model_name in model_candidates:
            if not _is_trainable(model_name, train):
                continue
            try:
                forecast = forecast_price_with_model(train, target, model_name).frame
            except ForecastingError:
                continue
            metrics = forecast_quality_metrics(
                target["dam_price_eur_mwh"],
                forecast["forecast_price_eur_mwh"],
            )
            daily_rows.append(
                {
                    "delivery_date": delivery_date.isoformat(),
                    "model": model_name,
                    "training_rows": len(train.dropna(subset=["dam_price_eur_mwh"])),
                    **metrics,
                }
            )
            predictions[model_name].append(
                pd.DataFrame(
                    {
                        "actual": target["dam_price_eur_mwh"].to_numpy(float),
                        "predicted": forecast["forecast_price_eur_mwh"].to_numpy(float),
                    }
                )
            )

    performance_rows: list[dict[str, float | str]] = []
    for model_name, parts in predictions.items():
        if not parts:
            continue
        combined = pd.concat(parts, ignore_index=True)
        metrics = forecast_quality_metrics(combined["actual"], combined["predicted"])
        performance_rows.append(
            {
                "model": model_name,
                "days_evaluated": len(parts),
                **metrics,
            }
        )

    performance = pd.DataFrame(performance_rows)
    if not performance.empty:
        performance = performance.sort_values(["mae_eur_mwh", "rmse_eur_mwh"]).reset_index(drop=True)
    return performance, pd.DataFrame(daily_rows)


def select_best_model(
    model_performance: pd.DataFrame,
    preferred_models: tuple[str, ...] = DEFAULT_ML_MODEL_CANDIDATES,
    metric: str = "mae_eur_mwh",
) -> str:
    if model_performance.empty:
        raise ValueError("No model performance rows are available for selection")

    preferred = model_performance[model_performance["model"].isin(preferred_models)]
    candidates = preferred if not preferred.empty else model_performance
    ordered = candidates.sort_values([metric, "rmse_eur_mwh"]).reset_index(drop=True)
    return str(ordered.loc[0, "model"])


def run_dispatch_smoke_test(
    frame: pd.DataFrame,
    smoke_start: date,
    smoke_end: date,
    params: BatteryParams,
    selected_model: str,
) -> pd.DataFrame:
    rows: list[dict[str, float | str | bool]] = []
    for delivery_date in daterange(smoke_start, smoke_end):
        train = _training_frame(frame, delivery_date)
        target = _target_frame(frame, delivery_date)
        if target.empty:
            continue

        forecast = forecast_price_with_model(train, target, selected_model).frame
        forecast_metrics = forecast_quality_metrics(
            target["dam_price_eur_mwh"],
            forecast["forecast_price_eur_mwh"],
        )
        scheduled = optimize_battery_schedule(forecast, params, price_col="forecast_price_eur_mwh")
        realized_metrics = settle_schedule_on_actual_prices(scheduled.schedule, target, params)
        oracle = optimize_battery_schedule(target, params, price_col="dam_price_eur_mwh")
        oracle_net = oracle.metrics["net_revenue_eur"]
        capture_ratio = (
            realized_metrics["net_revenue_eur"] / oracle_net if abs(oracle_net) > 1e-9 else np.nan
        )

        rows.append(
            {
                "delivery_date": delivery_date.isoformat(),
                "model": selected_model,
                "training_days": _training_days(train),
                "public_price_data": target["data_quality"].iloc[0] == "public price data",
                "forecast_mae_eur_mwh": forecast_metrics["mae_eur_mwh"],
                "forecast_rmse_eur_mwh": forecast_metrics["rmse_eur_mwh"],
                "forecast_spread_direction_accuracy": forecast_metrics[
                    "spread_direction_accuracy"
                ],
                "forecast_objective_net_revenue_eur": scheduled.metrics["net_revenue_eur"],
                "realized_net_revenue_eur": realized_metrics["net_revenue_eur"],
                "oracle_net_revenue_eur": oracle_net,
                "capture_ratio_vs_oracle": capture_ratio,
                "realized_charged_mwh": realized_metrics["charged_mwh"],
                "realized_discharged_mwh": realized_metrics["discharged_mwh"],
                "realized_equivalent_cycles": realized_metrics["equivalent_cycles"],
                "realized_captured_spread_eur_mwh": realized_metrics[
                    "captured_spread_eur_mwh"
                ],
            }
        )
    return pd.DataFrame(rows)


def run_trained_march_smoke_simulation(
    frame: pd.DataFrame,
    validation_start: date,
    validation_end: date,
    smoke_start: date,
    smoke_end: date,
    params: BatteryParams,
    model_candidates: tuple[str, ...] = DEFAULT_MODEL_CANDIDATES,
) -> SmokeSimulationResult:
    model_performance, daily_model_performance = compare_forecast_models_walk_forward(
        frame,
        validation_start,
        validation_end,
        model_candidates=model_candidates,
    )
    selected_model = select_best_model(model_performance)
    dispatch = run_dispatch_smoke_test(
        frame,
        smoke_start,
        smoke_end,
        params,
        selected_model,
    )
    return SmokeSimulationResult(
        model_performance=model_performance,
        daily_model_performance=daily_model_performance,
        dispatch=dispatch,
        selected_model=selected_model,
        source_summary=_source_summary_from_frame(frame),
    )


def settle_schedule_on_actual_prices(
    schedule: pd.DataFrame,
    market: pd.DataFrame,
    params: BatteryParams,
    dt_hours: float = MTU_HOURS,
) -> dict[str, float]:
    aligned = schedule[["timestamp", "charge_mw", "discharge_mw"]].merge(
        market[["timestamp", "dam_price_eur_mwh"]],
        on="timestamp",
        how="left",
    )
    prices = pd.to_numeric(aligned["dam_price_eur_mwh"], errors="coerce").to_numpy(float)
    charge = aligned["charge_mw"].to_numpy(float)
    discharge = aligned["discharge_mw"].to_numpy(float)
    charged_mwh = float(charge.sum() * dt_hours)
    discharged_mwh = float(discharge.sum() * dt_hours)
    throughput_mwh = float((charge + discharge).sum() * dt_hours)
    gross_revenue = float((prices * (discharge - charge) * dt_hours).sum())
    degradation_cost = float(params.degradation_cost_eur_mwh * throughput_mwh)
    avg_charge_price = (
        float((prices * charge * dt_hours).sum() / charged_mwh) if charged_mwh > 1e-9 else 0.0
    )
    avg_discharge_price = (
        float((prices * discharge * dt_hours).sum() / discharged_mwh)
        if discharged_mwh > 1e-9
        else 0.0
    )
    return {
        "gross_revenue_eur": gross_revenue,
        "degradation_cost_eur": degradation_cost,
        "net_revenue_eur": gross_revenue - degradation_cost,
        "charged_mwh": charged_mwh,
        "discharged_mwh": discharged_mwh,
        "equivalent_cycles": discharged_mwh / params.capacity_mwh,
        "avg_charge_price_eur_mwh": avg_charge_price,
        "avg_discharge_price_eur_mwh": avg_discharge_price,
        "captured_spread_eur_mwh": avg_discharge_price - avg_charge_price,
    }


def _is_trainable(model_name: str, train: pd.DataFrame) -> bool:
    priced_rows = len(train.dropna(subset=["dam_price_eur_mwh"]))
    return priced_rows >= minimum_training_rows_for_model(model_name)


def _target_frame(frame: pd.DataFrame, delivery_date: date) -> pd.DataFrame:
    return (
        frame[frame["timestamp"].dt.date == delivery_date]
        .drop(columns=["delivery_date"], errors="ignore")
        .reset_index(drop=True)
    )


def _training_frame(frame: pd.DataFrame, delivery_date: date) -> pd.DataFrame:
    return (
        frame[frame["timestamp"].dt.date < delivery_date]
        .drop(columns=["delivery_date"], errors="ignore")
        .reset_index(drop=True)
    )


def _training_days(train: pd.DataFrame) -> int:
    if train.empty:
        return 0
    return int(train["timestamp"].dt.date.nunique())


def _source_summary_from_frame(frame: pd.DataFrame) -> dict[str, int]:
    by_day = frame.groupby(frame["timestamp"].dt.date)["data_quality"].first()
    return {
        "days": int(len(by_day)),
        "public_price_days": int((by_day == "public price data").sum()),
        "synthetic_price_days": int((by_day != "public price data").sum()),
    }
