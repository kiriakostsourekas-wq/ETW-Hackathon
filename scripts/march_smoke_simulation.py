from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")

from batteryhack.config import PROCESSED_DIR, ensure_data_dirs
from batteryhack.presets import BATTERY_PRESETS, METLEN_PRESET_NAME
from batteryhack.simulation import (
    DEFAULT_MODEL_CANDIDATES,
    load_market_history,
    run_trained_march_smoke_simulation,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Train/select a live-safe price forecast model and run a METLEN BESS March smoke "
            "dispatch simulation."
        )
    )
    parser.add_argument("--start", default="2026-03-01", help="History start date YYYY-MM-DD")
    parser.add_argument(
        "--validation-start",
        default="2026-03-15",
        help="First validation date used for model selection",
    )
    parser.add_argument(
        "--validation-end",
        default="2026-03-21",
        help="Last validation date used for model selection",
    )
    parser.add_argument(
        "--smoke-start",
        default="2026-03-22",
        help="First out-of-sample smoke dispatch date",
    )
    parser.add_argument("--smoke-end", default="2026-03-31", help="Last smoke dispatch date")
    parser.add_argument(
        "--models",
        default=",".join(DEFAULT_MODEL_CANDIDATES),
        help="Comma-separated model families to compare",
    )
    parser.add_argument(
        "--no-synthetic",
        action="store_true",
        help="Fail if public DAM prices are unavailable instead of filling fallback prices",
    )
    parser.add_argument(
        "--include-synthetic-price-days",
        action="store_true",
        help="Keep fallback price days in model selection and smoke metrics",
    )
    parser.add_argument(
        "--performance-output",
        default="march_smoke_model_performance.csv",
        help="CSV filename under data/processed for model-selection performance",
    )
    parser.add_argument(
        "--daily-performance-output",
        default="march_smoke_daily_model_performance.csv",
        help="CSV filename under data/processed for daily validation metrics",
    )
    parser.add_argument(
        "--dispatch-output",
        default="march_smoke_dispatch.csv",
        help="CSV filename under data/processed for smoke dispatch metrics",
    )
    args = parser.parse_args()

    history_start = date.fromisoformat(args.start)
    validation_start = date.fromisoformat(args.validation_start)
    validation_end = date.fromisoformat(args.validation_end)
    smoke_start = date.fromisoformat(args.smoke_start)
    smoke_end = date.fromisoformat(args.smoke_end)
    model_candidates = tuple(model.strip() for model in args.models.split(",") if model.strip())

    ensure_data_dirs()
    history = load_market_history(
        history_start,
        smoke_end,
        allow_synthetic=not args.no_synthetic,
    )
    simulation_frame = history.frame
    dropped_synthetic_dates: list[str] = []
    if not args.include_synthetic_price_days:
        synthetic_dates = (
            simulation_frame.loc[
                simulation_frame["data_quality"] != "public price data",
                "timestamp",
            ]
            .dt.date.astype(str)
            .drop_duplicates()
            .tolist()
        )
        if synthetic_dates:
            dropped_synthetic_dates = synthetic_dates
            simulation_frame = simulation_frame[
                simulation_frame["data_quality"] == "public price data"
            ].copy()
    params = BATTERY_PRESETS[METLEN_PRESET_NAME].to_params()
    result = run_trained_march_smoke_simulation(
        simulation_frame,
        validation_start,
        validation_end,
        smoke_start,
        smoke_end,
        params,
        model_candidates=model_candidates,
    )

    performance_path = PROCESSED_DIR / args.performance_output
    daily_performance_path = PROCESSED_DIR / args.daily_performance_output
    dispatch_path = PROCESSED_DIR / args.dispatch_output
    result.model_performance.to_csv(performance_path, index=False)
    result.daily_model_performance.to_csv(daily_performance_path, index=False)
    result.dispatch.to_csv(dispatch_path, index=False)

    print("Source summary")
    print(history.source_summary)
    if history.warnings:
        print(f"Warnings: {len(history.warnings)}")
        for warning in history.warnings[:5]:
            print(f"- {warning}")
    if dropped_synthetic_dates:
        print(
            "Dropped synthetic fallback price days from simulation: "
            + ", ".join(dropped_synthetic_dates)
        )
    print("\nValidation model performance")
    print(result.model_performance.round(3).to_string(index=False))
    print(f"\nSelected ML model for smoke dispatch: {result.selected_model}")
    print("\nSmoke dispatch summary")
    if result.dispatch.empty:
        print("No smoke dispatch rows generated.")
    else:
        summary = {
            "days": len(result.dispatch),
            "mean_forecast_mae_eur_mwh": result.dispatch["forecast_mae_eur_mwh"].mean(),
            "total_realized_net_revenue_eur": result.dispatch["realized_net_revenue_eur"].sum(),
            "total_oracle_net_revenue_eur": result.dispatch["oracle_net_revenue_eur"].sum(),
            "mean_capture_ratio_vs_oracle": result.dispatch["capture_ratio_vs_oracle"].mean(),
            "total_discharged_mwh": result.dispatch["realized_discharged_mwh"].sum(),
        }
        print(
            "\n".join(
                f"{key}: {value:,.3f}" if isinstance(value, float) else f"{key}: {value}"
                for key, value in summary.items()
            )
        )
        print("\nDaily smoke rows")
        print(
            result.dispatch[
                [
                    "delivery_date",
                    "forecast_mae_eur_mwh",
                    "realized_net_revenue_eur",
                    "oracle_net_revenue_eur",
                    "capture_ratio_vs_oracle",
                    "realized_equivalent_cycles",
                ]
            ]
            .round(3)
            .to_string(index=False)
        )
    print(f"\nSaved {performance_path}")
    print(f"Saved {daily_performance_path}")
    print(f"Saved {dispatch_path}")


if __name__ == "__main__":
    main()
