from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import requests

from . import synthetic
from .config import (
    GREEK_WEATHER_POINTS,
    HENEX_SUMMARY_URL,
    IPTO_FILE_API,
    MTUS_PER_DAY,
    RAW_DIR,
    ensure_data_dirs,
)


class DataSourceError(RuntimeError):
    """Raised when a public data source cannot be parsed."""


@dataclass
class MarketBundle:
    frame: pd.DataFrame
    sources: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _numeric_values(row: Iterable[object], limit: int = MTUS_PER_DAY) -> list[float]:
    values: list[float] = []
    for value in row:
        number = pd.to_numeric(value, errors="coerce")
        if pd.notna(number):
            values.append(float(number))
        if len(values) == limit:
            break
    return values


def _request_bytes(url: str, timeout: int = 25) -> bytes:
    response = requests.get(url, timeout=timeout, headers={"User-Agent": "ETW-Hackathon-BESS/1.0"})
    response.raise_for_status()
    content = response.content
    if not content.startswith(b"PK"):
        raise DataSourceError(f"URL did not return an xlsx workbook: {url}")
    return content


def _cache_file(kind: str, delivery_date: date, suffix: str) -> Path:
    ensure_data_dirs()
    return RAW_DIR / f"{delivery_date:%Y%m%d}_{kind}.{suffix}"


def parse_henex_results_summary(path: Path, delivery_date: date) -> pd.DataFrame:
    workbook = pd.ExcelFile(path)
    sheet_name = "SPOT_Summary (SELL)" if "SPOT_Summary (SELL)" in workbook.sheet_names else workbook.sheet_names[0]
    raw = pd.read_excel(path, sheet_name=sheet_name, header=None)

    price_values: list[float] | None = None
    for _, row in raw.iterrows():
        label = str(row.iloc[0]).lower()
        if "15min" in label and "mcp" in label:
            price_values = _numeric_values(row.iloc[1:], MTUS_PER_DAY)
            break

    if price_values is None or len(price_values) != MTUS_PER_DAY:
        raise DataSourceError(f"Could not find 96 15-minute MCP values in {path}")

    frame = synthetic.day_index(delivery_date)
    frame["dam_price_eur_mwh"] = price_values
    return frame


def fetch_henex_prices(delivery_date: date, max_version: int = 5) -> tuple[pd.DataFrame, str]:
    last_error: Exception | None = None
    for version in range(1, max_version + 1):
        url = HENEX_SUMMARY_URL.format(yyyymmdd=f"{delivery_date:%Y%m%d}", version=version)
        cache_path = _cache_file(f"henex_results_summary_v{version:02d}", delivery_date, "xlsx")
        try:
            if not cache_path.exists():
                cache_path.write_bytes(_request_bytes(url))
            return parse_henex_results_summary(cache_path, delivery_date), url
        except Exception as exc:  # noqa: BLE001 - we want to keep trying versions
            last_error = exc
            if cache_path.exists() and cache_path.stat().st_size < 1000:
                cache_path.unlink(missing_ok=True)
    raise DataSourceError(f"HEnEx DAM prices unavailable for {delivery_date}: {last_error}")


def _ipto_records(delivery_date: date, filetype: str) -> list[dict[str, object]]:
    url = IPTO_FILE_API.format(date_iso=delivery_date.isoformat(), filetype=filetype)
    response = requests.get(url, timeout=25, headers={"User-Agent": "ETW-Hackathon-BESS/1.0"})
    response.raise_for_status()
    records = response.json()
    if not isinstance(records, list):
        raise DataSourceError(f"Unexpected IPTO response for {filetype}: {response.text[:200]}")
    return records


def parse_ipto_forecast(path: Path, delivery_date: date, column_name: str) -> pd.DataFrame:
    raw = pd.read_excel(path, header=None)
    best: list[float] | None = None

    for _, row in raw.iterrows():
        label = " ".join(str(value).lower() for value in row.iloc[:4].dropna())
        if "forecast" not in label:
            continue
        values = _numeric_values(row.iloc[1:], MTUS_PER_DAY)
        if len(values) == MTUS_PER_DAY:
            best = values
            break

    if best is None:
        for _, row in raw.iterrows():
            values = _numeric_values(row.iloc[1:], MTUS_PER_DAY)
            if len(values) == MTUS_PER_DAY and values != list(range(1, MTUS_PER_DAY + 1)):
                best = values
                break

    if best is None:
        raise DataSourceError(f"Could not find 96 forecast values in {path}")

    frame = synthetic.day_index(delivery_date)
    frame[column_name] = best
    return frame


def fetch_ipto_forecast(
    delivery_date: date,
    filetype: str,
    column_name: str,
) -> tuple[pd.DataFrame, str]:
    records = _ipto_records(delivery_date, filetype)
    if not records:
        raise DataSourceError(f"No IPTO records for {filetype} on {delivery_date}")

    record = records[0]
    url = str(record.get("file_path", ""))
    if not url:
        raise DataSourceError(f"IPTO record for {filetype} does not contain file_path")
    cache_path = _cache_file(filetype, delivery_date, "xlsx")
    if not cache_path.exists():
        cache_path.write_bytes(_request_bytes(url))
    return parse_ipto_forecast(cache_path, delivery_date, column_name), url


def _open_meteo_url(delivery_date: date, latitude: float, longitude: float, host: str) -> str:
    variables = ",".join(
        [
            "temperature_2m",
            "cloud_cover",
            "wind_speed_10m",
            "shortwave_radiation",
        ]
    )
    return (
        f"https://{host}/v1/forecast"
        f"?latitude={latitude:.4f}&longitude={longitude:.4f}"
        f"&hourly={variables}"
        f"&start_date={delivery_date.isoformat()}&end_date={delivery_date.isoformat()}"
        "&timezone=Europe%2FAthens"
    )


def fetch_open_meteo_weather(delivery_date: date) -> tuple[pd.DataFrame, str]:
    frames: list[pd.DataFrame] = []
    used_urls: list[str] = []
    hosts = ["api.open-meteo.com", "historical-forecast-api.open-meteo.com"]

    for name, (latitude, longitude) in GREEK_WEATHER_POINTS.items():
        payload: dict[str, object] | None = None
        url_used = ""
        for host in hosts:
            url = _open_meteo_url(delivery_date, latitude, longitude, host)
            try:
                response = requests.get(url, timeout=25)
                response.raise_for_status()
                candidate = response.json()
                if candidate.get("hourly", {}).get("time"):
                    payload = candidate
                    url_used = url
                    break
            except Exception:
                continue
        if payload is None:
            continue

        hourly = pd.DataFrame(payload["hourly"])
        hourly["timestamp"] = pd.to_datetime(hourly["time"]).dt.tz_localize(None)
        hourly = hourly.drop(columns=["time"]).set_index("timestamp").sort_index()
        hourly = hourly.apply(pd.to_numeric, errors="coerce")
        quarter_hour = hourly.resample("15min").interpolate("time").iloc[:MTUS_PER_DAY]
        quarter_hour["weather_point"] = name
        frames.append(quarter_hour.reset_index())
        used_urls.append(url_used)

    if not frames:
        raise DataSourceError(f"Open-Meteo weather unavailable for {delivery_date}")

    merged = pd.concat(frames, ignore_index=True)
    numeric_cols = [
        "temperature_2m",
        "cloud_cover",
        "wind_speed_10m",
        "shortwave_radiation",
    ]
    aggregated = merged.groupby("timestamp", as_index=False)[numeric_cols].mean()
    day = synthetic.day_index(delivery_date)
    output = day.merge(aggregated, on="timestamp", how="left")
    output[numeric_cols] = output[numeric_cols].interpolate().ffill().bfill()
    return output, json.dumps(used_urls[:2])


def load_market_bundle(delivery_date: date, allow_synthetic: bool = True) -> MarketBundle:
    """Load public data and fall back by column, keeping the demo usable."""
    base = synthetic.day_index(delivery_date)
    sources: dict[str, str] = {}
    warnings: list[str] = []

    try:
        prices, source = fetch_henex_prices(delivery_date)
        base = base.merge(prices, on=["timestamp", "interval"], how="left")
        sources["DAM prices"] = source
    except Exception as exc:  # noqa: BLE001
        warnings.append(str(exc))

    for filetype, column in [
        ("ISP1DayAheadLoadForecast", "load_forecast_mw"),
        ("ISP1DayAheadRESForecast", "res_forecast_mw"),
    ]:
        try:
            forecast, source = fetch_ipto_forecast(delivery_date, filetype, column)
            base = base.merge(forecast, on=["timestamp", "interval"], how="left")
            sources[column] = source
        except Exception as exc:  # noqa: BLE001
            warnings.append(str(exc))

    try:
        weather, source = fetch_open_meteo_weather(delivery_date)
        base = base.merge(weather, on=["timestamp", "interval"], how="left")
        sources["weather"] = source
    except Exception as exc:  # noqa: BLE001
        warnings.append(str(exc))

    fallback = synthetic.synthetic_market_day(delivery_date)
    for column in fallback.columns:
        if column in ("timestamp", "interval"):
            continue
        if column not in base.columns:
            base[column] = fallback[column]
        else:
            base[column] = base[column].fillna(fallback[column])

    missing_price = "DAM prices" not in sources
    if missing_price and not allow_synthetic:
        raise DataSourceError("DAM prices unavailable and synthetic fallback disabled")

    base["data_quality"] = np.where(
        missing_price,
        "synthetic price fallback",
        "public price data",
    )
    if missing_price:
        sources["DAM prices"] = "Synthetic fallback generated from Greek load/RES price shape"

    return MarketBundle(frame=base, sources=sources, warnings=warnings)
