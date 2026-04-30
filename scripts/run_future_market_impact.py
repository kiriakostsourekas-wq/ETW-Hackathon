from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")

from batteryhack.config import PROCESSED_DIR, ensure_data_dirs
from batteryhack.future_market_impact import (
    get_future_bess_scenarios,
    simulate_future_market_impact,
    write_future_headline_json,
)
from batteryhack.optimizer import BatteryParams


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run future BESS penetration scenarios against an interval price day "
            "or a daily backtest summary."
        )
    )
    parser.add_argument(
        "--input",
        default=None,
        help=(
            "CSV with interval prices/schedule or daily backtest summary. "
            "Defaults to strategy_comparison_intervals.csv, then "
            "ml_research_predictions.csv, then price_taker_forecast.csv."
        ),
    )
    parser.add_argument(
        "--price-col",
        default="auto",
        help=(
            "Price column to stress. Use auto for dam_price_eur_mwh, "
            "actual_price_eur_mwh, realized_price_eur_mwh, or price_eur_mwh."
        ),
    )
    parser.add_argument(
        "--scenarios",
        default="conservative,base,aggressive",
        help="Comma-separated scenario names.",
    )
    parser.add_argument("--output-dir", default=str(PROCESSED_DIR))
    parser.add_argument("--output-prefix", default="future_market_impact")
    parser.add_argument(
        "--headline-output",
        default="future_market_impact_headline.json",
        help=(
            "Headline JSON filename/path. Relative paths are written under "
            "--output-dir."
        ),
    )
    parser.add_argument("--power-mw", type=float, default=330.0)
    parser.add_argument("--capacity-mwh", type=float, default=790.0)
    parser.add_argument("--round-trip-efficiency", type=float, default=0.85)
    parser.add_argument("--min-soc-pct", type=float, default=10.0)
    parser.add_argument("--max-soc-pct", type=float, default=90.0)
    parser.add_argument("--initial-soc-pct", type=float, default=50.0)
    parser.add_argument("--terminal-soc-pct", type=float, default=50.0)
    parser.add_argument("--degradation-cost-eur-mwh", type=float, default=4.0)
    parser.add_argument("--max-cycles-per-day", type=float, default=1.5)
    args = parser.parse_args()

    ensure_data_dirs()
    input_path = Path(args.input) if args.input else _default_input_path()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Using input {input_path}")  # noqa: T201
    frame = pd.read_csv(input_path)
    if "timestamp" in frame.columns:
        frame["timestamp"] = pd.to_datetime(frame["timestamp"])

    scenario_names = [name.strip() for name in args.scenarios.split(",") if name.strip()]
    scenarios = get_future_bess_scenarios(scenario_names)
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
    result = simulate_future_market_impact(
        frame,
        scenarios=scenarios,
        battery_params=params,
        price_col=args.price_col,
    )

    summary_path = output_dir / f"{args.output_prefix}_summary.csv"
    result.scenario_summary.to_csv(summary_path, index=False)
    print(f"Saved {summary_path}")  # noqa: T201

    headline_path = Path(args.headline_output)
    if not headline_path.is_absolute():
        headline_path = output_dir / headline_path
    headline_artifact = write_future_headline_json(
        result.scenario_summary,
        headline_path,
        input_path=input_path,
    )
    print(f"Saved {headline_path}")  # noqa: T201

    if not result.interval_impacts.empty:
        interval_path = output_dir / f"{args.output_prefix}_intervals.csv"
        result.interval_impacts.to_csv(interval_path, index=False)
        print(f"Saved {interval_path}")  # noqa: T201

    headline_rows = pd.DataFrame(headline_artifact["rows"])
    if not headline_rows.empty:
        print(headline_rows.to_string(index=False))  # noqa: T201


def _default_input_path() -> Path:
    candidates = (
        PROCESSED_DIR / "strategy_comparison_intervals.csv",
        PROCESSED_DIR / "ml_research_predictions.csv",
        PROCESSED_DIR / "price_taker_forecast.csv",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "No default future scenario input found under data/processed. "
        "Expected strategy_comparison_intervals.csv, ml_research_predictions.csv, "
        "or price_taker_forecast.csv."
    )


if __name__ == "__main__":
    main()
