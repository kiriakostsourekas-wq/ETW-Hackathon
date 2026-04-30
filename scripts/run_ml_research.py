from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")

from batteryhack.config import PROCESSED_DIR, ensure_data_dirs
from batteryhack.ml_research import (
    DEFAULT_RESEARCH_MODEL_CANDIDATES,
    FEATURE_SET_COLUMNS,
    benchmark_frame_as_model_daily,
    build_daily_winners,
    build_model_selection_stability,
    build_paired_uplift_summary,
    run_feature_ablation_backtest,
    run_ml_research_backtest,
)
from batteryhack.optimizer import BatteryParams
from batteryhack.presets import BATTERY_PRESETS, METLEN_PRESET_NAME
from batteryhack.simulation import load_market_history


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run chronological ML research backtests for Greek DAM BESS forecasting."
    )
    parser.add_argument("--start", required=True, help="First target delivery date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="Last target delivery date YYYY-MM-DD")
    parser.add_argument(
        "--history-start",
        default=None,
        help="First date to load for training history. Defaults to start - min_train_days.",
    )
    parser.add_argument("--min-train-days", type=int, default=14)
    parser.add_argument("--max-days", type=int, default=None)
    parser.add_argument(
        "--models",
        default=",".join(DEFAULT_RESEARCH_MODEL_CANDIDATES),
        help="Comma-separated model list.",
    )
    parser.add_argument(
        "--feature-set",
        default="all_live_safe",
        choices=tuple(FEATURE_SET_COLUMNS),
        help="Feature subset for supervised ML candidates.",
    )
    parser.add_argument(
        "--include-synthetic-targets",
        action="store_true",
        help="Evaluate synthetic fallback target-price days. Off by default.",
    )
    parser.add_argument(
        "--include-synthetic-training",
        action="store_true",
        help="Train on synthetic fallback price labels. Off by default.",
    )
    parser.add_argument("--summary-output", default="ml_research_summary.csv")
    parser.add_argument("--daily-output", default="ml_research_daily.csv")
    parser.add_argument("--predictions-output", default="ml_research_predictions.csv")
    parser.add_argument("--skipped-output", default="ml_research_skipped_days.csv")
    parser.add_argument("--assumptions-output", default="ml_research_assumptions.json")
    parser.add_argument("--daily-winners-output", default="ml_research_daily_winners.csv")
    parser.add_argument("--model-stability-output", default="ml_research_model_stability.csv")
    parser.add_argument("--paired-uplift-output", default="ml_research_paired_uplift.csv")
    parser.add_argument(
        "--primary-model",
        default=None,
        help=(
            "Primary model for paired uplift. Defaults to the best total-PnL model "
            "from this run."
        ),
    )
    parser.add_argument(
        "--uk-baseline-path",
        default=None,
        help=(
            "Optional full same-window UK baseline CSV. Not used unless explicitly "
            "provided."
        ),
    )
    parser.add_argument(
        "--ablation-only",
        action="store_true",
        help="Run feature-set ablations instead of the main model comparison.",
    )
    parser.add_argument("--ablation-model", default="ridge")
    parser.add_argument(
        "--ablation-feature-sets",
        default=",".join(FEATURE_SET_COLUMNS),
        help="Comma-separated feature sets to test in ablation-only mode.",
    )
    parser.add_argument("--ablation-summary-output", default="ml_research_ablation_summary.csv")
    parser.add_argument("--power-mw", type=float, default=None)
    parser.add_argument("--capacity-mwh", type=float, default=None)
    parser.add_argument("--round-trip-efficiency", type=float, default=None)
    parser.add_argument("--degradation", type=float, default=None)
    parser.add_argument("--max-cycles", type=float, default=None)
    args = parser.parse_args()

    ensure_data_dirs()
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    history_start = (
        date.fromisoformat(args.history_start)
        if args.history_start
        else start - timedelta(days=args.min_train_days)
    )
    model_candidates = tuple(
        model.strip() for model in args.models.split(",") if model.strip()
    )
    params = _battery_params_from_args(args)

    history = load_market_history(history_start, end, allow_synthetic=True)
    if args.ablation_only:
        ablation = run_feature_ablation_backtest(
            history.frame,
            start,
            end,
            battery_params=params,
            min_train_days=args.min_train_days,
            max_days=args.max_days,
            model_name=args.ablation_model,
            feature_sets=tuple(
                value.strip()
                for value in args.ablation_feature_sets.split(",")
                if value.strip()
            ),
            drop_synthetic_targets=not args.include_synthetic_targets,
            drop_synthetic_training=not args.include_synthetic_training,
        )
        _write_csv(ablation, args.ablation_summary_output)
        print(ablation.round(4).to_string(index=False))
        print(f"\nSaved ablation output under {PROCESSED_DIR}")
        return

    result = run_ml_research_backtest(
        history.frame,
        start,
        end,
        battery_params=params,
        min_train_days=args.min_train_days,
        max_days=args.max_days,
        model_candidates=model_candidates,
        drop_synthetic_targets=not args.include_synthetic_targets,
        drop_synthetic_training=not args.include_synthetic_training,
        feature_set=args.feature_set,
    )

    _write_csv(result.summary, args.summary_output)
    _write_csv(result.daily, args.daily_output)
    _write_csv(result.predictions, args.predictions_output)
    _write_csv(result.skipped_days, args.skipped_output)
    daily_winners = build_daily_winners(result.daily)
    model_stability = build_model_selection_stability(result.summary, result.daily)
    primary_model = _select_primary_model(result.summary, result.daily, args.primary_model)
    paired_daily = _daily_with_explicit_uk_baseline(result.daily, args.uk_baseline_path)
    comparison_models = _paired_comparison_models(
        result.daily,
        primary_model,
        include_uk_baseline=args.uk_baseline_path is not None,
    )
    paired_uplift = build_paired_uplift_summary(
        paired_daily,
        primary_model=primary_model,
        comparison_models=comparison_models,
    )
    _write_csv(daily_winners, args.daily_winners_output)
    _write_csv(model_stability, args.model_stability_output)
    _write_csv(paired_uplift, args.paired_uplift_output)
    assumptions = {
        **result.assumptions,
        "source_summary": history.source_summary,
        "history_start": history_start.isoformat(),
        "battery_params": params.__dict__,
        "paired_uplift_primary_model": primary_model,
        "paired_uplift_comparison_models": list(comparison_models),
        "uk_baseline_path": args.uk_baseline_path,
    }
    _write_json(assumptions, args.assumptions_output)

    if result.summary.empty:
        print("No model days evaluated. Inspect skipped-days output.")
    else:
        print(result.summary.round(4).to_string(index=False))
    print(f"\nSaved outputs under {PROCESSED_DIR}")


def _select_primary_model(summary: pd.DataFrame, daily: pd.DataFrame, requested: str | None) -> str:
    if daily.empty:
        raise ValueError("Cannot select a paired-uplift primary model from empty daily results")
    available = set(daily["model"].dropna().astype(str))
    if requested is not None:
        if requested not in available:
            raise ValueError(
                f"--primary-model {requested!r} is not in current run models: "
                f"{sorted(available)}"
            )
        return requested
    if summary.empty or "total_realized_net_revenue_eur" not in summary.columns:
        totals = daily.groupby("model")["realized_net_revenue_eur"].sum()
        return str(totals.sort_values(ascending=False).index[0])
    ordered = summary.sort_values(
        ["total_realized_net_revenue_eur", "model"],
        ascending=[False, True],
    )
    return str(ordered.iloc[0]["model"])


def _daily_with_explicit_uk_baseline(daily: pd.DataFrame, uk_baseline_path: str | None):
    if uk_baseline_path is None:
        return daily
    path = Path(uk_baseline_path)
    if not path.exists():
        raise FileNotFoundError(f"UK baseline path does not exist: {path}")
    uk = benchmark_frame_as_model_daily(
        pd.read_csv(path),
        model_name="uk_naive_baseline",
    )
    expected_dates = set(daily["delivery_date"].astype(str).unique())
    uk_dates = set(uk["delivery_date"].astype(str).unique())
    missing = sorted(expected_dates - uk_dates)
    if missing:
        raise ValueError(
            "UK baseline must cover every evaluated ML target date; "
            f"missing {len(missing)} dates, including {missing[:5]}"
        )
    uk = uk[uk["delivery_date"].astype(str).isin(expected_dates)].copy()
    return pd.concat([daily, uk], ignore_index=True, sort=False)


def _paired_comparison_models(
    daily: pd.DataFrame,
    primary_model: str,
    include_uk_baseline: bool,
) -> tuple[str, ...]:
    models = [
        model
        for model in daily["model"].dropna().astype(str).drop_duplicates().tolist()
        if model != primary_model
    ]
    if include_uk_baseline:
        models.append("uk_naive_baseline")
    return tuple(models)


def _battery_params_from_args(args: argparse.Namespace) -> BatteryParams:
    preset = BATTERY_PRESETS[METLEN_PRESET_NAME].to_params()
    return BatteryParams(
        power_mw=args.power_mw if args.power_mw is not None else preset.power_mw,
        capacity_mwh=(
            args.capacity_mwh if args.capacity_mwh is not None else preset.capacity_mwh
        ),
        round_trip_efficiency=(
            args.round_trip_efficiency
            if args.round_trip_efficiency is not None
            else preset.round_trip_efficiency
        ),
        min_soc_pct=preset.min_soc_pct,
        max_soc_pct=preset.max_soc_pct,
        initial_soc_pct=preset.initial_soc_pct,
        terminal_soc_pct=preset.terminal_soc_pct,
        degradation_cost_eur_mwh=(
            args.degradation
            if args.degradation is not None
            else preset.degradation_cost_eur_mwh
        ),
        max_cycles_per_day=(
            args.max_cycles if args.max_cycles is not None else preset.max_cycles_per_day
        ),
    )


def _write_csv(frame, output_name: str) -> None:
    path = _processed_path(output_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def _write_json(payload: dict[str, object], output_name: str) -> None:
    path = _processed_path(output_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=_json_default))


def _processed_path(output_name: str) -> Path:
    path = Path(output_name)
    if path.is_absolute():
        resolved = path.resolve()
    else:
        resolved = (PROCESSED_DIR / path).resolve()
    processed_root = PROCESSED_DIR.resolve()
    if not resolved.is_relative_to(processed_root):
        raise ValueError(f"Output path must stay under {processed_root}: {resolved}")
    return resolved


def _json_default(value):
    if hasattr(value, "item"):
        return value.item()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


if __name__ == "__main__":
    main()
