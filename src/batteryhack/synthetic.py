from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from .config import MTUS_PER_DAY


def day_index(delivery_date: date) -> pd.DataFrame:
    timestamps = pd.date_range(
        pd.Timestamp(delivery_date),
        periods=MTUS_PER_DAY,
        freq="15min",
    )
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "interval": np.arange(1, MTUS_PER_DAY + 1),
        }
    )


def synthetic_market_day(delivery_date: date) -> pd.DataFrame:
    """Create a deterministic Greek-market-like 15-minute day for demos/tests."""
    seed = int(pd.Timestamp(delivery_date).strftime("%Y%m%d"))
    rng = np.random.default_rng(seed)
    df = day_index(delivery_date)
    hour = (
        df["timestamp"].dt.hour
        + df["timestamp"].dt.minute / 60.0
    ).to_numpy()

    solar_shape = np.exp(-0.5 * ((hour - 13.0) / 3.0) ** 2)
    evening_peak = np.exp(-0.5 * ((hour - 20.0) / 1.8) ** 2)
    morning_peak = np.exp(-0.5 * ((hour - 8.0) / 2.0) ** 2)
    night_support = np.exp(-0.5 * ((hour - 2.0) / 2.2) ** 2)
    wind_shape = 0.5 + 0.25 * np.sin((hour + 3.0) / 24.0 * 2 * np.pi)

    res_forecast_mw = 1500 + 4100 * solar_shape + 650 * wind_shape
    load_forecast_mw = 4200 + 650 * morning_peak + 1450 * evening_peak + 200 * night_support
    shortwave_radiation = 860 * solar_shape
    cloud_cover = np.clip(45 - 30 * solar_shape + rng.normal(0, 5, MTUS_PER_DAY), 0, 100)
    temperature_2m = 15 + 7 * np.sin((hour - 7.0) / 24.0 * 2 * np.pi)
    wind_speed_10m = 18 + 7 * wind_shape + rng.normal(0, 0.8, MTUS_PER_DAY)

    net_tightness = (load_forecast_mw - res_forecast_mw) / 1000.0
    dam_price = (
        88
        + 28 * morning_peak
        + 94 * evening_peak
        + 23 * net_tightness
        - 64 * solar_shape
        + rng.normal(0, 4.0, MTUS_PER_DAY)
    )
    dam_price = np.clip(dam_price, -20, 330)

    df["dam_price_eur_mwh"] = dam_price.round(2)
    df["load_forecast_mw"] = load_forecast_mw.round(1)
    df["res_forecast_mw"] = res_forecast_mw.round(1)
    df["shortwave_radiation"] = shortwave_radiation.round(1)
    df["cloud_cover"] = cloud_cover.round(1)
    df["temperature_2m"] = temperature_2m.round(1)
    df["wind_speed_10m"] = wind_speed_10m.round(1)
    df["data_quality"] = "synthetic fallback"
    return df
