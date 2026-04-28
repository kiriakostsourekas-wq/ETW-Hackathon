from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from batteryhack.backtest import run_backtest
from batteryhack.config import PROCESSED_DIR, ensure_data_dirs
from batteryhack.optimizer import BatteryParams


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Greek DAM BESS backtest over a date range.")
    parser.add_argument("--start", default="2026-04-22", help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default="2026-04-22", help="End date YYYY-MM-DD")
    parser.add_argument("--power-mw", type=float, default=10.0)
    parser.add_argument("--capacity-mwh", type=float, default=20.0)
    parser.add_argument("--degradation", type=float, default=4.0)
    parser.add_argument("--max-cycles", type=float, default=None)
    parser.add_argument("--output", default="backtest_results.csv")
    args = parser.parse_args()

    params = BatteryParams(
        power_mw=args.power_mw,
        capacity_mwh=args.capacity_mwh,
        degradation_cost_eur_mwh=args.degradation,
        max_cycles_per_day=args.max_cycles,
    )
    ensure_data_dirs()
    result = run_backtest(
        date.fromisoformat(args.start),
        date.fromisoformat(args.end),
        params,
    )
    output_path = PROCESSED_DIR / args.output
    result.to_csv(output_path, index=False)
    print(result.round(2).to_string(index=False))
    print(f"\nSaved {output_path}")


if __name__ == "__main__":
    main()
