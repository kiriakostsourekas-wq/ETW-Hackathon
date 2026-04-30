from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from batteryhack.baseline import BASELINE_JOIN_COLUMNS, run_uk_naive_baseline_backtest
from batteryhack.config import PROCESSED_DIR, ensure_data_dirs
from batteryhack.presets import BATTERY_PRESETS, METLEN_PRESET_NAME
from batteryhack.simulation import load_market_history


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run the UK-style naive previous-day persistence BESS benchmark on Greek DAM data."
        )
    )
    parser.add_argument("--history-start", default="2026-03-01")
    parser.add_argument("--start", default="2026-03-22")
    parser.add_argument("--end", default="2026-03-31")
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
        "--output",
        default="uk_naive_baseline_dispatch.csv",
        help="CSV filename under data/processed.",
    )
    args = parser.parse_args()

    history_start = date.fromisoformat(args.history_start)
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)

    ensure_data_dirs()
    history = load_market_history(
        history_start,
        end,
        allow_synthetic=not args.no_synthetic,
    )
    params = BATTERY_PRESETS[METLEN_PRESET_NAME].to_params()
    result = run_uk_naive_baseline_backtest(
        history.frame,
        start,
        end,
        params,
        drop_synthetic_targets=not args.include_synthetic_targets,
    )
    if not result.empty:
        ordered_columns = [column for column in BASELINE_JOIN_COLUMNS if column in result.columns]
        remaining_columns = [column for column in result.columns if column not in ordered_columns]
        result = result[ordered_columns + remaining_columns]

    output_path = PROCESSED_DIR / args.output
    result.to_csv(output_path, index=False)

    print("Source summary")
    print(history.source_summary)
    if history.warnings:
        print(f"Warnings: {len(history.warnings)}")
        for warning in history.warnings[:5]:
            print(f"- {warning}")
    print(
        "\nBatteryParams: "
        f"{params.power_mw:g} MW / {params.capacity_mwh:g} MWh, "
        f"RTE {params.round_trip_efficiency:.2f}, "
        f"SoC {params.min_soc_pct:g}-{params.max_soc_pct:g}%, "
        f"initial/terminal {params.initial_soc_pct:g}/{params.terminal_soc_pct:g}%, "
        f"degradation {params.degradation_cost_eur_mwh:g} EUR/MWh throughput, "
        f"cycle limit {params.max_cycles_per_day if params.max_cycles_per_day is not None else 'off'}"
    )

    if result.empty:
        print("\nNo baseline rows generated.")
    else:
        summary = {
            "days": len(result),
            "total_realized_net_revenue_eur": result["baseline_realized_net_revenue_eur"].sum(),
            "total_oracle_net_revenue_eur": result["oracle_net_revenue_eur"].sum(),
            "mean_capture_ratio_vs_oracle": result["baseline_capture_ratio_vs_oracle"].mean(),
            "mean_forecast_mae_eur_mwh": result["baseline_forecast_mae_eur_mwh"].mean(),
            "total_discharged_mwh": result["baseline_discharged_mwh"].sum(),
            "total_equivalent_cycles": result["baseline_equivalent_cycles"].sum(),
        }
        print("\nBaseline summary")
        for key, value in summary.items():
            if isinstance(value, float):
                print(f"{key}: {value:,.3f}")
            else:
                print(f"{key}: {value}")

        print("\nDaily baseline rows")
        print(
            result[
                [
                    "delivery_date",
                    "benchmark",
                    "baseline_method",
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

    print(f"\nSaved {output_path}")


if __name__ == "__main__":
    main()
