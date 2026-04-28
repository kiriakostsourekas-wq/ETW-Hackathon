from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


FEATURE_COLUMNS = [
    "load_forecast_mw",
    "res_forecast_mw",
    "shortwave_radiation",
    "cloud_cover",
    "temperature_2m",
    "wind_speed_10m",
]


def add_calendar_features(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    hour = output["timestamp"].dt.hour + output["timestamp"].dt.minute / 60.0
    output["hour_sin"] = np.sin(2 * np.pi * hour / 24.0)
    output["hour_cos"] = np.cos(2 * np.pi * hour / 24.0)
    output["is_weekend"] = output["timestamp"].dt.dayofweek.isin([5, 6]).astype(int)
    output["net_load_forecast_mw"] = output["load_forecast_mw"] - output["res_forecast_mw"]
    return output


def structural_price_forecast(frame: pd.DataFrame) -> pd.Series:
    """Transparent fallback forecast for presentation and scenario work."""
    features = add_calendar_features(frame)
    net_load = _zscore(features["net_load_forecast_mw"])
    solar = _zscore(features["shortwave_radiation"])
    cloud = _zscore(features["cloud_cover"])
    evening = np.exp(-0.5 * ((features["timestamp"].dt.hour + features["timestamp"].dt.minute / 60 - 20) / 2.0) ** 2)
    baseline = features["dam_price_eur_mwh"].rolling(8, min_periods=1, center=True).mean()
    forecast = baseline + 12 * net_load - 7 * solar + 3 * cloud + 18 * evening
    return forecast.clip(lower=-50).rename("forecast_price_eur_mwh")


def fit_ridge_forecast(history: pd.DataFrame, target: pd.DataFrame) -> pd.Series:
    """Train an explainable ridge model when enough historical rows are available."""
    train = add_calendar_features(history).dropna(subset=["dam_price_eur_mwh"])
    target_features = add_calendar_features(target)
    columns = FEATURE_COLUMNS + ["hour_sin", "hour_cos", "is_weekend", "net_load_forecast_mw"]
    train = train.dropna(subset=columns)
    target_features = target_features.dropna(subset=columns)
    if len(train) < 7 * 96 or target_features.empty:
        return structural_price_forecast(target)

    model = make_pipeline(StandardScaler(), RidgeCV(alphas=[0.1, 1.0, 10.0, 50.0]))
    model.fit(train[columns], train["dam_price_eur_mwh"])
    prediction = pd.Series(
        model.predict(add_calendar_features(target)[columns]),
        index=target.index,
        name="forecast_price_eur_mwh",
    )
    return prediction


def _zscore(series: pd.Series) -> pd.Series:
    std = series.std()
    if std == 0 or pd.isna(std):
        return series * 0
    return (series - series.mean()) / std
