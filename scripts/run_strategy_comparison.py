from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from batteryhack.config import PROCESSED_DIR, ensure_data_dirs
from batteryhack.presets import BATTERY_PRESETS, METLEN_PRESET_NAME
from batteryhack.simulation import load_market_history
from batteryhack.strategy_comparison import (
    build_headline_frame,
    build_headline_report,
    build_strategy_comparison,
    delivery_window,
    filter_delivery_dates,
    run_uk_naive_baseline_for_comparison,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build one same-date comparison for Agent 1 ML strategies versus the "
            "UK naive baseline on Greek DAM data."
        )
    )
    parser.add_argument("--ml-daily", default="ml_research_daily.csv")
    parser.add_argument("--ml-predictions", default="ml_research_predictions.csv")
    parser.add_argument(
        "--models",
        default=None,
        help="Optional comma-separated ML model names to include from the input CSVs.",
    )
    parser.add_argument(
        "--baseline-daily",
        default=None,
        help="Optional precomputed UK naive daily CSV. If omitted, the script runs the baseline.",
    )
    parser.add_argument(
        "--baseline-intervals",
        default=None,
        help="Optional precomputed UK naive interval CSV.",
    )
    parser.add_argument("--start", default=None, help="First delivery date YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="Last delivery date YYYY-MM-DD")
    parser.add_argument(
        "--history-start",
        default=None,
        help="First date to load when running the UK baseline. Defaults to start - 7 days.",
    )
    parser.add_argument(
        "--include-synthetic-targets",
        action="store_true",
        help="Include target days whose DAM price is synthetic fallback.",
    )
    parser.add_argument(
        "--no-synthetic",
        action="store_true",
        help="Fail if a public source is unavailable instead of using fallback data.",
    )
    parser.add_argument(
        "--skip-intervals",
        action="store_true",
        help="Only write daily and summary outputs.",
    )
    parser.add_argument("--daily-output", default="strategy_comparison_daily.csv")
    parser.add_argument("--intervals-output", default="strategy_comparison_intervals.csv")
    parser.add_argument("--summary-output", default="strategy_comparison_summary.csv")
    parser.add_argument("--headline-output", default="strategy_comparison_headline.json")
    args = parser.parse_args()

    ensure_data_dirs()
    ml_daily_path = _input_path(args.ml_daily)
    if not ml_daily_path.exists():
        raise FileNotFoundError(
            f"ML daily input not found: {ml_daily_path}. "
            "Run scripts/run_ml_research.py first or pass --ml-daily."
        )

    ml_daily = pd.read_csv(ml_daily_path)
    inferred_start, inferred_end = delivery_window(ml_daily)
    start = date.fromisoformat(args.start) if args.start else inferred_start
    end = date.fromisoformat(args.end) if args.end else inferred_end
    ml_daily = filter_delivery_dates(ml_daily, start, end)
    model_filter = _model_filter(args.models)
    if model_filter is not None:
        ml_daily = _filter_models(ml_daily, model_filter, "ml_daily")

    ml_predictions = _read_optional_csv(args.ml_predictions)
    if ml_predictions is not None:
        ml_predictions = filter_delivery_dates(ml_predictions, start, end)
        if model_filter is not None:
            ml_predictions = _filter_models(ml_predictions, model_filter, "ml_predictions")

    baseline_daily, baseline_intervals, battery_params = _load_or_run_baseline(args, start, end)
    baseline_daily = filter_delivery_dates(baseline_daily, start, end)
    if baseline_intervals is not None:
        baseline_intervals = filter_delivery_dates(baseline_intervals, start, end)

    result = build_strategy_comparison(
        ml_daily=ml_daily,
        baseline_daily=baseline_daily,
        ml_predictions=None if args.skip_intervals else ml_predictions,
        baseline_intervals=None if args.skip_intervals else baseline_intervals,
    )

    daily_path = _processed_output_path(args.daily_output)
    summary_path = _processed_output_path(args.summary_output)
    headline_path = _processed_output_path(args.headline_output)
    headline = build_headline_report(
        result.daily,
        result.summary,
        battery_params=battery_params,
    )
    result.daily.to_csv(daily_path, index=False)
    result.summary.to_csv(summary_path, index=False)
    _write_headline(headline, headline_path)

    intervals_path = None
    if not args.skip_intervals and not result.intervals.empty:
        intervals_path = _processed_output_path(args.intervals_output)
        result.intervals.to_csv(intervals_path, index=False)

    print("Strategy comparison summary")
    print(result.summary.round(4).to_string(index=False))
    print(f"\nSaved {daily_path}")
    if intervals_path is not None:
        print(f"Saved {intervals_path}")
    else:
        print("No interval comparison written; interval inputs were unavailable or empty.")
    print(f"Saved {summary_path}")
    print(f"Saved {headline_path}")


def _load_or_run_baseline(
    args: argparse.Namespace,
    start: date,
    end: date,
) -> tuple[pd.DataFrame, pd.DataFrame | None, object | None]:
    if args.baseline_daily:
        baseline_daily = pd.read_csv(_input_path(args.baseline_daily))
        baseline_intervals = _read_optional_csv(args.baseline_intervals)
        return baseline_daily, baseline_intervals, None

    history_start = (
        date.fromisoformat(args.history_start)
        if args.history_start
        else start - timedelta(days=7)
    )
    history = load_market_history(
        history_start,
        end,
        allow_synthetic=not args.no_synthetic,
    )
    params = BATTERY_PRESETS[METLEN_PRESET_NAME].to_params()
    baseline_daily, baseline_intervals = run_uk_naive_baseline_for_comparison(
        history.frame,
        start,
        end,
        params,
        drop_synthetic_targets=not args.include_synthetic_targets,
        include_intervals=not args.skip_intervals,
    )
    return baseline_daily, baseline_intervals, params


def _write_headline(headline: dict[str, object], path: Path) -> None:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        build_headline_frame(headline).to_csv(path, index=False)
        return
    path.write_text(json.dumps(headline, indent=2, default=_json_default) + "\n")


def _read_optional_csv(value: str | None) -> pd.DataFrame | None:
    if not value:
        return None
    path = _input_path(value)
    if not path.exists():
        return None
    return pd.read_csv(path)


def _model_filter(value: str | None) -> set[str] | None:
    if not value:
        return None
    models = {model.strip() for model in value.split(",") if model.strip()}
    if not models:
        raise ValueError("--models was provided but no model names were parsed")
    return models


def _filter_models(frame: pd.DataFrame, models: set[str], label: str) -> pd.DataFrame:
    model_column = "model" if "model" in frame.columns else "model_or_method"
    if model_column not in frame.columns:
        raise ValueError(
            f"{label} is missing model/model_or_method column required by --models"
        )
    filtered = frame[frame[model_column].astype(str).isin(models)].copy()
    if filtered.empty:
        raise ValueError(f"{label} has no rows for requested models: {sorted(models)}")
    return filtered


def _input_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    if path.exists():
        return path.resolve()
    return (PROCESSED_DIR / path).resolve()


def _processed_output_path(value: str) -> Path:
    path = Path(value)
    resolved = path.resolve() if path.is_absolute() else (PROCESSED_DIR / path).resolve()
    processed_root = PROCESSED_DIR.resolve()
    if not resolved.is_relative_to(processed_root):
        raise ValueError(f"Output path must stay under {processed_root}: {resolved}")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def _json_default(value: object) -> object:
    if hasattr(value, "item"):
        return value.item()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


if __name__ == "__main__":
    main()
