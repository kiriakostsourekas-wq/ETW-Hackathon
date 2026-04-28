from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from batteryhack.config import ENTSOE_API_URL, ENTSOE_SECURITY_TOKEN_ENV, GREECE_BIDDING_ZONE_EIC


USER_AGENT = "ETW-Hackathon-BESS/1.0"


def _reason_from_xml(payload: str) -> str:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return ""

    code = root.findtext(".//{*}Reason/{*}code")
    text = root.findtext(".//{*}Reason/{*}text")
    if code and text:
        return f"{code} {text}"
    if text:
        return text
    return ""


def _period(value: date, hours: int) -> tuple[str, str]:
    start = datetime.combine(value, datetime.min.time())
    end = start + timedelta(hours=hours)
    return start.strftime("%Y%m%d%H%M"), end.strftime("%Y%m%d%H%M")


def _get(params: dict[str, str] | None = None) -> requests.Response:
    return requests.get(
        ENTSOE_API_URL,
        params=params,
        timeout=20,
        headers={"User-Agent": USER_AGENT},
    )


def _print_response(label: str, response: requests.Response) -> None:
    reason = _reason_from_xml(response.text)
    content_type = response.headers.get("content-type", "unknown")
    print(f"{label}: HTTP {response.status_code}, content-type={content_type}")
    if reason:
        print(f"{label} acknowledgement: {reason}")


def _sample_prices(token: str, sample_date: date, hours: int) -> None:
    period_start, period_end = _period(sample_date, hours)
    params = {
        "securityToken": token,
        "documentType": "A44",
        "in_Domain": GREECE_BIDDING_ZONE_EIC,
        "out_Domain": GREECE_BIDDING_ZONE_EIC,
        "periodStart": period_start,
        "periodEnd": period_end,
    }
    response = _get(params)
    _print_response("Sample query", response)
    if response.status_code != 200:
        return

    try:
        root = ET.fromstring(response.text)
    except ET.ParseError:
        print(f"Sample bytes received: {len(response.content)}")
        return

    points = root.findall(".//{*}Point")
    first_price = root.findtext(".//{*}Point/{*}price.amount")
    print(f"Sample points received: {len(points)}")
    if first_price:
        print(f"First sample price amount: {first_price} EUR/MWh")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check ENTSO-E Transparency Platform API access.")
    parser.add_argument("--token-env", default=ENTSOE_SECURITY_TOKEN_ENV)
    parser.add_argument("--sample", action="store_true", help="Run a minimal Greece DAM sample query.")
    parser.add_argument("--sample-date", default="2026-04-22", help="Sample date YYYY-MM-DD.")
    parser.add_argument("--hours", type=int, default=1, help="Requested sample window length in hours.")
    args = parser.parse_args()

    print(f"Endpoint: {ENTSOE_API_URL}")
    response = _get()
    _print_response("Reachability probe", response)

    token = os.environ.get(args.token_env)
    if not token:
        print(f"Authenticated probe skipped: set {args.token_env} to your ENTSO-E security token.")
        return 0

    auth_response = _get({"securityToken": token})
    _print_response("Authenticated no-data probe", auth_response)
    if "Authentication failed" in auth_response.text:
        return 1

    if args.sample:
        _sample_prices(token, date.fromisoformat(args.sample_date), args.hours)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
