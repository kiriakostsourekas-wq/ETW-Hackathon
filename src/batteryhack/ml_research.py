from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import ElasticNet, RidgeCV
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .forecasting import (
    ForecastingError,
    add_calendar_features,
    candidate_feature_columns,
    forecast_quality_metrics,
    price_shape_baseline_forecast,
)
from .optimizer import BatteryParams, optimize_battery_schedule
from .simulation import daterange, settle_schedule_on_actual_prices


DEFAULT_RESEARCH_MODEL_CANDIDATES = (
    "interval_profile",
    "ridge",
    "elastic_net",
    "hist_gradient_boosting",
    "extra_trees",
    "stacked_ensemble",
    "scarcity_ensemble",
)
SUPPORTED_RESEARCH_MODEL_CANDIDATES = DEFAULT_RESEARCH_MODEL_CANDIDATES + (
    "scarcity_ensemble_conservative",
)

STACK_BASE_MODELS = ("ridge", "hist_gradient_boosting", "extra_trees")
SCARCITY_BASE_MODELS = (
    "ridge",
    "extra_trees",
    "hist_gradient_boosting",
    "interval_profile",
)
SCARCITY_VALIDATION_DAYS = 3
SCARCITY_DISAGREEMENT_THRESHOLD_EUR_MWH = 18.0
SCARCITY_CONSERVATIVE_SHRINK = 0.35
DEFAULT_FEATURE_SET = "all_live_safe"
FEATURE_SET_COLUMNS = {
    "all_live_safe": None,
    "calendar_only": ("hour_sin", "hour_cos", "is_weekend", "evening_peak", "solar_peak"),
    "load_res_net_load": (
        "load_forecast_mw",
        "res_forecast_mw",
        "net_load_forecast_mw",
        "res_share_forecast",
    ),
    "weather_only": (
        "shortwave_radiation",
        "cloud_cover",
        "temperature_2m",
        "wind_speed_10m",
    ),
}


@dataclass(frozen=True)
class CandidateForecast:
    model: str
    forecast: pd.Series
    feature_columns: tuple[str, ...]
    diagnostics: dict[str, float | str]
    interval_diagnostics: pd.DataFrame | None = None


@dataclass(frozen=True)
class MLResearchResult:
    summary: pd.DataFrame
    daily: pd.DataFrame
    predictions: pd.DataFrame
    skipped_days: pd.DataFrame
    assumptions: dict[str, object]


def run_ml_research_backtest(
    history: pd.DataFrame,
    start_date: date,
    end_date: date,
    battery_params: BatteryParams,
    min_train_days: int = 14,
    max_days: int | None = None,
    model_candidates: tuple[str, ...] = DEFAULT_RESEARCH_MODEL_CANDIDATES,
    drop_synthetic_targets: bool = True,
    drop_synthetic_training: bool = True,
    feature_set: str = DEFAULT_FEATURE_SET,
) -> MLResearchResult:
    """Run a chronological, no-target-leakage model research backtest.

    Each target day is forecast using rows strictly before that delivery date. By default,
    target days and training labels marked as synthetic price fallback are excluded.
    """
    if min_train_days < 1:
        raise ValueError("min_train_days must be at least 1")
    _validate_model_candidates(model_candidates)
    _validate_feature_set(feature_set)

    frame = _normalize_history(history)
    daily_rows: list[dict[str, float | str | bool | None]] = []
    prediction_parts: list[pd.DataFrame] = []
    skipped_rows: list[dict[str, str | int]] = []
    evaluated_days = 0

    target_dates = list(daterange(start_date, end_date))
    if max_days is not None:
        target_dates = target_dates[:max_days]

    for delivery_date in target_dates:
        target = _target_frame(frame, delivery_date)
        if target.empty:
            skipped_rows.append({"delivery_date": delivery_date.isoformat(), "reason": "no rows"})
            continue
        if not _has_complete_target_prices(target):
            skipped_rows.append(
                {"delivery_date": delivery_date.isoformat(), "reason": "missing target prices"}
            )
            continue
        if drop_synthetic_targets and not _is_public_price_day(target):
            skipped_rows.append(
                {"delivery_date": delivery_date.isoformat(), "reason": "synthetic target prices"}
            )
            continue

        train = _training_frame(frame, delivery_date, drop_synthetic_training)
        train_priced = train.dropna(subset=["dam_price_eur_mwh"])
        train_days = _priced_training_days(train_priced)
        if train_days < min_train_days:
            skipped_rows.append(
                {
                    "delivery_date": delivery_date.isoformat(),
                    "reason": "insufficient prior training days",
                    "training_days": train_days,
                }
            )
            continue

        oracle = optimize_battery_schedule(
            target,
            battery_params,
            price_col="dam_price_eur_mwh",
        )
        oracle_net = float(oracle.metrics["net_revenue_eur"])

        for model_name in model_candidates:
            try:
                candidate = forecast_with_research_model(
                    train,
                    target,
                    model_name,
                    feature_set=feature_set,
                    battery_params=battery_params,
                )
            except ForecastingError as exc:
                skipped_rows.append(
                    {
                        "delivery_date": delivery_date.isoformat(),
                        "reason": f"{model_name}: {exc}",
                        "training_days": train_days,
                    }
                )
                continue

            forecast_frame = target.copy()
            forecast_frame["forecast_price_eur_mwh"] = candidate.forecast.to_numpy(float)
            dispatch_mode = "standard"
            mean_adjustment = 0.0
            if _uses_conservative_dispatch(model_name):
                raw_forecast = forecast_frame["forecast_price_eur_mwh"].copy()
                forecast_frame["forecast_price_eur_mwh"] = _conservative_dispatch_forecast(
                    raw_forecast,
                    candidate.interval_diagnostics,
                )
                mean_adjustment = float(
                    (forecast_frame["forecast_price_eur_mwh"] - raw_forecast).abs().mean()
                )
                dispatch_mode = "conservative_spread_shrink"
            dispatch = optimize_battery_schedule(
                forecast_frame,
                battery_params,
                price_col="forecast_price_eur_mwh",
            )
            realized = settle_schedule_on_actual_prices(
                dispatch.schedule,
                target,
                battery_params,
            )
            quality = forecast_quality_metrics(
                target["dam_price_eur_mwh"],
                forecast_frame["forecast_price_eur_mwh"],
            )
            capture = (
                realized["net_revenue_eur"] / oracle_net if abs(oracle_net) > 1e-9 else np.nan
            )
            training_start = (
                train_priced["timestamp"].min().date().isoformat()
                if not train_priced.empty
                else None
            )
            training_end = (
                train_priced["timestamp"].max().date().isoformat()
                if not train_priced.empty
                else None
            )
            mean_disagreement = _diagnostic_float(
                candidate.interval_diagnostics,
                "model_disagreement_eur_mwh",
                "mean",
            )
            max_disagreement = _diagnostic_float(
                candidate.interval_diagnostics,
                "model_disagreement_eur_mwh",
                "max",
            )

            daily_rows.append(
                {
                    "delivery_date": delivery_date.isoformat(),
                    "model": model_name,
                    "feature_set": feature_set,
                    "dispatch_mode": dispatch_mode,
                    "training_start": training_start,
                    "training_end": training_end,
                    "training_days": train_days,
                    "training_rows": int(len(train_priced)),
                    "target_public_price_data": _is_public_price_day(target),
                    "feature_count": len(candidate.feature_columns),
                    "mae_eur_mwh": quality["mae_eur_mwh"],
                    "rmse_eur_mwh": quality["rmse_eur_mwh"],
                    "spread_direction_accuracy": quality["spread_direction_accuracy"],
                    "top_quartile_accuracy": quality["top_quartile_accuracy"],
                    "bottom_quartile_accuracy": quality["bottom_quartile_accuracy"],
                    "forecast_objective_net_revenue_eur": dispatch.metrics["net_revenue_eur"],
                    "realized_net_revenue_eur": realized["net_revenue_eur"],
                    "oracle_net_revenue_eur": oracle_net,
                    "capture_ratio_vs_oracle": capture,
                    "realized_charged_mwh": realized["charged_mwh"],
                    "realized_discharged_mwh": realized["discharged_mwh"],
                    "realized_equivalent_cycles": realized["equivalent_cycles"],
                    "realized_captured_spread_eur_mwh": realized["captured_spread_eur_mwh"],
                    "forecast_max_price_eur_mwh": float(
                        forecast_frame["forecast_price_eur_mwh"].max()
                    ),
                    "forecast_min_price_eur_mwh": float(
                        forecast_frame["forecast_price_eur_mwh"].min()
                    ),
                    "actual_max_price_eur_mwh": float(target["dam_price_eur_mwh"].max()),
                    "actual_min_price_eur_mwh": float(target["dam_price_eur_mwh"].min()),
                    "mean_model_disagreement_eur_mwh": mean_disagreement,
                    "max_model_disagreement_eur_mwh": max_disagreement,
                    "high_disagreement_day": bool(
                        pd.notna(mean_disagreement)
                        and mean_disagreement >= SCARCITY_DISAGREEMENT_THRESHOLD_EUR_MWH
                    ),
                    "dispatch_mean_abs_adjustment_eur_mwh": mean_adjustment,
                    "scarcity_weights": str(candidate.diagnostics.get("scarcity_weights", "")),
                }
            )
            prediction_parts.append(
                _prediction_output(
                    delivery_date=delivery_date,
                    model_name=model_name,
                    feature_set=feature_set,
                    dispatch_mode=dispatch_mode,
                    target=target,
                    forecast_frame=forecast_frame,
                    schedule=dispatch.schedule,
                    interval_diagnostics=candidate.interval_diagnostics,
                )
            )
        evaluated_days += 1

    daily = pd.DataFrame(daily_rows)
    predictions = (
        pd.concat(prediction_parts, ignore_index=True)
        if prediction_parts
        else pd.DataFrame(
            columns=[
                "delivery_date",
                "timestamp",
                "interval",
                "model",
                "feature_set",
                "dispatch_mode",
                "actual_price_eur_mwh",
                "forecast_price_eur_mwh",
                "charge_mw",
                "discharge_mw",
                "net_power_mw",
                "soc_pct_end",
            ]
        )
    )
    summary = summarize_model_performance(daily, predictions)
    assumptions = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "min_train_days": min_train_days,
        "max_days": max_days,
        "model_candidates": list(model_candidates),
        "feature_set": feature_set,
        "drop_synthetic_targets": drop_synthetic_targets,
        "drop_synthetic_training": drop_synthetic_training,
        "evaluated_target_days": evaluated_days,
        "leakage_rule": (
            "target day is excluded from training; only rows with timestamp date "
            "< target date are fit"
        ),
        "dispatch_assumption": (
            "price-taking schedule optimized on forecast prices, settled on published DAM MCP"
        ),
    }
    return MLResearchResult(
        summary=summary,
        daily=daily,
        predictions=predictions,
        skipped_days=pd.DataFrame(skipped_rows),
        assumptions=assumptions,
    )


def forecast_with_research_model(
    history: pd.DataFrame,
    target: pd.DataFrame,
    model_name: str,
    feature_set: str = DEFAULT_FEATURE_SET,
    battery_params: BatteryParams | None = None,
) -> CandidateForecast:
    _validate_model_candidates((model_name,))
    _validate_feature_set(feature_set)
    forecast_model_name = _base_forecast_model_name(model_name)
    train = _normalize_history(history)
    target_frame = _normalize_history(target)
    if train.empty:
        raise ForecastingError(f"{model_name} needs prior training rows")

    if forecast_model_name == "scarcity_ensemble":
        if battery_params is None:
            raise ForecastingError("scarcity_ensemble requires battery_params")
        return _scarcity_ensemble_forecast(
            train,
            target_frame,
            battery_params,
            feature_set=feature_set,
        )

    if forecast_model_name == "interval_profile":
        forecast = price_shape_baseline_forecast(train, target_frame)
        return CandidateForecast(
            model=model_name,
            forecast=forecast.rename("forecast_price_eur_mwh"),
            feature_columns=("interval", "is_weekend"),
            diagnostics={"model_family": "profile"},
        )
    if forecast_model_name == "stacked_ensemble":
        return _stacked_ensemble_forecast(train, target_frame, feature_set=feature_set)

    columns, x_train, y_train, x_target = _supervised_matrices(
        train,
        target_frame,
        feature_set,
    )
    estimator = _build_estimator(forecast_model_name)
    estimator.fit(x_train, y_train)
    prediction = pd.Series(
        estimator.predict(x_target),
        index=target_frame.index,
        name="forecast_price_eur_mwh",
    )
    return CandidateForecast(
        model=model_name,
        forecast=prediction.clip(lower=-75),
        feature_columns=columns,
        diagnostics={"model_family": forecast_model_name, "feature_set": feature_set},
    )


def summarize_model_performance(daily: pd.DataFrame, predictions: pd.DataFrame) -> pd.DataFrame:
    if daily.empty:
        return pd.DataFrame()

    rows: list[dict[str, float | str | int]] = []
    group_columns = ["model"]
    if "feature_set" in daily.columns:
        group_columns.append("feature_set")

    for group_key, model_daily in daily.groupby(group_columns, sort=False):
        if isinstance(group_key, tuple):
            model_name = str(group_key[0])
            feature_set = str(group_key[1])
        else:
            model_name = str(group_key)
            feature_set = DEFAULT_FEATURE_SET
        model_predictions = predictions[predictions["model"] == model_name]
        if "feature_set" in model_predictions.columns:
            model_predictions = model_predictions[
                model_predictions["feature_set"] == feature_set
            ]
        if model_predictions.empty:
            aggregate_quality = {
                "mae_eur_mwh": float(model_daily["mae_eur_mwh"].mean()),
                "rmse_eur_mwh": float(model_daily["rmse_eur_mwh"].mean()),
                "spread_direction_accuracy": float(
                    model_daily["spread_direction_accuracy"].mean()
                ),
                "top_quartile_accuracy": float(model_daily["top_quartile_accuracy"].mean()),
                "bottom_quartile_accuracy": float(
                    model_daily["bottom_quartile_accuracy"].mean()
                ),
            }
            intervals = 0
        else:
            aggregate_quality = forecast_quality_metrics(
                model_predictions["actual_price_eur_mwh"],
                model_predictions["forecast_price_eur_mwh"],
            )
            intervals = int(len(model_predictions))

        total_realized = float(model_daily["realized_net_revenue_eur"].sum())
        total_oracle = float(model_daily["oracle_net_revenue_eur"].sum())
        rows.append(
            {
                "model": str(model_name),
                "feature_set": feature_set,
                "days_evaluated": int(model_daily["delivery_date"].nunique()),
                "intervals_evaluated": intervals,
                **aggregate_quality,
                "mean_daily_mae_eur_mwh": float(model_daily["mae_eur_mwh"].mean()),
                "mean_daily_rmse_eur_mwh": float(model_daily["rmse_eur_mwh"].mean()),
                "mean_daily_spread_direction_accuracy": float(
                    model_daily["spread_direction_accuracy"].mean()
                ),
                "mean_daily_top_quartile_accuracy": float(
                    model_daily["top_quartile_accuracy"].mean()
                ),
                "mean_daily_bottom_quartile_accuracy": float(
                    model_daily["bottom_quartile_accuracy"].mean()
                ),
                "total_forecast_objective_net_revenue_eur": float(
                    model_daily["forecast_objective_net_revenue_eur"].sum()
                ),
                "total_realized_net_revenue_eur": total_realized,
                "total_oracle_net_revenue_eur": total_oracle,
                "capture_ratio_vs_oracle": (
                    total_realized / total_oracle if abs(total_oracle) > 1e-9 else np.nan
                ),
                "mean_daily_capture_ratio_vs_oracle": float(
                    model_daily["capture_ratio_vs_oracle"].mean()
                ),
                "mean_training_days": float(model_daily["training_days"].mean()),
                "mean_training_rows": float(model_daily["training_rows"].mean()),
                "mean_feature_count": float(model_daily["feature_count"].mean()),
            }
        )

    return (
        pd.DataFrame(rows)
        .sort_values(["mae_eur_mwh", "rmse_eur_mwh", "model"])
        .reset_index(drop=True)
    )

def run_feature_ablation_backtest(
    history: pd.DataFrame,
    start_date: date,
    end_date: date,
    battery_params: BatteryParams,
    min_train_days: int = 14,
    max_days: int | None = None,
    model_name: str = "ridge",
    feature_sets: tuple[str, ...] = tuple(FEATURE_SET_COLUMNS),
    drop_synthetic_targets: bool = True,
    drop_synthetic_training: bool = True,
) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for feature_set in feature_sets:
        result = run_ml_research_backtest(
            history=history,
            start_date=start_date,
            end_date=end_date,
            battery_params=battery_params,
            min_train_days=min_train_days,
            max_days=max_days,
            model_candidates=(model_name,),
            drop_synthetic_targets=drop_synthetic_targets,
            drop_synthetic_training=drop_synthetic_training,
            feature_set=feature_set,
        )
        if result.summary.empty:
            rows.append(
                pd.DataFrame(
                    [
                        {
                            "model": model_name,
                            "feature_set": feature_set,
                            "days_evaluated": 0,
                            "status": "no evaluated days",
                        }
                    ]
                )
            )
        else:
            summary = result.summary.copy()
            summary["status"] = "ok"
            rows.append(summary)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def build_daily_winners(daily: pd.DataFrame) -> pd.DataFrame:
    if daily.empty:
        return pd.DataFrame()
    required = {"delivery_date", "model", "realized_net_revenue_eur"}
    missing = required - set(daily.columns)
    if missing:
        raise ValueError(f"daily results missing columns: {sorted(missing)}")

    rows: list[dict[str, float | str]] = []
    for delivery_date, group in daily.groupby("delivery_date", sort=True):
        ordered = group.sort_values(
            ["realized_net_revenue_eur", "model"],
            ascending=[False, True],
        ).reset_index(drop=True)
        winner = ordered.iloc[0]
        runner_up = ordered.iloc[1] if len(ordered) > 1 else ordered.iloc[0]
        rows.append(
            {
                "delivery_date": str(delivery_date),
                "winning_model": str(winner["model"]),
                "winning_realized_net_revenue_eur": float(
                    winner["realized_net_revenue_eur"]
                ),
                "runner_up_model": str(runner_up["model"]),
                "runner_up_realized_net_revenue_eur": float(
                    runner_up["realized_net_revenue_eur"]
                ),
                "win_margin_eur": float(
                    winner["realized_net_revenue_eur"]
                    - runner_up["realized_net_revenue_eur"]
                ),
                "winning_capture_ratio_vs_oracle": float(
                    winner["capture_ratio_vs_oracle"]
                ),
            }
        )
    return pd.DataFrame(rows)


def build_model_selection_stability(
    summary: pd.DataFrame,
    daily: pd.DataFrame,
) -> pd.DataFrame:
    if summary.empty or daily.empty:
        return pd.DataFrame()

    daily_winners = build_daily_winners(daily)
    winner_counts = daily_winners["winning_model"].value_counts().rename("winner_count")
    daily_by_model = daily.groupby("model", as_index=False).agg(
        mean_daily_realized_net_revenue_eur=("realized_net_revenue_eur", "mean"),
        median_daily_realized_net_revenue_eur=("realized_net_revenue_eur", "median"),
        mean_daily_capture_ratio_vs_oracle=("capture_ratio_vs_oracle", "mean"),
        median_daily_capture_ratio_vs_oracle=("capture_ratio_vs_oracle", "median"),
    )
    stable = summary.merge(daily_by_model, on="model", how="left")
    stable["daily_pnl_winner_count"] = stable["model"].map(winner_counts).fillna(0).astype(int)

    criteria = [
        ("total_pnl", "total_realized_net_revenue_eur", True),
        ("mean_daily_pnl", "mean_daily_realized_net_revenue_eur", True),
        ("median_daily_pnl", "median_daily_realized_net_revenue_eur", True),
        ("mae", "mae_eur_mwh", False),
        ("top_quartile_accuracy", "top_quartile_accuracy", True),
        ("bottom_quartile_accuracy", "bottom_quartile_accuracy", True),
        ("capture_ratio", "capture_ratio_vs_oracle", True),
        ("daily_pnl_winner_count", "daily_pnl_winner_count", True),
    ]
    rows: list[dict[str, float | str | bool]] = []
    for criterion, column, higher_is_better in criteria:
        ordered = stable.sort_values(
            [column, "model"],
            ascending=[not higher_is_better, True],
        ).reset_index(drop=True)
        winner = ordered.iloc[0]
        runner_up = ordered.iloc[1] if len(ordered) > 1 else ordered.iloc[0]
        rows.append(
            {
                "criterion": criterion,
                "metric_column": column,
                "higher_is_better": higher_is_better,
                "winning_model": str(winner["model"]),
                "winning_value": float(winner[column]),
                "runner_up_model": str(runner_up["model"]),
                "runner_up_value": float(runner_up[column]),
                "margin_vs_runner_up": float(winner[column] - runner_up[column]),
            }
        )
    return pd.DataFrame(rows)


def build_paired_uplift_summary(
    daily: pd.DataFrame,
    primary_model: str = "ridge",
    comparison_models: tuple[str, ...] = ("extra_trees", "interval_profile"),
) -> pd.DataFrame:
    if daily.empty:
        return pd.DataFrame()

    rows: list[dict[str, float | str | int]] = []
    for comparison_model in comparison_models:
        primary = _model_daily_series(daily, primary_model)
        comparison = _model_daily_series(daily, comparison_model)
        joined = primary.join(comparison, how="inner", lsuffix="_primary", rsuffix="_comparison")
        if joined.empty:
            rows.append(
                {
                    "primary_model": primary_model,
                    "comparison_model": comparison_model,
                    "paired_days": 0,
                    "status": "no overlapping dates",
                }
            )
            continue
        pnl_uplift = (
            joined["realized_net_revenue_eur_primary"]
            - joined["realized_net_revenue_eur_comparison"]
        )
        capture_uplift = (
            joined["capture_ratio_vs_oracle_primary"]
            - joined["capture_ratio_vs_oracle_comparison"]
        )
        rows.append(
            {
                "primary_model": primary_model,
                "comparison_model": comparison_model,
                "paired_days": int(len(joined)),
                "status": "ok",
                "primary_total_realized_net_revenue_eur": float(
                    joined["realized_net_revenue_eur_primary"].sum()
                ),
                "comparison_total_realized_net_revenue_eur": float(
                    joined["realized_net_revenue_eur_comparison"].sum()
                ),
                "total_pnl_uplift_eur": float(pnl_uplift.sum()),
                "mean_daily_pnl_uplift_eur": float(pnl_uplift.mean()),
                "median_daily_pnl_uplift_eur": float(pnl_uplift.median()),
                "primary_win_days": int((pnl_uplift > 0).sum()),
                "comparison_win_days": int((pnl_uplift < 0).sum()),
                "tie_days": int((pnl_uplift == 0).sum()),
                "mean_capture_ratio_uplift": float(capture_uplift.mean()),
                "median_capture_ratio_uplift": float(capture_uplift.median()),
            }
        )
    return pd.DataFrame(rows)


def benchmark_frame_as_model_daily(
    benchmark: pd.DataFrame,
    model_name: str,
) -> pd.DataFrame:
    required = {"delivery_date", "realized_net_revenue_eur", "capture_ratio_vs_oracle"}
    missing = required - set(benchmark.columns)
    if missing:
        raise ValueError(f"benchmark frame missing columns: {sorted(missing)}")
    output = benchmark[
        ["delivery_date", "realized_net_revenue_eur", "capture_ratio_vs_oracle"]
    ].copy()
    output["model"] = model_name
    return output


def _scarcity_ensemble_forecast(
    train: pd.DataFrame,
    target: pd.DataFrame,
    battery_params: BatteryParams,
    feature_set: str,
) -> CandidateForecast:
    target_dates = sorted(target["timestamp"].dt.date.unique())
    if target_dates:
        train = train[train["timestamp"].dt.date < target_dates[0]].copy()
    if train.empty:
        raise ForecastingError("scarcity_ensemble needs prior training rows")

    base_predictions = _scarcity_base_prediction_frame(train, target, feature_set)
    if len(base_predictions.columns) < 2:
        raise ForecastingError("scarcity_ensemble has fewer than two trainable base models")

    validation = _recent_validation_model_scores(train, battery_params, feature_set)
    weights = _scarcity_weights(validation, tuple(base_predictions.columns))
    weight_array = np.array([weights[column] for column in base_predictions.columns], dtype=float)
    forecast_values = base_predictions.to_numpy(float) @ weight_array
    forecast = pd.Series(
        forecast_values,
        index=target.index,
        name="forecast_price_eur_mwh",
    ).clip(lower=-75)
    disagreement = base_predictions.std(axis=1).fillna(0.0)

    interval_diagnostics = target[["timestamp", "interval"]].copy()
    interval_diagnostics["raw_ensemble_forecast_price_eur_mwh"] = forecast.to_numpy(float)
    interval_diagnostics["model_disagreement_eur_mwh"] = disagreement.to_numpy(float)
    for model_name in base_predictions.columns:
        interval_diagnostics[f"base_forecast_{model_name}_eur_mwh"] = base_predictions[
            model_name
        ].to_numpy(float)
        interval_diagnostics[f"weight_{model_name}"] = float(weights[model_name])

    diagnostics: dict[str, float | str] = {
        "model_family": "scarcity_weighted_ensemble",
        "feature_set": feature_set,
        "base_models": ",".join(base_predictions.columns),
        "scarcity_weight_metric": "recent_validation_capture_ratio_vs_oracle",
        "scarcity_weights": ",".join(
            f"{model}={weights[model]:.4f}" for model in base_predictions.columns
        ),
        "validation_days": float(validation["delivery_date"].nunique())
        if not validation.empty
        else 0.0,
        "validation_dates": ",".join(sorted(validation["delivery_date"].unique()))
        if not validation.empty
        else "",
        "mean_model_disagreement_eur_mwh": float(disagreement.mean()),
        "max_model_disagreement_eur_mwh": float(disagreement.max()),
    }
    return CandidateForecast(
        model="scarcity_ensemble",
        forecast=forecast,
        feature_columns=tuple(base_predictions.columns),
        diagnostics=diagnostics,
        interval_diagnostics=interval_diagnostics,
    )


def _scarcity_base_prediction_frame(
    train: pd.DataFrame,
    target: pd.DataFrame,
    feature_set: str,
) -> pd.DataFrame:
    predictions: dict[str, np.ndarray] = {}
    for model_name in SCARCITY_BASE_MODELS:
        try:
            candidate = forecast_with_research_model(
                train,
                target,
                model_name,
                feature_set=feature_set,
            )
        except ForecastingError:
            continue
        predictions[model_name] = candidate.forecast.to_numpy(float)
    return pd.DataFrame(predictions, index=target.index)


def _recent_validation_model_scores(
    train: pd.DataFrame,
    battery_params: BatteryParams,
    feature_set: str,
) -> pd.DataFrame:
    validation_dates = _available_training_dates(train)[-SCARCITY_VALIDATION_DAYS:]
    rows: list[dict[str, float | str]] = []
    for validation_day in validation_dates:
        subtrain = train[train["timestamp"].dt.date < validation_day].copy()
        validation = train[train["timestamp"].dt.date == validation_day].copy()
        if subtrain.empty or validation.empty or not _has_complete_target_prices(validation):
            continue
        try:
            oracle = optimize_battery_schedule(
                validation,
                battery_params,
                price_col="dam_price_eur_mwh",
            )
        except Exception:
            continue
        oracle_net = float(oracle.metrics["net_revenue_eur"])

        for model_name in SCARCITY_BASE_MODELS:
            try:
                candidate = forecast_with_research_model(
                    subtrain,
                    validation,
                    model_name,
                    feature_set=feature_set,
                )
                forecast_frame = validation.copy()
                forecast_frame["forecast_price_eur_mwh"] = candidate.forecast.to_numpy(float)
                dispatch = optimize_battery_schedule(
                    forecast_frame,
                    battery_params,
                    price_col="forecast_price_eur_mwh",
                )
                realized = settle_schedule_on_actual_prices(
                    dispatch.schedule,
                    validation,
                    battery_params,
                )
            except Exception:
                continue
            capture = (
                realized["net_revenue_eur"] / oracle_net
                if abs(oracle_net) > 1e-9
                else np.nan
            )
            rows.append(
                {
                    "delivery_date": validation_day.isoformat(),
                    "model": model_name,
                    "realized_net_revenue_eur": realized["net_revenue_eur"],
                    "capture_ratio_vs_oracle": capture,
                }
            )
    return pd.DataFrame(rows)


def _scarcity_weights(
    validation: pd.DataFrame,
    model_names: tuple[str, ...],
) -> dict[str, float]:
    if validation.empty:
        return _equal_weights(model_names)

    scores = (
        validation.groupby("model")["capture_ratio_vs_oracle"]
        .mean()
        .reindex(model_names)
        .fillna(0.0)
        .clip(lower=0.0)
    )
    if float(scores.sum()) <= 1e-12:
        return _equal_weights(model_names)
    weights = scores / scores.sum()
    return {model_name: float(weights.loc[model_name]) for model_name in model_names}


def _equal_weights(model_names: tuple[str, ...]) -> dict[str, float]:
    if not model_names:
        return {}
    weight = 1.0 / len(model_names)
    return {model_name: weight for model_name in model_names}


def _conservative_dispatch_forecast(
    forecast: pd.Series,
    interval_diagnostics: pd.DataFrame | None,
) -> pd.Series:
    if interval_diagnostics is None or interval_diagnostics.empty:
        return forecast
    if "model_disagreement_eur_mwh" not in interval_diagnostics.columns:
        return forecast

    disagreement = pd.Series(
        interval_diagnostics["model_disagreement_eur_mwh"].to_numpy(float),
        index=forecast.index,
    ).fillna(0.0)
    mean_disagreement = float(disagreement.mean())
    if mean_disagreement < SCARCITY_DISAGREEMENT_THRESHOLD_EUR_MWH:
        return forecast

    center = float(forecast.median())
    stress = min(
        1.0,
        mean_disagreement / max(SCARCITY_DISAGREEMENT_THRESHOLD_EUR_MWH, 1.0) - 1.0,
    )
    interval_stress = (disagreement / max(mean_disagreement, 1.0)).clip(lower=0.5, upper=2.0)
    shrink = (1.0 - SCARCITY_CONSERVATIVE_SHRINK * stress * interval_stress).clip(
        lower=0.35,
        upper=1.0,
    )
    adjusted = center + (forecast - center) * shrink
    return adjusted.rename(forecast.name)


def _stacked_ensemble_forecast(
    train: pd.DataFrame,
    target: pd.DataFrame,
    feature_set: str = DEFAULT_FEATURE_SET,
) -> CandidateForecast:
    training_days = _available_training_dates(train)
    if len(training_days) < 3:
        return _average_ensemble_forecast(
            train,
            target,
            "not enough days for meta fit",
            feature_set,
        )

    validation_days = training_days[-min(3, max(1, len(training_days) // 5)) :]
    meta_parts: list[pd.DataFrame] = []
    base_names: set[str] = set()

    for validation_day in validation_days:
        subtrain = train[train["timestamp"].dt.date < validation_day].copy()
        validation = train[train["timestamp"].dt.date == validation_day].copy()
        if validation.empty or subtrain.empty:
            continue
        base_predictions = _base_model_prediction_frame(subtrain, validation, feature_set)
        if len(base_predictions.columns) < 2:
            continue
        base_names.update(base_predictions.columns)
        meta = base_predictions.copy()
        meta["actual"] = validation["dam_price_eur_mwh"].to_numpy(float)
        meta_parts.append(meta.dropna())

    final_base = _base_model_prediction_frame(train, target, feature_set)
    if len(final_base.columns) < 2:
        return _average_ensemble_forecast(
            train,
            target,
            "fewer than two base models fit",
            feature_set,
        )
    if not meta_parts:
        return _average_from_final_base(final_base, target, "no chronological meta rows")

    meta_frame = pd.concat(meta_parts, ignore_index=True)
    usable_columns = tuple(column for column in final_base.columns if column in meta_frame.columns)
    if len(usable_columns) < 2:
        return _average_from_final_base(final_base, target, "no overlapping meta columns")

    meta_frame = meta_frame.dropna(subset=[*usable_columns, "actual"])
    if len(meta_frame) < 96:
        return _average_from_final_base(final_base, target, "insufficient meta rows")

    meta_model = RidgeCV(alphas=[0.01, 0.1, 1.0, 10.0])
    meta_model.fit(meta_frame[list(usable_columns)], meta_frame["actual"])
    prediction = pd.Series(
        meta_model.predict(final_base[list(usable_columns)]),
        index=target.index,
        name="forecast_price_eur_mwh",
    )
    return CandidateForecast(
        model="stacked_ensemble",
        forecast=prediction.clip(lower=-75),
        feature_columns=usable_columns,
        diagnostics={
            "model_family": "chronological_stacking",
            "meta_rows": float(len(meta_frame)),
            "meta_base_models": ",".join(usable_columns),
            "base_models_tried": ",".join(sorted(base_names)),
            "feature_set": feature_set,
        },
    )


def _average_ensemble_forecast(
    train: pd.DataFrame,
    target: pd.DataFrame,
    reason: str,
    feature_set: str,
) -> CandidateForecast:
    final_base = _base_model_prediction_frame(train, target, feature_set)
    if final_base.empty:
        raise ForecastingError("stacked_ensemble has no trainable base models")
    return _average_from_final_base(final_base, target, reason)


def _average_from_final_base(
    final_base: pd.DataFrame,
    target: pd.DataFrame,
    reason: str,
) -> CandidateForecast:
    prediction = final_base.mean(axis=1)
    prediction.index = target.index
    prediction.name = "forecast_price_eur_mwh"
    return CandidateForecast(
        model="stacked_ensemble",
        forecast=prediction.clip(lower=-75),
        feature_columns=tuple(final_base.columns),
        diagnostics={"model_family": "average_ensemble", "fallback_reason": reason},
    )


def _base_model_prediction_frame(
    train: pd.DataFrame,
    target: pd.DataFrame,
    feature_set: str,
) -> pd.DataFrame:
    predictions: dict[str, np.ndarray] = {}
    for model_name in STACK_BASE_MODELS:
        try:
            candidate = forecast_with_research_model(
                train,
                target,
                model_name,
                feature_set=feature_set,
            )
        except ForecastingError:
            continue
        predictions[model_name] = candidate.forecast.to_numpy(float)
    return pd.DataFrame(predictions, index=target.index)


def _build_estimator(model_name: str):
    if model_name == "ridge":
        return make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            RidgeCV(alphas=[0.1, 1.0, 10.0, 50.0]),
        )
    if model_name == "elastic_net":
        return make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            ElasticNet(alpha=0.02, l1_ratio=0.15, max_iter=5000, random_state=42),
        )
    if model_name == "hist_gradient_boosting":
        return make_pipeline(
            SimpleImputer(strategy="median"),
            HistGradientBoostingRegressor(
                max_iter=120,
                learning_rate=0.06,
                l2_regularization=0.2,
                random_state=42,
            ),
        )
    if model_name == "extra_trees":
        return make_pipeline(
            SimpleImputer(strategy="median"),
            ExtraTreesRegressor(
                n_estimators=64,
                min_samples_leaf=6,
                max_features=0.8,
                random_state=42,
                n_jobs=1,
            ),
        )
    raise ForecastingError(f"Unsupported research model: {model_name}")


def _supervised_matrices(
    train: pd.DataFrame,
    target: pd.DataFrame,
    feature_set: str,
) -> tuple[tuple[str, ...], pd.DataFrame, pd.Series, pd.DataFrame]:
    train_features = add_calendar_features(train)
    target_features = add_calendar_features(target)
    columns = _filter_feature_columns(
        tuple(
            column
            for column in candidate_feature_columns(target_features, live=True)
            if column in train_features.columns
            and train_features[column].notna().any()
            and target_features[column].notna().any()
        ),
        feature_set,
    )
    if not columns:
        raise ForecastingError("no live-safe feature columns are available")

    supervised = train_features.dropna(subset=["dam_price_eur_mwh"]).copy()
    if len(supervised) < 96:
        raise ForecastingError("fewer than 96 priced training rows")

    return (
        columns,
        supervised[list(columns)],
        supervised["dam_price_eur_mwh"].astype(float),
        target_features[list(columns)],
    )


def _prediction_output(
    delivery_date: date,
    model_name: str,
    feature_set: str,
    dispatch_mode: str,
    target: pd.DataFrame,
    forecast_frame: pd.DataFrame,
    schedule: pd.DataFrame,
    interval_diagnostics: pd.DataFrame | None = None,
) -> pd.DataFrame:
    output = target[["timestamp", "interval", "dam_price_eur_mwh"]].copy()
    output.insert(0, "delivery_date", delivery_date.isoformat())
    output["model"] = model_name
    output["feature_set"] = feature_set
    output["dispatch_mode"] = dispatch_mode
    output = output.rename(columns={"dam_price_eur_mwh": "actual_price_eur_mwh"})
    output["forecast_price_eur_mwh"] = forecast_frame["forecast_price_eur_mwh"].to_numpy(float)
    schedule_cols = ["timestamp", "charge_mw", "discharge_mw", "net_power_mw", "soc_pct_end"]
    output = output.merge(schedule[schedule_cols], on="timestamp", how="left")
    if interval_diagnostics is not None and not interval_diagnostics.empty:
        output = output.merge(interval_diagnostics, on=["timestamp", "interval"], how="left")
    return output


def _normalize_history(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    required = {"timestamp", "interval", "dam_price_eur_mwh"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"history is missing required columns: {sorted(missing)}")
    output = frame.copy()
    output["timestamp"] = pd.to_datetime(output["timestamp"]).dt.tz_localize(None)
    output["interval"] = pd.to_numeric(output["interval"], errors="coerce").astype("Int64")
    output["dam_price_eur_mwh"] = pd.to_numeric(
        output["dam_price_eur_mwh"],
        errors="coerce",
    )
    return output.sort_values(["timestamp", "interval"]).reset_index(drop=True)


def _target_frame(frame: pd.DataFrame, delivery_date: date) -> pd.DataFrame:
    return frame[frame["timestamp"].dt.date == delivery_date].copy().reset_index(drop=True)


def _training_frame(
    frame: pd.DataFrame,
    delivery_date: date,
    drop_synthetic_training: bool,
) -> pd.DataFrame:
    train = frame[frame["timestamp"].dt.date < delivery_date].copy().reset_index(drop=True)
    if drop_synthetic_training and "data_quality" in train.columns:
        train = train[train["data_quality"] == "public price data"].copy()
    return train.reset_index(drop=True)


def _has_complete_target_prices(target: pd.DataFrame) -> bool:
    return bool(
        len(target) > 0
        and target["dam_price_eur_mwh"].notna().all()
        and target["interval"].nunique() == len(target)
    )


def _is_public_price_day(target: pd.DataFrame) -> bool:
    if "data_quality" not in target.columns:
        return True
    return bool((target["data_quality"] == "public price data").all())


def _priced_training_days(train: pd.DataFrame) -> int:
    if train.empty:
        return 0
    return int(train.dropna(subset=["dam_price_eur_mwh"])["timestamp"].dt.date.nunique())


def _available_training_dates(train: pd.DataFrame) -> list[date]:
    priced = train.dropna(subset=["dam_price_eur_mwh"])
    return sorted(priced["timestamp"].dt.date.unique())


def _model_daily_series(daily: pd.DataFrame, model_name: str) -> pd.DataFrame:
    required = {
        "delivery_date",
        "model",
        "realized_net_revenue_eur",
        "capture_ratio_vs_oracle",
    }
    missing = required - set(daily.columns)
    if missing:
        raise ValueError(f"daily results missing columns: {sorted(missing)}")
    model_daily = daily[daily["model"] == model_name].copy()
    if model_daily.empty:
        return pd.DataFrame(
            columns=["realized_net_revenue_eur", "capture_ratio_vs_oracle"],
            index=pd.Index([], name="delivery_date"),
        )
    return (
        model_daily[
            ["delivery_date", "realized_net_revenue_eur", "capture_ratio_vs_oracle"]
        ]
        .drop_duplicates(subset=["delivery_date"], keep="first")
        .set_index("delivery_date")
        .sort_index()
    )


def _filter_feature_columns(columns: tuple[str, ...], feature_set: str) -> tuple[str, ...]:
    allowed = FEATURE_SET_COLUMNS[feature_set]
    if allowed is None:
        return columns
    allowed_set = set(allowed)
    return tuple(column for column in columns if column in allowed_set)


def _diagnostic_float(
    interval_diagnostics: pd.DataFrame | None,
    column: str,
    reducer: str,
) -> float:
    if interval_diagnostics is None or interval_diagnostics.empty:
        return float("nan")
    if column not in interval_diagnostics.columns:
        return float("nan")
    values = pd.to_numeric(interval_diagnostics[column], errors="coerce").dropna()
    if values.empty:
        return float("nan")
    if reducer == "mean":
        return float(values.mean())
    if reducer == "max":
        return float(values.max())
    raise ValueError(f"Unsupported reducer: {reducer}")


def _uses_conservative_dispatch(model_name: str) -> bool:
    return model_name == "scarcity_ensemble_conservative"


def _base_forecast_model_name(model_name: str) -> str:
    if model_name == "scarcity_ensemble_conservative":
        return "scarcity_ensemble"
    return model_name


def _validate_model_candidates(model_candidates: Iterable[str]) -> None:
    supported = set(SUPPORTED_RESEARCH_MODEL_CANDIDATES)
    unknown = sorted(set(model_candidates) - supported)
    if unknown:
        raise ForecastingError(f"Unsupported research models: {unknown}")


def _validate_feature_set(feature_set: str) -> None:
    if feature_set not in FEATURE_SET_COLUMNS:
        raise ForecastingError(f"Unsupported feature set: {feature_set}")
