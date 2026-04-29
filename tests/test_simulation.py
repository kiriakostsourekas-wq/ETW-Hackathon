from __future__ import annotations

import os
from datetime import date, timedelta

import pandas as pd

os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")

from batteryhack.optimizer import BatteryParams
from batteryhack.simulation import (
    compare_forecast_models_walk_forward,
    run_dispatch_smoke_test,
    select_best_model,
    settle_schedule_on_actual_prices,
)
from batteryhack.synthetic import synthetic_market_day


def _synthetic_history(days: int = 18) -> pd.DataFrame:
    start = date(2026, 3, 1)
    frames = []
    for offset in range(days):
        frame = synthetic_market_day(start + timedelta(days=offset))
        frame["data_quality"] = "public price data"
        frame["delivery_date"] = start + timedelta(days=offset)
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def test_model_comparison_selects_trainable_ml_candidate() -> None:
    history = _synthetic_history(18)

    performance, daily = compare_forecast_models_walk_forward(
        history,
        date(2026, 3, 15),
        date(2026, 3, 17),
        model_candidates=("ridge", "hist_gradient_boosting"),
    )

    assert not performance.empty
    assert not daily.empty
    assert set(performance["model"]).issubset({"ridge", "hist_gradient_boosting"})
    assert select_best_model(performance) in {"ridge", "hist_gradient_boosting"}


def test_dispatch_smoke_settles_forecast_schedule_against_actual_prices() -> None:
    history = _synthetic_history(18)
    params = BatteryParams(power_mw=10, capacity_mwh=20, max_cycles_per_day=1.0)

    dispatch = run_dispatch_smoke_test(
        history,
        date(2026, 3, 17),
        date(2026, 3, 18),
        params,
        selected_model="ridge",
    )

    assert len(dispatch) == 2
    assert dispatch["realized_net_revenue_eur"].notna().all()
    assert dispatch["oracle_net_revenue_eur"].notna().all()
    assert dispatch["realized_equivalent_cycles"].le(1.0 + 1e-6).all()


def test_settlement_uses_actual_dam_prices_not_forecast_objective() -> None:
    market = synthetic_market_day(date(2026, 3, 1))
    schedule = market[["timestamp", "interval"]].copy()
    schedule["charge_mw"] = 0.0
    schedule["discharge_mw"] = 0.0
    schedule.loc[0, "charge_mw"] = 10.0
    schedule.loc[1, "discharge_mw"] = 10.0
    market["dam_price_eur_mwh"] = 100.0
    market.loc[1, "dam_price_eur_mwh"] = 200.0

    metrics = settle_schedule_on_actual_prices(
        schedule,
        market,
        BatteryParams(power_mw=10, capacity_mwh=20, degradation_cost_eur_mwh=0),
    )

    assert metrics["gross_revenue_eur"] == 250.0
    assert metrics["discharged_mwh"] == 2.5
