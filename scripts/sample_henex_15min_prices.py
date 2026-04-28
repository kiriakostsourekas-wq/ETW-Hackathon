from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from batteryhack.config import PROCESSED_DIR, ensure_data_dirs
from batteryhack.data_sources import fetch_henex_prices


def _date_range(start: date, end: date, max_days: int) -> list[date]:
    if end < start:
        raise ValueError("--end must be on or after --start")
    if max_days < 1:
        raise ValueError("--max-days must be at least 1")

    days: list[date] = []
    current = start
    while current <= end and len(days) < max_days:
        days.append(current)
        current += timedelta(days=1)
    return days


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch a small sample of 15-minute Greek DAM prices from HEnEx.",
    )
    parser.add_argument("--start", default="2026-04-22", help="Start delivery date YYYY-MM-DD.")
    parser.add_argument("--end", default="2026-04-24", help="End delivery date YYYY-MM-DD.")
    parser.add_argument("--max-days", type=int, default=3, help="Safety cap for sample size.")
    parser.add_argument("--output", default="henex_15min_price_sample.csv")
    parser.add_argument("--strict", action="store_true", help="Fail fast if any date is unavailable.")
    args = parser.parse_args()

    ensure_data_dirs()
    frames: list[pd.DataFrame] = []
    errors: list[str] = []

    for delivery_date in _date_range(
        date.fromisoformat(args.start),
        date.fromisoformat(args.end),
        args.max_days,
    ):
        try:
            frame, source_url = fetch_henex_prices(delivery_date)
            if len(frame) != 96:
                raise RuntimeError(f"expected 96 quarter-hour prices, got {len(frame)}")

            frame = frame.copy()
            frame.insert(0, "delivery_date", delivery_date.isoformat())
            frame["source_url"] = source_url
            frames.append(frame)
            print(f"{delivery_date}: fetched {len(frame)} 15-minute prices")
        except Exception as exc:  # noqa: BLE001 - sample loop should report and continue by default
            message = f"{delivery_date}: {exc}"
            errors.append(message)
            print(f"{delivery_date}: skipped - {exc}")
            if args.strict:
                raise

    if not frames:
        print("No HEnEx price data fetched.")
        return 1

    output = pd.concat(frames, ignore_index=True)
    output_path = PROCESSED_DIR / args.output
    output.to_csv(output_path, index=False)

    print("\nSample rows:")
    print(output.head(12).to_string(index=False))
    print(f"\nSaved {len(output)} rows to {output_path}")
    if errors:
        print("\nSkipped dates:")
        for error in errors:
            print(f"- {error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
