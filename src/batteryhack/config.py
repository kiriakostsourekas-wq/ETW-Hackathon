from __future__ import annotations

from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
CACHE_DIR = DATA_DIR / "cache"
PROCESSED_DIR = DATA_DIR / "processed"

DEFAULT_DEMO_DATE = date(2026, 4, 22)
MTUS_PER_DAY = 96
MTU_HOURS = 0.25

HENEX_SUMMARY_URL = (
    "https://www.enexgroup.gr/documents/20126/366820/"
    "{yyyymmdd}_EL-DAM_ResultsSummary_EN_v{version:02d}.xlsx"
)

IPTO_FILE_API = (
    "https://www.admie.gr/getOperationMarketFilewRange"
    "?dateStart={date_iso}&dateEnd={date_iso}&FileCategory={filetype}"
)
IPTO_FILE_API_EXACT = (
    "https://www.admie.gr/getOperationMarketFile"
    "?dateStart={date_iso}&dateEnd={date_iso}&FileCategory={filetype}"
)
IPTO_FILETYPE_INFO_URL = "https://www.admie.gr/getFiletypeInfoEN"

ENTSOE_API_URL = "https://web-api.tp.entsoe.eu/api"
ENTSOE_SECURITY_TOKEN_ENV = "ENTSOE_SECURITY_TOKEN"
GREECE_BIDDING_ZONE_EIC = "10YGR-HTSO-----Y"

GREEK_WEATHER_POINTS = {
    "Athens": (37.98, 23.72),
    "Thessaly": (39.64, 22.42),
    "Western Macedonia": (40.30, 21.79),
    "Crete": (35.34, 25.13),
}

SOURCE_LINKS = {
    "HEnEx DAM": "https://www.enexgroup.gr/en/web/guest/markets-publications-el-day-ahead-market",
    "IPTO API": "https://www.admie.gr/en/market/market-statistics/file-download-api",
    "Open-Meteo": "https://open-meteo.com/en/docs",
    "ENTSO-E Transparency Platform": "https://web-api.tp.entsoe.eu/api",
}


def ensure_data_dirs() -> None:
    for path in (DATA_DIR, RAW_DIR, CACHE_DIR, PROCESSED_DIR):
        path.mkdir(parents=True, exist_ok=True)
