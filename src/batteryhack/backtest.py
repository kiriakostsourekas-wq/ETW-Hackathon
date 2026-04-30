from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from .analytics import heuristic_threshold_schedule
from .data_sources import load_market_bundle
from .optimizer import BatteryParams, optimize_battery_schedule


def daterange(start_date: date, end_date: date):
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def run_backtest(
    start_date: date,
    end_date: date,
    params: BatteryParams,
    allow_synthetic: bool = True,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for delivery_date in daterange(start_date, end_date):
        bundle = load_market_bundle(delivery_date, allow_synthetic=allow_synthetic)
        optimized = optimize_battery_schedule(bundle.frame, params)
        heuristic = heuristic_threshold_schedule(bundle.frame, params.power_mw, params.capacity_mwh)
        rows.append(
            {
                "delivery_date": delivery_date.isoformat(),
                "net_revenue_eur": optimized.metrics["net_revenue_eur"],
                "gross_revenue_eur": optimized.metrics["gross_revenue_eur"],
                "degradation_cost_eur": optimized.metrics["degradation_cost_eur"],
                "heuristic_gross_revenue_eur": heuristic["heuristic_gross_revenue_eur"],
                "uplift_vs_heuristic_eur": optimized.metrics["gross_revenue_eur"]
                - heuristic["heuristic_gross_revenue_eur"],
                "charged_mwh": optimized.metrics["charged_mwh"],
                "discharged_mwh": optimized.metrics["discharged_mwh"],
                "equivalent_cycles": optimized.metrics["equivalent_cycles"],
                "captured_spread_eur_mwh": optimized.metrics["captured_spread_eur_mwh"],
                "used_public_dam": bundle.sources.get("DAM prices", "").startswith("https://"),
                "warning_count": len(bundle.warnings),
                "optional_unavailable_count": len(bundle.optional_unavailable),
            }
        )
    return pd.DataFrame(rows)
