from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from .forecasting import (
    ForecastingError,
    candidate_feature_columns,
    forecast_price_with_model,
    forecast_price_with_uncertainty,
    forecast_quality_metrics,
    minimum_training_rows_for_model,
)
from .optimizer import BatteryParams, optimize_battery_schedule
from .price_impact import (
    PRICE_IMPACT_SCENARIOS,
    StorageImpactParams,
    adjust_prices_for_storage_feedback,
)
from .simulation import (
    DEFAULT_MODEL_CANDIDATES,
    compare_forecast_models_walk_forward,
    load_market_history,
    select_best_model,
    settle_schedule_on_actual_prices,
)


@dataclass(frozen=True)
class ForecastModelRegistry:
    selected_model: str
    target_date: str
    training_start: str | None
    training_end: str | None
    validation_start: str | None
    validation_end: str | None
    training_rows: int
    feature_columns: tuple[str, ...]
    candidate_models: tuple[str, ...]
    selected_metrics: dict[str, float | str | None]
    leakage_audit: dict[str, Any]
    source_summary: dict[str, int]


@dataclass(frozen=True)
class StorageAwareForecast:
    registry: ForecastModelRegistry
    feature_table: pd.DataFrame
    target_frame: pd.DataFrame
    base_forecast_frame: pd.DataFrame
    base_schedule: pd.DataFrame
    storage_adjusted_frame: pd.DataFrame
    storage_schedule: pd.DataFrame
    model_performance: pd.DataFrame
    daily_model_performance: pd.DataFrame
    metrics: dict[str, float | str | None]
    assumptions: dict[str, Any]


def build_forecast_feature_table(
    start_date: date,
    end_date: date,
    allow_synthetic: bool = True,
) -> tuple[pd.DataFrame, dict[str, int], tuple[str, ...]]:
    """Build the live-safe forecasting table from public market/system/weather inputs."""
    history = load_market_history(start_date, end_date, allow_synthetic=allow_synthetic)
    frame = history.frame.copy().sort_values("timestamp").reset_index(drop=True)
    return frame, history.source_summary, history.warnings


def build_storage_aware_forecast(
    target_date: date,
    battery_params: BatteryParams,
    history_start: date | None = None,
    validation_days: int = 3,
    model_candidates: tuple[str, ...] = DEFAULT_MODEL_CANDIDATES,
    impact_params: StorageImpactParams | None = None,
    allow_synthetic: bool = True,
) -> StorageAwareForecast:
    if history_start is None:
        history_start = target_date - timedelta(days=21)
    if impact_params is None:
        impact_params = PRICE_IMPACT_SCENARIOS["Storage-aware medium impact"]

    feature_table, source_summary, warnings = build_forecast_feature_table(
        history_start,
        target_date,
        allow_synthetic=allow_synthetic,
    )
    feature_table["timestamp"] = pd.to_datetime(feature_table["timestamp"])
    target_frame = _target_frame(feature_table, target_date)
    train_frame = _training_frame(feature_table, target_date)
    if target_frame.empty:
        raise ForecastingError(f"No target rows available for {target_date}")

    model_performance, daily_performance = _selectable_model_performance(
        feature_table,
        target_date,
        validation_days,
        model_candidates,
    )
    selected_model = _select_model_for_target(model_performance, train_frame, model_candidates)
    forecast = _forecast_for_target(train_frame, target_frame, selected_model)
    registry = _build_registry(
        selected_model=selected_model,
        target_date=target_date,
        train_frame=train_frame,
        target_frame=target_frame,
        validation_days=validation_days,
        model_candidates=model_candidates,
        model_performance=model_performance,
        source_summary=source_summary,
        warnings=warnings,
        feature_columns=forecast.feature_columns,
    )

    base_forecast_frame = forecast.frame.copy()
    base_schedule = optimize_battery_schedule(
        base_forecast_frame,
        battery_params,
        price_col="forecast_price_eur_mwh",
    ).schedule
    impact = adjust_prices_for_storage_feedback(
        base_forecast_frame,
        base_schedule,
        impact_params,
        price_col="forecast_price_eur_mwh",
        output_col="storage_adjusted_forecast_eur_mwh",
    )
    storage_schedule_output = optimize_battery_schedule(
        impact.frame,
        battery_params,
        price_col="storage_adjusted_forecast_eur_mwh",
    )

    metrics = _storage_forecast_metrics(
        target_frame=target_frame,
        base_forecast_frame=base_forecast_frame,
        base_schedule=base_schedule,
        storage_adjusted_frame=impact.frame,
        storage_schedule=storage_schedule_output.schedule,
        battery_params=battery_params,
        impact_metrics=impact.metrics,
    )
    assumptions = {
        "target": "15-minute HEnEx Day-Ahead Market MCP",
        "history_start": history_start.isoformat(),
        "history_end": target_date.isoformat(),
        "validation_days": validation_days,
        "model_candidates": list(model_candidates),
        "impact_scenario": impact_params.scenario_name,
        "storage_impact": asdict(impact_params),
        "battery": asdict(battery_params),
        "storage_impact_status": (
            "scenario-based until HEnEx aggregated curve elasticity is calibrated"
        ),
    }

    return StorageAwareForecast(
        registry=registry,
        feature_table=feature_table,
        target_frame=target_frame,
        base_forecast_frame=base_forecast_frame,
        base_schedule=base_schedule,
        storage_adjusted_frame=impact.frame,
        storage_schedule=storage_schedule_output.schedule,
        model_performance=model_performance,
        daily_model_performance=daily_performance,
        metrics=metrics,
        assumptions=assumptions,
    )


def registry_to_dict(registry: ForecastModelRegistry) -> dict[str, Any]:
    return asdict(registry)


def _selectable_model_performance(
    frame: pd.DataFrame,
    target_date: date,
    validation_days: int,
    model_candidates: tuple[str, ...],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    prior_dates = sorted(day for day in frame["timestamp"].dt.date.unique() if day < target_date)
    if not prior_dates or validation_days <= 0:
        return pd.DataFrame(), pd.DataFrame()
    validation_dates = prior_dates[-validation_days:]
    return compare_forecast_models_walk_forward(
        frame[frame["timestamp"].dt.date <= validation_dates[-1]].copy(),
        validation_dates[0],
        validation_dates[-1],
        model_candidates=model_candidates,
    )


def _select_model_for_target(
    model_performance: pd.DataFrame,
    train_frame: pd.DataFrame,
    model_candidates: tuple[str, ...],
) -> str:
    if not model_performance.empty:
        return select_best_model(model_performance)

    priced_rows = len(train_frame.dropna(subset=["dam_price_eur_mwh"]))
    for model_name in reversed(model_candidates):
        try:
            if priced_rows >= minimum_training_rows_for_model(model_name):
                return model_name
        except ForecastingError:
            continue
    return "structural_proxy"


def _forecast_for_target(train_frame: pd.DataFrame, target_frame: pd.DataFrame, model_name: str):
    try:
        return forecast_price_with_model(train_frame, target_frame, model_name)
    except ForecastingError:
        return forecast_price_with_uncertainty(train_frame, target_frame)


def _build_registry(
    selected_model: str,
    target_date: date,
    train_frame: pd.DataFrame,
    target_frame: pd.DataFrame,
    validation_days: int,
    model_candidates: tuple[str, ...],
    model_performance: pd.DataFrame,
    source_summary: dict[str, int],
    warnings: tuple[str, ...],
    feature_columns: tuple[str, ...],
) -> ForecastModelRegistry:
    selected_rows = (
        model_performance[model_performance["model"] == selected_model]
        if not model_performance.empty and "model" in model_performance
        else pd.DataFrame()
    )
    selected_metrics = (
        selected_rows.iloc[0].replace({np.nan: None}).to_dict()
        if not selected_rows.empty
        else {
            "model": selected_model,
            "mae_eur_mwh": None,
            "rmse_eur_mwh": None,
            "top_quartile_accuracy": None,
            "bottom_quartile_accuracy": None,
            "spread_direction_accuracy": None,
        }
    )
    validation_start = None
    validation_end = None
    prior_dates = sorted(train_frame["timestamp"].dt.date.unique()) if not train_frame.empty else []
    if prior_dates and validation_days > 0:
        validation_dates = prior_dates[-validation_days:]
        validation_start = validation_dates[0].isoformat()
        validation_end = validation_dates[-1].isoformat()

    eligible_features = candidate_feature_columns(target_frame)
    leakage_audit = {
        "live_safe": True,
        "eligible_feature_count": len(eligible_features),
        "used_feature_count": len(feature_columns),
        "used_features_are_live_safe": set(feature_columns).issubset(set(eligible_features)),
        "blocked_feature_examples": [
            "dam_price_eur_mwh",
            "actual_load_mw",
            "actual_res_mw",
            "curve_slope_eur_mwh_per_mw",
        ],
        "warnings_count": len(warnings),
    }

    priced_train = train_frame.dropna(subset=["dam_price_eur_mwh"])
    return ForecastModelRegistry(
        selected_model=selected_model,
        target_date=target_date.isoformat(),
        training_start=(
            priced_train["timestamp"].min().date().isoformat() if not priced_train.empty else None
        ),
        training_end=(
            priced_train["timestamp"].max().date().isoformat() if not priced_train.empty else None
        ),
        validation_start=validation_start,
        validation_end=validation_end,
        training_rows=len(priced_train),
        feature_columns=feature_columns,
        candidate_models=model_candidates,
        selected_metrics=selected_metrics,
        leakage_audit=leakage_audit,
        source_summary=source_summary,
    )


def _storage_forecast_metrics(
    target_frame: pd.DataFrame,
    base_forecast_frame: pd.DataFrame,
    base_schedule: pd.DataFrame,
    storage_adjusted_frame: pd.DataFrame,
    storage_schedule: pd.DataFrame,
    battery_params: BatteryParams,
    impact_metrics: dict[str, float],
) -> dict[str, float | str | None]:
    base_forecast_quality = forecast_quality_metrics(
        target_frame["dam_price_eur_mwh"],
        base_forecast_frame["forecast_price_eur_mwh"],
    )
    adjusted_forecast_quality = forecast_quality_metrics(
        target_frame["dam_price_eur_mwh"],
        storage_adjusted_frame["storage_adjusted_forecast_eur_mwh"],
    )
    base_objective = optimize_battery_schedule(
        base_forecast_frame,
        battery_params,
        price_col="forecast_price_eur_mwh",
    ).metrics
    storage_objective = optimize_battery_schedule(
        storage_adjusted_frame,
        battery_params,
        price_col="storage_adjusted_forecast_eur_mwh",
    ).metrics
    base_realized = settle_schedule_on_actual_prices(base_schedule, target_frame, battery_params)
    storage_realized = settle_schedule_on_actual_prices(storage_schedule, target_frame, battery_params)
    oracle = optimize_battery_schedule(target_frame, battery_params, price_col="dam_price_eur_mwh").metrics
    oracle_net = oracle["net_revenue_eur"]

    return {
        "base_forecast_mae_eur_mwh": base_forecast_quality["mae_eur_mwh"],
        "base_forecast_rmse_eur_mwh": base_forecast_quality["rmse_eur_mwh"],
        "base_top_quartile_accuracy": base_forecast_quality["top_quartile_accuracy"],
        "base_bottom_quartile_accuracy": base_forecast_quality["bottom_quartile_accuracy"],
        "base_spread_direction_accuracy": base_forecast_quality[
            "spread_direction_accuracy"
        ],
        "adjusted_forecast_mae_eur_mwh": adjusted_forecast_quality["mae_eur_mwh"],
        "price_taker_objective_net_revenue_eur": base_objective["net_revenue_eur"],
        "storage_aware_objective_net_revenue_eur": storage_objective["net_revenue_eur"],
        "price_taker_realized_net_revenue_eur": base_realized["net_revenue_eur"],
        "storage_aware_realized_net_revenue_eur": storage_realized["net_revenue_eur"],
        "oracle_net_revenue_eur": oracle_net,
        "price_taker_capture_ratio_vs_oracle": (
            base_realized["net_revenue_eur"] / oracle_net if abs(oracle_net) > 1e-9 else None
        ),
        "storage_aware_capture_ratio_vs_oracle": (
            storage_realized["net_revenue_eur"] / oracle_net if abs(oracle_net) > 1e-9 else None
        ),
        "storage_aware_revenue_delta_eur": (
            storage_objective["net_revenue_eur"] - base_objective["net_revenue_eur"]
        ),
        **{f"impact_{key}": value for key, value in impact_metrics.items()},
    }


def _target_frame(frame: pd.DataFrame, target_date: date) -> pd.DataFrame:
    return (
        frame[frame["timestamp"].dt.date == target_date]
        .drop(columns=["delivery_date"], errors="ignore")
        .reset_index(drop=True)
    )


def _training_frame(frame: pd.DataFrame, target_date: date) -> pd.DataFrame:
    return (
        frame[frame["timestamp"].dt.date < target_date]
        .drop(columns=["delivery_date"], errors="ignore")
        .reset_index(drop=True)
    )
