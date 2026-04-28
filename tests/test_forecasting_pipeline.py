from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from batteryhack.forecasting import (
    ForecastingError,
    assert_live_feature_columns,
    forecast_price_with_uncertainty,
    structural_price_forecast,
    walk_forward_forecast_backtest,
)
from batteryhack.synthetic import synthetic_market_day


def test_structural_forecast_does_not_require_target_prices() -> None:
    frame = synthetic_market_day(date(2026, 4, 22)).drop(columns=["dam_price_eur_mwh"])

    forecast = structural_price_forecast(frame)

    assert len(forecast) == 96
    assert forecast.notna().all()


def test_live_forecast_rejects_post_clearing_features() -> None:
    with pytest.raises(ForecastingError):
        assert_live_feature_columns(["load_forecast_mw", "dam_price_eur_mwh"])


def test_forecast_output_adds_uncertainty_without_history() -> None:
    target = synthetic_market_day(date(2026, 4, 22)).drop(columns=["dam_price_eur_mwh"])

    output = forecast_price_with_uncertainty(pd.DataFrame(), target)

    assert output.selected_model == "structural_proxy"
    assert output.frame["forecast_low_eur_mwh"].le(output.frame["forecast_price_eur_mwh"]).all()
    assert output.frame["forecast_high_eur_mwh"].ge(output.frame["forecast_price_eur_mwh"]).all()


def test_walk_forward_backtest_trains_only_on_prior_dates() -> None:
    history = pd.concat(
        [synthetic_market_day(date(2026, 4, 1) + timedelta(days=offset)) for offset in range(10)],
        ignore_index=True,
    )

    result = walk_forward_forecast_backtest(history, min_train_days=7, max_test_days=2)

    assert len(result) == 2
    assert (pd.to_datetime(result["train_until"]) < pd.to_datetime(result["delivery_date"])).all()
    assert result["mae_eur_mwh"].notna().all()
