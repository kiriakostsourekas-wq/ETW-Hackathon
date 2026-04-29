from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")

from batteryhack.config import PROCESSED_DIR, RAW_DIR, ensure_data_dirs
from batteryhack.data_sources import load_market_bundle
from batteryhack.market_impact import (
    MarketImpactThresholds,
    load_curve_file,
    run_single_bess_market_impact,
    thresholds_to_dict,
)
from batteryhack.optimizer import BatteryParams, optimize_battery_schedule


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run an offline HEnEx curve re-clearing test for one METLEN-scale "
            "330 MW / 790 MWh BESS. The dispatch is optimized once and never "
            "re-optimized after impact."
        )
    )
    parser.add_argument("--start-date", default="2026-04-22")
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--curve-file", default=None, help="Normalized CSV/XLSX curve file.")
    parser.add_argument(
        "--curve-dir",
        default=str(RAW_DIR),
        help="Directory containing files named like YYYYMMDD_*AggrCurves*.xlsx.",
    )
    parser.add_argument("--interval-output", default="market_impact_intervals.csv")
    parser.add_argument("--summary-output", default="market_impact_daily_summary.csv")
    parser.add_argument("--power-mw", type=float, default=330.0)
    parser.add_argument("--capacity-mwh", type=float, default=790.0)
    parser.add_argument("--round-trip-efficiency", type=float, default=0.85)
    parser.add_argument("--min-soc-pct", type=float, default=10.0)
    parser.add_argument("--max-soc-pct", type=float, default=90.0)
    parser.add_argument("--initial-soc-pct", type=float, default=50.0)
    parser.add_argument("--terminal-soc-pct", type=float, default=50.0)
    parser.add_argument("--degradation-cost-eur-mwh", type=float, default=4.0)
    parser.add_argument("--max-cycles-per-day", type=float, default=1.5)
    parser.add_argument("--median-threshold-eur-mwh", type=float, default=0.5)
    parser.add_argument("--haircut-threshold-pct", type=float, default=2.0)
    parser.add_argument("--minimum-valid-share", type=float, default=0.8)
    args = parser.parse_args()

    ensure_data_dirs()
    start_date = date.fromisoformat(args.start_date)
    end_date = date.fromisoformat(args.end_date) if args.end_date else start_date
    if end_date < start_date:
        raise ValueError("--end-date must be on or after --start-date")

    params = BatteryParams(
        power_mw=args.power_mw,
        capacity_mwh=args.capacity_mwh,
        round_trip_efficiency=args.round_trip_efficiency,
        min_soc_pct=args.min_soc_pct,
        max_soc_pct=args.max_soc_pct,
        initial_soc_pct=args.initial_soc_pct,
        terminal_soc_pct=args.terminal_soc_pct,
        degradation_cost_eur_mwh=args.degradation_cost_eur_mwh,
        max_cycles_per_day=args.max_cycles_per_day,
    )
    thresholds = MarketImpactThresholds(
        median_abs_shift_eur_mwh=args.median_threshold_eur_mwh,
        revenue_haircut_pct=args.haircut_threshold_pct,
        minimum_valid_interval_share=args.minimum_valid_share,
    )

    interval_outputs: list[pd.DataFrame] = []
    summary_outputs: list[pd.DataFrame] = []
    for delivery_date in _date_range(start_date, end_date):
        curve_path = Path(args.curve_file) if args.curve_file else _find_curve_file(
            Path(args.curve_dir),
            delivery_date,
        )
        if curve_path is None:
            print(f"{delivery_date}: no AggrCurves file found; skipping")  # noqa: T201
            continue

        bundle = load_market_bundle(delivery_date)
        market = bundle.frame.copy()
        schedule = optimize_battery_schedule(market, params).schedule
        curves = load_curve_file(curve_path)
        result = run_single_bess_market_impact(
            market=market,
            schedule=schedule,
            curves=curves,
            battery_params=params,
            thresholds=thresholds,
        )
        intervals = result.interval_impacts.copy()
        intervals["curve_file"] = str(curve_path)
        summary = result.daily_summary.copy()
        summary["curve_file"] = str(curve_path)
        summary["thresholds"] = str(thresholds_to_dict(thresholds))
        interval_outputs.append(intervals)
        summary_outputs.append(summary)
        decision = summary["decision"].iloc[0] if not summary.empty else "inconclusive"
        print(f"{delivery_date}: {decision} ({curve_path.name})")  # noqa: T201

    if not interval_outputs:
        raise RuntimeError("No market-impact experiment rows were produced")

    interval_path = PROCESSED_DIR / args.interval_output
    summary_path = PROCESSED_DIR / args.summary_output
    pd.concat(interval_outputs, ignore_index=True).to_csv(interval_path, index=False)
    pd.concat(summary_outputs, ignore_index=True).to_csv(summary_path, index=False)
    print(f"Saved {interval_path}")  # noqa: T201
    print(f"Saved {summary_path}")  # noqa: T201


def _date_range(start_date: date, end_date: date):
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def _find_curve_file(curve_dir: Path, delivery_date: date) -> Path | None:
    yyyymmdd = f"{delivery_date:%Y%m%d}"
    candidates = sorted(curve_dir.glob(f"{yyyymmdd}*AggrCurves*.xlsx"))
    if not candidates:
        candidates = sorted(curve_dir.glob(f"{yyyymmdd}*AggrCurves*.csv"))
    return candidates[0] if candidates else None


if __name__ == "__main__":
    main()
