from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from batteryhack.config import MTU_HOURS
from batteryhack.optimizer import BatteryParams, optimize_battery_schedule
from batteryhack.price_impact import (
    StorageImpactParams,
    adjust_prices_for_storage_feedback,
    optimize_with_storage_feedback,
)
from batteryhack.synthetic import day_index


def _two_block_market() -> pd.DataFrame:
    market = day_index(date(2026, 4, 22))
    market["dam_price_eur_mwh"] = np.r_[np.full(48, 20.0), np.full(48, 180.0)]
    return market


def _two_block_schedule() -> pd.DataFrame:
    market = day_index(date(2026, 4, 22))
    return market.assign(
        charge_mw=np.r_[np.full(24, 100.0), np.zeros(72)],
        discharge_mw=np.r_[np.zeros(72), np.full(24, 100.0)],
    )


def test_charging_intervals_do_not_lower_adjusted_prices() -> None:
    market = _two_block_market()
    schedule = _two_block_schedule()

    result = adjust_prices_for_storage_feedback(
        market,
        schedule,
        StorageImpactParams(
            fleet_power_mw=1000,
            fleet_energy_mwh=1000,
            reference_power_mw=100,
            charge_price_elasticity_eur_mwh_per_gw=12,
            discharge_price_elasticity_eur_mwh_per_gw=12,
            spread_compression_factor=0.15,
        ),
    )

    adjusted = result.frame["storage_adjusted_price_eur_mwh"].to_numpy(float)
    base = market["dam_price_eur_mwh"].to_numpy(float)
    charging = schedule["charge_mw"].to_numpy(float) > 0

    assert np.all(adjusted[charging] >= base[charging] - 1e-9)


def test_discharging_intervals_do_not_raise_adjusted_prices() -> None:
    market = _two_block_market()
    schedule = _two_block_schedule()

    result = adjust_prices_for_storage_feedback(
        market,
        schedule,
        StorageImpactParams(
            fleet_power_mw=1000,
            fleet_energy_mwh=1000,
            reference_power_mw=100,
            charge_price_elasticity_eur_mwh_per_gw=12,
            discharge_price_elasticity_eur_mwh_per_gw=12,
            spread_compression_factor=0.15,
        ),
    )

    adjusted = result.frame["storage_adjusted_price_eur_mwh"].to_numpy(float)
    base = market["dam_price_eur_mwh"].to_numpy(float)
    discharging = schedule["discharge_mw"].to_numpy(float) > 0

    assert np.all(adjusted[discharging] <= base[discharging] + 1e-9)


def test_zero_fleet_leaves_prices_unchanged() -> None:
    market = _two_block_market()
    schedule = _two_block_schedule()

    result = adjust_prices_for_storage_feedback(
        market,
        schedule,
        StorageImpactParams(
            fleet_power_mw=0,
            fleet_energy_mwh=0,
            reference_power_mw=100,
            spread_compression_factor=0.5,
        ),
    )

    assert np.allclose(
        result.frame["storage_adjusted_price_eur_mwh"],
        market["dam_price_eur_mwh"],
    )
    assert result.metrics["average_spread_compression_eur_mwh"] == 0.0


def test_high_impact_compresses_spreads_more_than_low_impact() -> None:
    market = _two_block_market()
    schedule = _two_block_schedule()
    low = adjust_prices_for_storage_feedback(
        market,
        schedule,
        StorageImpactParams(
            fleet_power_mw=1000,
            fleet_energy_mwh=1000,
            reference_power_mw=100,
            charge_price_elasticity_eur_mwh_per_gw=4,
            discharge_price_elasticity_eur_mwh_per_gw=5,
            spread_compression_factor=0.03,
        ),
    )
    high = adjust_prices_for_storage_feedback(
        market,
        schedule,
        StorageImpactParams(
            fleet_power_mw=1000,
            fleet_energy_mwh=1000,
            reference_power_mw=100,
            charge_price_elasticity_eur_mwh_per_gw=20,
            discharge_price_elasticity_eur_mwh_per_gw=22,
            spread_compression_factor=0.30,
        ),
    )

    assert (
        high.metrics["average_spread_compression_eur_mwh"]
        > low.metrics["average_spread_compression_eur_mwh"]
    )


def test_storage_aware_revenue_is_lower_on_synthetic_duck_curve() -> None:
    market = day_index(date(2026, 4, 22))
    market["dam_price_eur_mwh"] = np.r_[
        np.full(24, 65.0),
        np.full(32, 5.0),
        np.full(16, 85.0),
        np.full(24, 185.0),
    ]
    params = BatteryParams(
        power_mw=100,
        capacity_mwh=100,
        round_trip_efficiency=1.0,
        min_soc_pct=0,
        max_soc_pct=100,
        initial_soc_pct=100,
        terminal_soc_pct=100,
        degradation_cost_eur_mwh=0,
        max_cycles_per_day=1.0,
    )

    price_taker = optimize_battery_schedule(market, params)
    storage_aware = optimize_with_storage_feedback(
        market,
        params,
        StorageImpactParams(
            fleet_power_mw=1000,
            fleet_energy_mwh=1000,
            reference_power_mw=100,
            charge_price_elasticity_eur_mwh_per_gw=60,
            discharge_price_elasticity_eur_mwh_per_gw=70,
            spread_compression_factor=0.55,
        ),
        iterations=2,
    )

    adjusted_prices = storage_aware.adjusted_market[
        "storage_adjusted_price_eur_mwh"
    ].to_numpy(float)
    schedule = storage_aware.schedule
    storage_net = float(
        (
            adjusted_prices
            * (schedule["discharge_mw"].to_numpy(float) - schedule["charge_mw"].to_numpy(float))
            * MTU_HOURS
        ).sum()
    )

    assert storage_net < price_taker.metrics["net_revenue_eur"]
