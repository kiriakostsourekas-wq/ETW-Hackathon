from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from batteryhack.config import PROCESSED_DIR, ensure_data_dirs
from batteryhack.data_sources import DataSourceError, fetch_henex_prices, load_market_bundle


def daterange(start_date: date, end_date: date, max_days: int) -> list[date]:
    if end_date < start_date:
        raise ValueError("--end must be on or after --start")
    days: list[date] = []
    current = start_date
    while current <= end_date and len(days) < max_days:
        days.append(current)
        current += timedelta(days=1)
    return days


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Scrape no-key Greek DAM training data from HEnEx, IPTO, and Open-Meteo. "
            "The default output rejects synthetic feature fallback so the CSV can be used "
            "for leakage-safe model training."
        )
    )
    parser.add_argument("--start", default="2025-10-01", help="Start delivery date YYYY-MM-DD.")
    parser.add_argument("--end", default=date.today().isoformat(), help="End delivery date YYYY-MM-DD.")
    parser.add_argument("--max-days", type=int, default=220, help="Safety cap for date count.")
    parser.add_argument(
        "--allow-synthetic",
        action="store_true",
        help="Allow synthetic DAM price fallback. Off by default for training quality.",
    )
    parser.add_argument(
        "--fill-synthetic-features",
        action="store_true",
        help="Fill missing feature columns with synthetic demo data. Off by default.",
    )
    parser.add_argument("--output", default="greek_dam_training_dataset.csv")
    parser.add_argument("--manifest", default="greek_dam_training_manifest.json")
    args = parser.parse_args()

    ensure_data_dirs()
    frames: list[pd.DataFrame] = []
    manifest: list[dict[str, object]] = []

    for delivery_date in daterange(
        date.fromisoformat(args.start),
        date.fromisoformat(args.end),
        args.max_days,
    ):
        try:
            if not args.allow_synthetic:
                fetch_henex_prices(delivery_date)
            bundle = load_market_bundle(
                delivery_date,
                allow_synthetic=args.allow_synthetic,
                fill_synthetic_features=args.fill_synthetic_features,
            )
            frame = bundle.frame.copy()
            if len(frame) != 96:
                raise DataSourceError(f"expected 96 intervals, got {len(frame)}")
            quality = str(frame["data_quality"].iloc[0])
            if quality != "public price data" and not args.allow_synthetic:
                raise DataSourceError("skipping non-public DAM price day")

            frame.insert(0, "delivery_date", delivery_date.isoformat())
            frames.append(frame)
            manifest.append(
                {
                    "delivery_date": delivery_date.isoformat(),
                    "status": "ok",
                    "data_quality": quality,
                    "sources": bundle.sources,
                    "warnings": bundle.warnings,
                    "optional_unavailable": bundle.optional_unavailable,
                }
            )
            print(
                f"{delivery_date}: ok, {len(bundle.sources)} source groups, "
                f"{len(bundle.warnings)} warnings, "
                f"{len(bundle.optional_unavailable)} optional unavailable"
            )
        except Exception as exc:  # noqa: BLE001 - scraper should continue across bad days
            manifest.append(
                {
                    "delivery_date": delivery_date.isoformat(),
                    "status": "skipped",
                    "error": str(exc),
                }
            )
            print(f"{delivery_date}: skipped - {exc}")

    if not frames:
        print("No public training rows were scraped.")
        return 1

    output = pd.concat(frames, ignore_index=True).sort_values("timestamp").reset_index(drop=True)
    output_path = PROCESSED_DIR / args.output
    manifest_path = PROCESSED_DIR / args.manifest
    output.to_csv(output_path, index=False)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    public_days = int((output.groupby("delivery_date")["data_quality"].first() == "public price data").sum())
    feature_columns = [
        column
        for column in output.columns
        if column not in {"delivery_date", "timestamp", "interval", "dam_price_eur_mwh"}
    ]
    non_null_features = output[feature_columns].notna().mean().sort_values(ascending=False)
    print(f"\nSaved {len(output)} rows across {public_days} public-price days to {output_path}")
    print(f"Saved source manifest to {manifest_path}")
    print("\nTop feature coverage:")
    print(non_null_features.head(25).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
