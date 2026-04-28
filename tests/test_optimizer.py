from __future__ import annotations

from datetime import date

import numpy as np

from batteryhack.optimizer import BatteryParams, optimize_battery_schedule
from batteryhack.synthetic import day_index


def test_flat_prices_stay_idle_with_degradation() -> None:
    market = day_index(date(2026, 4, 22))
    market["dam_price_eur_mwh"] = 80.0
    result = optimize_battery_schedule(
        market,
        BatteryParams(degradation_cost_eur_mwh=5.0),
    )
    assert result.metrics["charged_mwh"] < 1e-6
    assert result.metrics["discharged_mwh"] < 1e-6
    assert abs(result.metrics["net_revenue_eur"]) < 1e-6


def test_arbitrage_case_generates_positive_profit() -> None:
    market = day_index(date(2026, 4, 22))
    market["dam_price_eur_mwh"] = np.r_[np.full(48, 20.0), np.full(48, 160.0)]
    result = optimize_battery_schedule(
        market,
        BatteryParams(degradation_cost_eur_mwh=1.0),
    )
    assert result.metrics["net_revenue_eur"] > 0
    assert result.metrics["charged_mwh"] > 0
    assert result.metrics["discharged_mwh"] > 0
    assert result.schedule["soc_pct_end"].between(10, 90).all()


def test_power_and_soc_constraints_hold() -> None:
    market = day_index(date(2026, 4, 22))
    market["dam_price_eur_mwh"] = np.sin(np.linspace(0, 8 * np.pi, 96)) * 60 + 90
    params = BatteryParams(power_mw=7, capacity_mwh=21, degradation_cost_eur_mwh=2)
    result = optimize_battery_schedule(market, params)
    assert result.schedule["charge_mw"].max() <= params.power_mw + 1e-6
    assert result.schedule["discharge_mw"].max() <= params.power_mw + 1e-6
    assert result.schedule["soc_pct_end"].min() >= params.min_soc_pct - 1e-6
    assert result.schedule["soc_pct_end"].max() <= params.max_soc_pct + 1e-6
