from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from batteryhack.baseline import (
    BASELINE_JOIN_COLUMNS,
    BASELINE_PRICE_COL,
    UK_NAIVE_FALLBACK_METHOD,
    UK_NAIVE_PREVIOUS_DAY_METHOD,
    build_uk_naive_price_forecast,
    run_uk_naive_baseline_backtest,
    run_uk_naive_self_schedule_baseline,
)
from batteryhack.optimizer import BatteryParams
from batteryhack.presets import BATTERY_PRESETS, METLEN_PRESET_NAME
from batteryhack.synthetic import synthetic_market_day


def _history(start: date, days: int) -> pd.DataFrame:
    frames = []
    for offset in range(days):
        delivery_date = start + timedelta(days=offset)
        frame = synthetic_market_day(delivery_date)
        frame["data_quality"] = "public price data"
        frame["delivery_date"] = delivery_date
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def test_persistence_forecast_uses_previous_day_not_target_day() -> None:
    history = _history(date(2026, 4, 1), 4)
    previous_mask = history["timestamp"].dt.date == date(2026, 4, 3)
    target_mask = history["timestamp"].dt.date == date(2026, 4, 4)
    history.loc[previous_mask, "dam_price_eur_mwh"] = history.loc[previous_mask, "interval"] * 1.0
    history.loc[target_mask, "dam_price_eur_mwh"] = 999.0

    forecast = build_uk_naive_price_forecast(history, date(2026, 4, 4))

    assert forecast.method == UK_NAIVE_PREVIOUS_DAY_METHOD
    assert forecast.source_dates == ("2026-04-03",)
    assert len(forecast.frame) == 96
    assert forecast.frame[BASELINE_PRICE_COL].tolist() == [float(i) for i in range(1, 97)]


def test_persistence_forecast_falls_back_to_prior_valid_interval_median() -> None:
    history = _history(date(2026, 4, 1), 5)
    history.loc[history["timestamp"].dt.date == date(2026, 4, 4), "data_quality"] = (
        "synthetic price fallback"
    )
    for delivery_date, value in [
        (date(2026, 4, 1), 10.0),
        (date(2026, 4, 2), 20.0),
        (date(2026, 4, 3), 30.0),
    ]:
        history.loc[history["timestamp"].dt.date == delivery_date, "dam_price_eur_mwh"] = value

    forecast = build_uk_naive_price_forecast(history, date(2026, 4, 5))

    assert forecast.method == UK_NAIVE_FALLBACK_METHOD
    assert forecast.source_dates == ("2026-04-03", "2026-04-02", "2026-04-01")
    assert forecast.frame[BASELINE_PRICE_COL].eq(20.0).all()


def test_baseline_optimizer_respects_metlen_constraints() -> None:
    history = _history(date(2026, 4, 1), 3)
    target = history[history["timestamp"].dt.date == date(2026, 4, 3)].copy()
    params = BATTERY_PRESETS[METLEN_PRESET_NAME].to_params()

    result = run_uk_naive_self_schedule_baseline(history, target, params)
    schedule = result.schedule

    assert schedule["charge_mw"].max() <= params.power_mw + 1e-6
    assert schedule["discharge_mw"].max() <= params.power_mw + 1e-6
    assert schedule["soc_pct_end"].between(params.min_soc_pct - 1e-6, params.max_soc_pct + 1e-6).all()
    assert abs(schedule["soc_pct_end"].iloc[-1] - params.terminal_soc_pct) < 1e-6
    assert result.metrics["baseline_equivalent_cycles"] <= params.max_cycles_per_day + 1e-6


def test_flat_persistence_forecast_with_degradation_keeps_battery_idle() -> None:
    history = _history(date(2026, 4, 1), 2)
    history["dam_price_eur_mwh"] = 50.0
    target = history[history["timestamp"].dt.date == date(2026, 4, 2)].copy()
    params = BatteryParams(
        power_mw=10,
        capacity_mwh=20,
        round_trip_efficiency=0.9,
        degradation_cost_eur_mwh=5,
        max_cycles_per_day=1.0,
    )

    result = run_uk_naive_self_schedule_baseline(history, target, params)

    assert result.schedule["charge_mw"].sum() == 0.0
    assert result.schedule["discharge_mw"].sum() == 0.0
    assert result.metrics["baseline_realized_net_revenue_eur"] == 0.0


def test_baseline_backtest_drops_synthetic_target_days_by_default() -> None:
    history = _history(date(2026, 4, 1), 4)
    history.loc[history["timestamp"].dt.date == date(2026, 4, 3), "data_quality"] = (
        "synthetic price fallback"
    )
    params = BatteryParams(power_mw=10, capacity_mwh=20, max_cycles_per_day=1.0)

    result = run_uk_naive_baseline_backtest(
        history,
        date(2026, 4, 2),
        date(2026, 4, 4),
        params,
    )

    assert result["delivery_date"].tolist() == ["2026-04-02", "2026-04-04"]


def test_uk_naive_fallback_ignores_target_and_future_prices() -> None:
    history = _history(date(2026, 4, 1), 5)
    history.loc[history["timestamp"].dt.date == date(2026, 4, 2), "dam_price_eur_mwh"] = 20.0
    history.loc[history["timestamp"].dt.date == date(2026, 4, 3), "data_quality"] = (
        "synthetic price fallback"
    )
    history.loc[history["timestamp"].dt.date == date(2026, 4, 4), "dam_price_eur_mwh"] = 999.0
    history.loc[history["timestamp"].dt.date == date(2026, 4, 5), "dam_price_eur_mwh"] = -999.0

    forecast = build_uk_naive_price_forecast(history, date(2026, 4, 4), fallback_days=1)

    assert forecast.method == UK_NAIVE_FALLBACK_METHOD
    assert forecast.source_dates == ("2026-04-02",)
    assert forecast.frame[BASELINE_PRICE_COL].eq(20.0).all()


def test_baseline_backtest_exposes_ml_joinable_columns() -> None:
    history = _history(date(2026, 4, 1), 3)
    params = BatteryParams(power_mw=10, capacity_mwh=20, max_cycles_per_day=1.0)

    result = run_uk_naive_baseline_backtest(
        history,
        date(2026, 4, 2),
        date(2026, 4, 3),
        params,
    )

    assert not result.empty
    assert set(BASELINE_JOIN_COLUMNS).issubset(result.columns)
    assert result["benchmark"].eq("uk_naive_baseline").all()
    assert result["forecast_mae_eur_mwh"].equals(result["baseline_forecast_mae_eur_mwh"])
    assert result["realized_net_revenue_eur"].equals(result["baseline_realized_net_revenue_eur"])
