from __future__ import annotations

from dataclasses import replace
from datetime import date

import numpy as np

from batteryhack.optimizer import BatteryParams, optimize_battery_schedule
from batteryhack.presets import BATTERY_PRESETS, METLEN_PRESET_NAME
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


def test_metlen_preset_values_are_valid() -> None:
    preset = BATTERY_PRESETS[METLEN_PRESET_NAME]
    params = preset.to_params()

    assert params.power_mw == 330.0
    assert params.capacity_mwh == 790.0
    assert round(preset.duration_hours, 2) == 2.39
    assert preset.usable_energy_mwh == 632.0
    assert params.min_soc_pct == 10.0
    assert params.max_soc_pct == 90.0
    assert params.round_trip_efficiency == 0.85


def test_metlen_scale_constraints_hold() -> None:
    market = day_index(date(2026, 4, 22))
    market["dam_price_eur_mwh"] = np.r_[
        np.full(24, 15.0),
        np.full(24, 110.0),
        np.full(24, 5.0),
        np.full(24, 180.0),
    ]
    params = BATTERY_PRESETS[METLEN_PRESET_NAME].to_params()

    result = optimize_battery_schedule(market, params)

    assert result.schedule["charge_mw"].max() <= 330.0 + 1e-6
    assert result.schedule["discharge_mw"].max() <= 330.0 + 1e-6
    assert result.schedule["soc_pct_end"].between(10.0 - 1e-6, 90.0 + 1e-6).all()


def test_cycle_limits_bind_for_daily_budgets() -> None:
    market = day_index(date(2026, 4, 22))
    market["dam_price_eur_mwh"] = np.tile(np.r_[np.full(16, 200.0), np.full(16, 0.0)], 3)

    for cycle_limit in (0.5, 1.0, 1.5):
        params = BatteryParams(
            power_mw=100.0,
            capacity_mwh=100.0,
            round_trip_efficiency=1.0,
            min_soc_pct=0.0,
            max_soc_pct=100.0,
            initial_soc_pct=100.0,
            terminal_soc_pct=100.0,
            degradation_cost_eur_mwh=0.0,
            max_cycles_per_day=cycle_limit,
        )
        result = optimize_battery_schedule(market, params)

        assert result.metrics["equivalent_cycles"] <= cycle_limit + 1e-6
        assert result.metrics["equivalent_cycles"] >= cycle_limit - 1e-6


def test_higher_efficiency_does_not_reduce_net_revenue() -> None:
    market = day_index(date(2026, 4, 22))
    market["dam_price_eur_mwh"] = np.r_[
        np.full(32, 20.0),
        np.full(32, 160.0),
        np.full(32, 35.0),
    ]
    base_params = replace(
        BATTERY_PRESETS[METLEN_PRESET_NAME].to_params(),
        max_cycles_per_day=1.5,
        degradation_cost_eur_mwh=5.0,
    )

    base = optimize_battery_schedule(
        market,
        replace(base_params, round_trip_efficiency=0.85),
    )
    optimistic = optimize_battery_schedule(
        market,
        replace(base_params, round_trip_efficiency=0.90),
    )

    assert optimistic.metrics["net_revenue_eur"] >= base.metrics["net_revenue_eur"] - 1e-6
