from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import RidgeCV
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


class ForecastingError(ValueError):
    """Raised when a forecast would use unavailable or leaking features."""


@dataclass(frozen=True)
class ForecastOutput:
    frame: pd.DataFrame
    selected_model: str
    feature_columns: tuple[str, ...]
    diagnostics: dict[str, float | str]


BASE_SIGNAL_COLUMNS = [
    "load_forecast_mw",
    "res_forecast_mw",
    "shortwave_radiation",
    "cloud_cover",
    "temperature_2m",
    "wind_speed_10m",
]

LIVE_FEATURE_TIMING = {
    "load_forecast_mw": "ex_ante",
    "res_forecast_mw": "ex_ante",
    "shortwave_radiation": "ex_ante",
    "cloud_cover": "ex_ante",
    "temperature_2m": "ex_ante",
    "wind_speed_10m": "ex_ante",
    "dispatchable_availability_mw": "ex_ante",
    "atc_import_export_mw": "ex_ante",
    "hydro_flexibility_index": "ex_ante",
    "ttf_gas_eur_mwh": "ex_ante",
    "eua_eur_tonne": "ex_ante",
    "entsoe_system_context_index": "ex_ante",
    "hour_sin": "ex_ante",
    "hour_cos": "ex_ante",
    "is_weekend": "ex_ante",
    "net_load_forecast_mw": "ex_ante",
    "res_share_forecast": "ex_ante",
    "evening_peak": "ex_ante",
    "solar_peak": "ex_ante",
    "dam_price_eur_mwh": "post_clearing",
    "bg_dam_price_eur_mwh": "post_clearing",
    "it_dam_price_eur_mwh": "post_clearing",
    "curve_slope_eur_mwh_per_mw": "post_clearing",
    "energy_surplus_mw": "post_clearing",
    "actual_load_mw": "actual",
    "actual_res_mw": "actual",
    "actual_import_export_mw": "actual",
}

LIVE_SAFE_TIMING = {"ex_ante", "planning"}
MODEL_MIN_ROWS = 7 * 96
NONLINEAR_MIN_ROWS = 14 * 96


def add_calendar_features(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    hour = output["timestamp"].dt.hour + output["timestamp"].dt.minute / 60.0
    output["hour_sin"] = np.sin(2 * np.pi * hour / 24.0)
    output["hour_cos"] = np.cos(2 * np.pi * hour / 24.0)
    output["is_weekend"] = output["timestamp"].dt.dayofweek.isin([5, 6]).astype(int)
    output["evening_peak"] = np.exp(-0.5 * ((hour - 20.0) / 2.0) ** 2)
    output["solar_peak"] = np.exp(-0.5 * ((hour - 13.0) / 3.0) ** 2)
    if {"load_forecast_mw", "res_forecast_mw"}.issubset(output.columns):
        output["net_load_forecast_mw"] = output["load_forecast_mw"] - output["res_forecast_mw"]
        output["res_share_forecast"] = (
            output["res_forecast_mw"] / output["load_forecast_mw"].replace(0, np.nan)
        )
    return output


def assert_live_feature_columns(feature_columns: list[str] | tuple[str, ...]) -> None:
    blocked = [
        column
        for column in feature_columns
        if LIVE_FEATURE_TIMING.get(column, "ex_ante") not in LIVE_SAFE_TIMING
    ]
    if blocked:
        raise ForecastingError(
            f"Live forecast cannot use post-clearing or actual columns: {blocked}"
        )


def candidate_feature_columns(frame: pd.DataFrame, live: bool = True) -> tuple[str, ...]:
    features = add_calendar_features(frame)
    columns = [
        column
        for column in (
            BASE_SIGNAL_COLUMNS
            + [
                "dispatchable_availability_mw",
                "atc_import_export_mw",
                "hydro_flexibility_index",
                "ttf_gas_eur_mwh",
                "eua_eur_tonne",
                "entsoe_system_context_index",
                "hour_sin",
                "hour_cos",
                "is_weekend",
                "net_load_forecast_mw",
                "res_share_forecast",
                "evening_peak",
                "solar_peak",
            ]
        )
        if column in features.columns
    ]
    if live:
        assert_live_feature_columns(columns)
    return tuple(columns)


def structural_price_forecast(frame: pd.DataFrame) -> pd.Series:
    """Transparent live-safe fallback forecast for presentation and scenario work."""
    features = add_calendar_features(frame)
    net_load = _zscore(features.get("net_load_forecast_mw", pd.Series(0, index=features.index)))
    solar = _zscore(features.get("shortwave_radiation", pd.Series(0, index=features.index)))
    cloud = _zscore(features.get("cloud_cover", pd.Series(0, index=features.index)))
    wind = _zscore(features.get("wind_speed_10m", pd.Series(0, index=features.index)))
    temperature = _zscore(features.get("temperature_2m", pd.Series(0, index=features.index)))

    forecast = (
        92.0
        + 17.0 * net_load
        - 12.0 * solar
        + 4.0 * cloud
        - 4.0 * wind
        + 3.0 * temperature.abs()
        + 24.0 * features["evening_peak"]
        - 4.0 * features["is_weekend"]
    )
    return forecast.clip(lower=-50).rename("forecast_price_eur_mwh")


def price_shape_baseline_forecast(history: pd.DataFrame, target: pd.DataFrame) -> pd.Series:
    train = _priced_history(history)
    target_features = add_calendar_features(target)
    if train.empty or "interval" not in train or "interval" not in target_features:
        return structural_price_forecast(target)

    weekend_profile = train.groupby(["is_weekend", "interval"])["dam_price_eur_mwh"].mean()
    interval_profile = train.groupby("interval")["dam_price_eur_mwh"].mean()
    fallback = float(train["dam_price_eur_mwh"].tail(min(len(train), 7 * 96)).mean())

    predictions: list[float] = []
    for _, row in target_features.iterrows():
        key = (int(row["is_weekend"]), int(row["interval"]))
        if key in weekend_profile.index:
            predictions.append(float(weekend_profile.loc[key]))
        elif int(row["interval"]) in interval_profile.index:
            predictions.append(float(interval_profile.loc[int(row["interval"])]))
        else:
            predictions.append(fallback)

    output = pd.Series(predictions, index=target.index, name="forecast_price_eur_mwh")
    if (
        "net_load_forecast_mw" in train.columns
        and "net_load_forecast_mw" in target_features.columns
    ):
        historical_net = train.groupby("interval")["net_load_forecast_mw"].mean()
        target_net = target_features["interval"].map(historical_net)
        net_delta = _zscore(target_features["net_load_forecast_mw"] - target_net)
        output = output + 8.0 * net_delta.fillna(0)
    return output.clip(lower=-50).rename("forecast_price_eur_mwh")


def fit_ridge_forecast(history: pd.DataFrame, target: pd.DataFrame) -> pd.Series:
    """Train an explainable ridge model when enough historical rows are available."""
    train = _priced_history(history)
    target_features = add_calendar_features(target)
    columns = [
        column
        for column in candidate_feature_columns(target_features)
        if column in train.columns and column in target_features.columns
    ]
    assert_live_feature_columns(columns)
    if not columns:
        return price_shape_baseline_forecast(history, target)

    train = train.dropna(subset=columns)
    target_clean = target_features.dropna(subset=columns)
    if len(train) < 7 * 96 or target_clean.empty:
        return price_shape_baseline_forecast(history, target)

    model = make_pipeline(StandardScaler(), RidgeCV(alphas=[0.1, 1.0, 10.0, 50.0]))
    model.fit(train[columns], train["dam_price_eur_mwh"])
    prediction = price_shape_baseline_forecast(history, target)
    prediction.loc[target_clean.index] = model.predict(target_clean[columns])
    return prediction


def fit_nonlinear_challenger(history: pd.DataFrame, target: pd.DataFrame) -> pd.Series:
    train = _priced_history(history)
    target_features = add_calendar_features(target)
    columns = [
        column
        for column in candidate_feature_columns(target_features)
        if column in train.columns and column in target_features.columns
    ]
    assert_live_feature_columns(columns)
    if len(train.dropna(subset=columns)) < NONLINEAR_MIN_ROWS or not columns:
        return fit_ridge_forecast(history, target)

    train = train.dropna(subset=columns)
    model = HistGradientBoostingRegressor(
        max_iter=160,
        learning_rate=0.06,
        l2_regularization=0.2,
        random_state=42,
    )
    model.fit(train[columns], train["dam_price_eur_mwh"])
    target_clean = target_features.dropna(subset=columns)
    prediction = fit_ridge_forecast(history, target)
    if not target_clean.empty:
        prediction.loc[target_clean.index] = model.predict(target_clean[columns])
    return prediction.clip(lower=-50)


def forecast_price_with_uncertainty(history: pd.DataFrame, target: pd.DataFrame) -> ForecastOutput:
    target_features = add_calendar_features(target)
    columns = candidate_feature_columns(target_features)
    train = _priced_history(history)
    if len(train) >= NONLINEAR_MIN_ROWS:
        forecast = fit_nonlinear_challenger(history, target)
        selected_model = "hist_gradient_boosting"
    elif len(train) >= MODEL_MIN_ROWS:
        forecast = fit_ridge_forecast(history, target)
        selected_model = "ridge"
    elif not train.empty:
        forecast = price_shape_baseline_forecast(history, target)
        selected_model = "interval_profile"
    else:
        forecast = structural_price_forecast(target)
        selected_model = "structural_proxy"

    residual_width = _forecast_uncertainty_width(history, forecast)
    frame = target.copy()
    frame["forecast_price_eur_mwh"] = forecast.to_numpy(float)
    frame["forecast_low_eur_mwh"] = (forecast - residual_width).clip(lower=-75).to_numpy(float)
    frame["forecast_high_eur_mwh"] = (forecast + residual_width).to_numpy(float)
    frame["forecast_model"] = selected_model
    diagnostics: dict[str, float | str] = {
        "selected_model": selected_model,
        "uncertainty_width_eur_mwh": float(residual_width),
    }
    return ForecastOutput(
        frame=frame,
        selected_model=selected_model,
        feature_columns=columns,
        diagnostics=diagnostics,
    )


def forecast_quality_metrics(actual: pd.Series, predicted: pd.Series) -> dict[str, float]:
    aligned = pd.DataFrame({"actual": actual, "predicted": predicted}).dropna()
    if aligned.empty:
        return {
            "mae_eur_mwh": float("nan"),
            "rmse_eur_mwh": float("nan"),
            "spread_direction_accuracy": float("nan"),
            "top_quartile_accuracy": float("nan"),
            "bottom_quartile_accuracy": float("nan"),
        }

    error = aligned["predicted"] - aligned["actual"]
    actual_centered = aligned["actual"] - aligned["actual"].median()
    predicted_centered = aligned["predicted"] - aligned["predicted"].median()
    actual_top = aligned["actual"] >= aligned["actual"].quantile(0.75)
    predicted_top = aligned["predicted"] >= aligned["predicted"].quantile(0.75)
    actual_bottom = aligned["actual"] <= aligned["actual"].quantile(0.25)
    predicted_bottom = aligned["predicted"] <= aligned["predicted"].quantile(0.25)

    return {
        "mae_eur_mwh": float(error.abs().mean()),
        "rmse_eur_mwh": float(np.sqrt(np.square(error).mean())),
        "spread_direction_accuracy": float(
            (np.sign(actual_centered) == np.sign(predicted_centered)).mean()
        ),
        "top_quartile_accuracy": float((actual_top == predicted_top).mean()),
        "bottom_quartile_accuracy": float((actual_bottom == predicted_bottom).mean()),
    }


def walk_forward_forecast_backtest(
    history: pd.DataFrame,
    min_train_days: int = 7,
    max_test_days: int | None = None,
) -> pd.DataFrame:
    frame = history.copy()
    frame["delivery_date"] = frame["timestamp"].dt.date
    dates = sorted(frame["delivery_date"].unique())
    rows: list[dict[str, float | str]] = []
    test_dates = dates[min_train_days:]
    if max_test_days is not None:
        test_dates = test_dates[:max_test_days]

    for delivery_date in test_dates:
        train = frame[frame["delivery_date"] < delivery_date].drop(columns=["delivery_date"])
        target = frame[frame["delivery_date"] == delivery_date].drop(columns=["delivery_date"])
        forecast = forecast_price_with_uncertainty(train, target).frame
        metrics = forecast_quality_metrics(
            target["dam_price_eur_mwh"],
            forecast["forecast_price_eur_mwh"],
        )
        rows.append(
            {
                "delivery_date": delivery_date.isoformat(),
                "train_until": max(train["timestamp"]).date().isoformat(),
                **metrics,
            }
        )
    return pd.DataFrame(rows)


def _zscore(series: pd.Series) -> pd.Series:
    std = series.std()
    if std == 0 or pd.isna(std):
        return series * 0
    return (series - series.mean()) / std


def _forecast_uncertainty_width(history: pd.DataFrame, forecast: pd.Series) -> float:
    train = _priced_history(history)
    if train.empty:
        return 22.0
    if "interval" not in train:
        return max(15.0, float(train["dam_price_eur_mwh"].std()))
    profile = train.groupby("interval")["dam_price_eur_mwh"].transform("mean")
    residuals = (train["dam_price_eur_mwh"] - profile).abs().dropna()
    if residuals.empty:
        return max(15.0, float(forecast.std()))
    return float(max(12.0, residuals.quantile(0.8)))


def _priced_history(history: pd.DataFrame) -> pd.DataFrame:
    if history.empty or "timestamp" not in history or "dam_price_eur_mwh" not in history:
        return pd.DataFrame()
    return add_calendar_features(history).dropna(subset=["dam_price_eur_mwh"])
