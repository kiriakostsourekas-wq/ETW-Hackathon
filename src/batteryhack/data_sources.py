from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin

import numpy as np
import pandas as pd
import requests

from . import synthetic
from .config import (
    GREEK_WEATHER_POINTS,
    HENEX_DAM_PUBLICATIONS_URL,
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


def _request_raw_bytes(url: str, timeout: int = 25) -> bytes:
    response = requests.get(url, timeout=timeout, headers={"User-Agent": "ETW-Hackathon-BESS/1.0"})
    response.raise_for_status()
    return response.content


def _cache_file(kind: str, delivery_date: date, suffix: str) -> Path:
    ensure_data_dirs()
    return RAW_DIR / f"{delivery_date:%Y%m%d}_{kind}.{suffix}"


def _expand_hourly_to_quarter_hour(values: Iterable[float]) -> list[float]:
    hourly = [float(value) for value in values]
    if len(hourly) != 24:
        raise DataSourceError(f"Expected 24 hourly values, got {len(hourly)}")
    return [value for value in hourly for _ in range(4)]


def parse_henex_results_summary(path: Path, delivery_date: date) -> pd.DataFrame:
    workbook = pd.ExcelFile(path)
    sheet_name = (
        "SPOT_Summary (SELL)"
        if "SPOT_Summary (SELL)" in workbook.sheet_names
        else workbook.sheet_names[0]
    )
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


def fetch_henex_publication_file(
    delivery_date: date,
    publication_kind: str,
    max_version: int = 3,
) -> tuple[Path, str]:
    """Fetch HEnEx DAM workbooks that are exposed through Liferay UUID links."""
    last_error: Exception | None = None
    page_text: str | None = None
    for version in range(1, max_version + 1):
        filename = f"{delivery_date:%Y%m%d}_EL-DAM_{publication_kind}_EN_v{version:02d}.xlsx"
        cache_path = _cache_file(
            f"henex_{publication_kind.lower()}_v{version:02d}",
            delivery_date,
            "xlsx",
        )
        if cache_path.exists():
            return cache_path, str(cache_path)

        try:
            if page_text is None:
                page_text = requests.get(
                    HENEX_DAM_PUBLICATIONS_URL,
                    timeout=30,
                    headers={"User-Agent": "ETW-Hackathon-BESS/1.0"},
                ).text
            pattern = (
                r'href="([^"]+)"[^>]*>\s*(?:<i[^>]*></i>)?\s*(?:&nbsp;|\xa0|\s)*'
                + re.escape(filename)
            )
            match = re.search(pattern, page_text)
            if not match:
                last_error = DataSourceError(f"{filename} not listed on HEnEx DAM page")
                continue
            url = urljoin(HENEX_DAM_PUBLICATIONS_URL, match.group(1).replace("&amp;", "&"))
            cache_path.write_bytes(_request_bytes(url))
            return cache_path, url
        except Exception as exc:  # noqa: BLE001 - try all versions before failing
            last_error = exc
            if cache_path.exists() and cache_path.stat().st_size < 1000:
                cache_path.unlink(missing_ok=True)
    raise DataSourceError(
        f"HEnEx {publication_kind} unavailable for {delivery_date}: {last_error}"
    )


def _quarter_hour_values_from_row(row: pd.Series, start_index: int = 1) -> list[float]:
    values: list[float] = []
    for value in row.iloc[start_index:]:
        number = pd.to_numeric(value, errors="coerce")
        if pd.notna(number):
            values.append(float(number))
        if len(values) == MTUS_PER_DAY:
            break
    return values


def parse_henex_pre_market_summary(path: Path, delivery_date: date) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name=0, header=None)
    row_map = {
        "GAS": "premarket_gas_mw",
        "HYDRO": "premarket_hydro_mw",
        "RENEWABLES": "premarket_renewables_mw",
        "LIGNITE": "premarket_lignite_mw",
        "BESS": None,
        "PRODUCTION": "premarket_production_mw",
        "DEMAND": "premarket_demand_mw",
        "TOTAL IMPORTS": "premarket_imports_mw",
        "TOTAL EXPORTS": "premarket_exports_mw",
    }
    values_by_column: dict[str, list[float]] = {}
    seen_bess = 0
    for _, row in raw.iterrows():
        label = str(row.iloc[0]).strip()
        if label == "BESS":
            seen_bess += 1
            column = (
                "premarket_bess_production_mw"
                if seen_bess == 1
                else "premarket_bess_demand_mw"
            )
        else:
            column = row_map.get(label)
        if column is None:
            continue
        values = _quarter_hour_values_from_row(row)
        if len(values) == MTUS_PER_DAY:
            values_by_column[column] = values

    buy_sell_rows = raw[raw.iloc[:, 0].astype(str).str.strip().eq("Greece Mainland")]
    if len(buy_sell_rows) >= 2:
        buy_values = _quarter_hour_values_from_row(buy_sell_rows.iloc[0])
        sell_values = _quarter_hour_values_from_row(buy_sell_rows.iloc[1])
        if len(buy_values) == MTUS_PER_DAY and len(sell_values) == MTUS_PER_DAY:
            values_by_column["premarket_buy_nomination_mw"] = buy_values
            values_by_column["premarket_sell_nomination_mw"] = sell_values

    if not values_by_column:
        raise DataSourceError(f"Could not parse HEnEx pre-market summary features in {path}")

    frame = synthetic.day_index(delivery_date)
    for column, values in values_by_column.items():
        frame[column] = values
    if {"premarket_sell_nomination_mw", "premarket_buy_nomination_mw"}.issubset(frame.columns):
        frame["premarket_net_sell_nomination_mw"] = (
            frame["premarket_sell_nomination_mw"] - frame["premarket_buy_nomination_mw"]
        )
    if {"premarket_imports_mw", "premarket_exports_mw"}.issubset(frame.columns):
        frame["premarket_net_imports_mw"] = (
            frame["premarket_imports_mw"] - frame["premarket_exports_mw"]
        )
    return frame


def fetch_henex_pre_market_summary(delivery_date: date) -> tuple[pd.DataFrame, str]:
    path, source = fetch_henex_publication_file(delivery_date, "PreMarketSummary")
    return parse_henex_pre_market_summary(path, delivery_date), source


def parse_henex_posnoms(path: Path, delivery_date: date) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name=0)
    required = {"SIDE_DESCR", "DELIVERY_MTU", "TOTAL_ORDERS"}
    if not required.issubset(raw.columns):
        raise DataSourceError(f"HEnEx POSNOMs missing columns: {required - set(raw.columns)}")

    raw = raw.copy()
    raw["timestamp"] = pd.to_datetime(raw["DELIVERY_MTU"]).dt.tz_localize(None)
    raw["orders"] = pd.to_numeric(raw["TOTAL_ORDERS"], errors="coerce").fillna(0.0)
    pivot = raw.pivot_table(
        index="timestamp",
        columns=raw["SIDE_DESCR"].astype(str).str.lower(),
        values="orders",
        aggfunc="sum",
        fill_value=0.0,
    ).reset_index()
    frame = synthetic.day_index(delivery_date).merge(pivot, on="timestamp", how="left")
    frame["posnom_buy_mw"] = frame.get("buy", 0.0)
    frame["posnom_sell_mw"] = frame.get("sell", 0.0)
    frame["posnom_net_sell_mw"] = frame["posnom_sell_mw"] - frame["posnom_buy_mw"]
    return frame[["timestamp", "interval", "posnom_buy_mw", "posnom_sell_mw", "posnom_net_sell_mw"]]


def fetch_henex_posnoms(delivery_date: date) -> tuple[pd.DataFrame, str]:
    path, source = fetch_henex_publication_file(delivery_date, "POSNOMs")
    return parse_henex_posnoms(path, delivery_date), source


def _ipto_records(delivery_date: date, filetype: str) -> list[dict[str, object]]:
    url = IPTO_FILE_API.format(date_iso=delivery_date.isoformat(), filetype=filetype)
    response = requests.get(url, timeout=25, headers={"User-Agent": "ETW-Hackathon-BESS/1.0"})
    response.raise_for_status()
    records = response.json()
    if not isinstance(records, list):
        raise DataSourceError(f"Unexpected IPTO response for {filetype}: {response.text[:200]}")
    return records


def _record_extension(record: dict[str, object], default: str = "xlsx") -> str:
    url = str(record.get("file_path", ""))
    suffix = Path(url.split("?")[0]).suffix.lower().lstrip(".")
    return suffix or default


def _fetch_ipto_file(
    delivery_date: date,
    filetype: str,
    record_index: int = 0,
) -> tuple[Path, str, dict[str, object]]:
    records = _ipto_records(delivery_date, filetype)
    if not records:
        raise DataSourceError(f"No IPTO records for {filetype} on {delivery_date}")
    if record_index >= len(records):
        raise DataSourceError(
            f"IPTO has only {len(records)} records for {filetype} on {delivery_date}"
        )
    record = records[record_index]
    url = str(record.get("file_path", ""))
    if not url:
        raise DataSourceError(f"IPTO record for {filetype} does not contain file_path")
    suffix = _record_extension(record)
    cache_path = _cache_file(f"{filetype}_{record_index + 1:02d}", delivery_date, suffix)
    if not cache_path.exists():
        content = _request_bytes(url) if suffix == "xlsx" else _request_raw_bytes(url)
        cache_path.write_bytes(content)
    return cache_path, url, record


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
    cache_path, url, _ = _fetch_ipto_file(delivery_date, filetype)
    return parse_ipto_forecast(cache_path, delivery_date, column_name), url


def parse_ipto_unit_availability(path: Path, delivery_date: date) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name=0, header=None)
    numeric = raw.iloc[:, 3].apply(pd.to_numeric, errors="coerce")
    availability = float(numeric.dropna().sum())
    frame = synthetic.day_index(delivery_date)
    frame["dispatchable_availability_mw"] = availability
    return frame


def fetch_ipto_unit_availability(delivery_date: date) -> tuple[pd.DataFrame, str]:
    path, source, _ = _fetch_ipto_file(delivery_date, "ISP1UnitAvailabilities")
    return parse_ipto_unit_availability(path, delivery_date), source


def _parse_hourly_table_sum(path: Path) -> list[float]:
    raw = pd.read_excel(path, sheet_name=0, header=None)
    rows: list[float] = []
    for _, row in raw.iterrows():
        hour = pd.to_numeric(row.iloc[0], errors="coerce")
        if pd.isna(hour) or not 1 <= int(hour) <= 24:
            continue
        values = pd.to_numeric(row.iloc[1:], errors="coerce")
        rows.append(float(values.dropna().sum()))
        if len(rows) == 24:
            break
    if len(rows) != 24:
        raise DataSourceError(f"Could not parse 24 hourly values from {path}")
    return rows


def fetch_ipto_atc(delivery_date: date) -> tuple[pd.DataFrame, str]:
    records = _ipto_records(delivery_date, "DailyAuctionsSpecificationsATC")
    if not records:
        raise DataSourceError(f"No IPTO ATC records on {delivery_date}")

    hourly_import = [0.0] * 24
    hourly_export = [0.0] * 24
    sources: list[str] = []
    for index, record in enumerate(records):
        path, source, record = _fetch_ipto_file(
            delivery_date,
            "DailyAuctionsSpecificationsATC",
            record_index=index,
        )
        description = str(record.get("file_description", "")).upper()
        values = _parse_hourly_table_sum(path)
        if "IMP" in description:
            hourly_import = values
        elif "EXP" in description:
            hourly_export = values
        sources.append(source)

    frame = synthetic.day_index(delivery_date)
    frame["atc_import_mw"] = _expand_hourly_to_quarter_hour(hourly_import)
    frame["atc_export_mw"] = _expand_hourly_to_quarter_hour(hourly_export)
    frame["atc_import_export_mw"] = frame["atc_import_mw"] - frame["atc_export_mw"]
    return frame, json.dumps(sources)


def parse_ipto_long_term_nominations(path: Path, delivery_date: date) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name=0, header=None)
    import_hourly = np.zeros(24)
    export_hourly = np.zeros(24)
    for _, row in raw.iterrows():
        side = str(row.iloc[0]).strip().upper()
        if side not in {"IMPORTS", "EXPORTS"}:
            continue
        area = str(row.iloc[2]).strip().upper()
        if area == "SUM":
            continue
        values = pd.to_numeric(row.iloc[3:27], errors="coerce").fillna(0.0).to_numpy(float)
        if len(values) != 24:
            continue
        if side == "IMPORTS":
            import_hourly += values
        else:
            export_hourly += values

    frame = synthetic.day_index(delivery_date)
    frame["ltptr_import_nomination_mw"] = _expand_hourly_to_quarter_hour(import_hourly)
    frame["ltptr_export_nomination_mw"] = _expand_hourly_to_quarter_hour(export_hourly)
    frame["ltptr_net_import_nomination_mw"] = (
        frame["ltptr_import_nomination_mw"] - frame["ltptr_export_nomination_mw"]
    )
    return frame


def fetch_ipto_long_term_nominations(delivery_date: date) -> tuple[pd.DataFrame, str]:
    path, source, _ = _fetch_ipto_file(delivery_date, "LTPTRsNominationsSummary")
    return parse_ipto_long_term_nominations(path, delivery_date), source


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


def load_market_bundle(
    delivery_date: date,
    allow_synthetic: bool = True,
    fill_synthetic_features: bool = True,
) -> MarketBundle:
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

    for label, fetcher in [
        ("IPTO unit availability", fetch_ipto_unit_availability),
        ("IPTO ATC", fetch_ipto_atc),
        ("IPTO LT PTR nominations", fetch_ipto_long_term_nominations),
        ("HEnEx pre-market summary", fetch_henex_pre_market_summary),
        ("HEnEx POSNOMs", fetch_henex_posnoms),
    ]:
        try:
            extra, source = fetcher(delivery_date)
            base = base.merge(extra, on=["timestamp", "interval"], how="left")
            sources[label] = source
        except Exception as exc:  # noqa: BLE001
            warnings.append(str(exc))

    try:
        weather, source = fetch_open_meteo_weather(delivery_date)
        base = base.merge(weather, on=["timestamp", "interval"], how="left")
        sources["weather"] = source
    except Exception as exc:  # noqa: BLE001
        warnings.append(str(exc))

    fallback = synthetic.synthetic_market_day(delivery_date)
    missing_price = "DAM prices" not in sources
    if missing_price and not allow_synthetic:
        raise DataSourceError("DAM prices unavailable and synthetic fallback disabled")
    if fill_synthetic_features:
        for column in fallback.columns:
            if column in ("timestamp", "interval"):
                continue
            if column not in base.columns:
                base[column] = fallback[column]
            else:
                base[column] = base[column].fillna(fallback[column])
    elif missing_price:
        base["dam_price_eur_mwh"] = fallback["dam_price_eur_mwh"]

    base["data_quality"] = np.where(
        missing_price,
        "synthetic price fallback",
        "public price data",
    )
    if missing_price:
        sources["DAM prices"] = "Synthetic fallback generated from Greek load/RES price shape"

    return MarketBundle(frame=base, sources=sources, warnings=warnings)
