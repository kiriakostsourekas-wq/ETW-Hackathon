from datetime import date

import numpy as np
import pandas as pd

from batteryhack.market_impact import (
    MarketImpactThresholds,
    counterfactual_interval_price,
    reclear_curve,
    run_single_bess_market_impact,
)
from batteryhack.optimizer import BatteryParams
from batteryhack.synthetic import day_index


def _synthetic_curve(depth_multiplier: float = 1.0) -> pd.DataFrame:
    prices = np.arange(0.0, 201.0)
    slope = 20.0 * depth_multiplier
    return pd.DataFrame(
        {
            "price_eur_mwh": prices,
            "buy_mw": 6000.0 - slope * prices,
            "sell_mw": 2000.0 + slope * prices,
        }
    )


def test_baseline_reclear_matches_synthetic_mcp() -> None:
    assert reclear_curve(_synthetic_curve()) == 100.0


def test_charge_and_discharge_move_prices_in_expected_direction() -> None:
    curve = _synthetic_curve()

    charge = counterfactual_interval_price(curve, 100.0, charge_mw=330.0)
    discharge = counterfactual_interval_price(curve, 100.0, discharge_mw=330.0)

    assert charge["mcp_shift_eur_mwh"] > 0
    assert discharge["mcp_shift_eur_mwh"] < 0
    assert charge["counterfactual_price_eur_mwh"] >= 100.0
    assert discharge["counterfactual_price_eur_mwh"] <= 100.0


def test_larger_bess_action_has_greater_or_equal_shift() -> None:
    curve = _synthetic_curve()

    small = counterfactual_interval_price(curve, 100.0, charge_mw=100.0)
    large = counterfactual_interval_price(curve, 100.0, charge_mw=330.0)

    assert abs(large["mcp_shift_eur_mwh"]) >= abs(small["mcp_shift_eur_mwh"])


def test_zero_bess_action_has_zero_shift() -> None:
    result = counterfactual_interval_price(_synthetic_curve(), 100.0, charge_mw=0.0)

    assert result["mcp_shift_eur_mwh"] == 0.0
    assert result["counterfactual_price_eur_mwh"] == 100.0


def test_market_impact_summary_reports_threshold_decision() -> None:
    market = day_index(date(2026, 4, 22))
    market["dam_price_eur_mwh"] = 100.0
    market["load_forecast_mw"] = 6000.0
    schedule = market[["timestamp", "interval"]].copy()
    schedule["charge_mw"] = 0.0
    schedule["discharge_mw"] = 0.0
    schedule.loc[schedule["interval"].isin([1, 2]), "charge_mw"] = 330.0
    schedule.loc[schedule["interval"].isin([80, 81]), "discharge_mw"] = 330.0
    curves = {interval: _synthetic_curve() for interval in range(1, 97)}

    result = run_single_bess_market_impact(
        market=market,
        schedule=schedule,
        curves=curves,
        battery_params=BatteryParams(
            power_mw=330,
            capacity_mwh=790,
            round_trip_efficiency=0.85,
            degradation_cost_eur_mwh=4,
        ),
        thresholds=MarketImpactThresholds(),
    )

    summary = result.daily_summary.iloc[0]
    assert summary["median_abs_mcp_shift_eur_mwh"] > 0.5
    assert summary["p95_abs_mcp_shift_eur_mwh"] >= summary["median_abs_mcp_shift_eur_mwh"]
    assert "revenue_haircut_pct" in summary
    assert summary["decision"] == "material"


def test_missing_curve_coverage_marks_result_inconclusive() -> None:
    market = day_index(date(2026, 4, 22))
    market["dam_price_eur_mwh"] = 100.0
    schedule = market[["timestamp", "interval"]].copy()
    schedule["charge_mw"] = 330.0
    schedule["discharge_mw"] = 0.0

    result = run_single_bess_market_impact(
        market=market,
        schedule=schedule,
        curves={1: _synthetic_curve()},
        battery_params=BatteryParams(power_mw=330, capacity_mwh=790),
        thresholds=MarketImpactThresholds(),
    )

    summary = result.daily_summary.iloc[0]
    assert summary["valid_interval_share"] < 0.8
    assert summary["decision"] == "inconclusive"
