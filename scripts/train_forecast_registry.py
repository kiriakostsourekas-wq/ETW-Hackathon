from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")

from batteryhack.config import PROCESSED_DIR, ensure_data_dirs
from batteryhack.optimizer import BatteryParams
from batteryhack.price_impact import PRICE_IMPACT_SCENARIOS
from batteryhack.production_forecast import build_storage_aware_forecast, registry_to_dict


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train/select a live-safe DAM forecast model and export registry artifacts."
    )
    parser.add_argument("--target-date", default="2026-04-22")
    parser.add_argument("--history-days", type=int, default=21)
    parser.add_argument("--validation-days", type=int, default=3)
    parser.add_argument("--impact-scenario", default="Storage-aware medium impact")
    parser.add_argument("--registry-output", default="forecast_model_registry.json")
    parser.add_argument("--forecast-output", default="storage_aware_forecast.csv")
    args = parser.parse_args()

    ensure_data_dirs()
    target_date = date.fromisoformat(args.target_date)
    history_start = target_date - timedelta(days=args.history_days)
    impact = PRICE_IMPACT_SCENARIOS[args.impact_scenario]
    params = BatteryParams(
        power_mw=330,
        capacity_mwh=790,
        round_trip_efficiency=0.85,
        min_soc_pct=10,
        max_soc_pct=90,
        initial_soc_pct=50,
        terminal_soc_pct=50,
        degradation_cost_eur_mwh=4,
        max_cycles_per_day=1.5,
    )
    result = build_storage_aware_forecast(
        target_date=target_date,
        history_start=history_start,
        validation_days=args.validation_days,
        battery_params=params,
        impact_params=impact,
    )

    registry_payload = {
        "registry": registry_to_dict(result.registry),
        "metrics": result.metrics,
        "assumptions": result.assumptions,
    }
    registry_path = PROCESSED_DIR / args.registry_output
    registry_path.write_text(json.dumps(registry_payload, indent=2, default=_json_default))

    forecast_frame = result.base_forecast_frame[
        [
            "timestamp",
            "interval",
            "dam_price_eur_mwh",
            "forecast_price_eur_mwh",
            "forecast_low_eur_mwh",
            "forecast_high_eur_mwh",
        ]
    ].merge(
        result.storage_adjusted_frame[
            [
                "timestamp",
                "storage_adjusted_forecast_eur_mwh",
                "storage_price_adjustment_eur_mwh",
            ]
        ],
        on="timestamp",
        how="left",
    )
    forecast_path = PROCESSED_DIR / args.forecast_output
    forecast_frame.to_csv(forecast_path, index=False)

    print(f"Selected model: {result.registry.selected_model}")
    print(f"Saved {registry_path}")
    print(f"Saved {forecast_path}")


def _json_default(value):
    if hasattr(value, "item"):
        return value.item()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


if __name__ == "__main__":
    main()
