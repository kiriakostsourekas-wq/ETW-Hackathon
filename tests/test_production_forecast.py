from datetime import date, timedelta

import pandas as pd

from batteryhack.optimizer import BatteryParams
import batteryhack.production_forecast as production_forecast
from batteryhack.production_forecast import build_price_taker_forecast
from batteryhack.simulation import MarketHistory
from batteryhack.synthetic import synthetic_market_day


def test_price_taker_forecast_returns_registry_and_96_rows(monkeypatch):
    start = date(2026, 4, 1)
    target = date(2026, 4, 22)
    frame = pd.concat(
        [synthetic_market_day(start + timedelta(days=offset)) for offset in range(22)],
        ignore_index=True,
    )
    frame["delivery_date"] = frame["timestamp"].dt.date
    frame["data_quality"] = "public price data"

    def fake_history(_start_date, _end_date, allow_synthetic=True):
        return MarketHistory(
            frame=frame,
            source_summary={"days": 22, "public_price_days": 22, "synthetic_price_days": 0},
            warnings=(),
        )

    optimizer_calls = 0
    real_optimizer = production_forecast.optimize_battery_schedule

    def counting_optimizer(*args, **kwargs):
        nonlocal optimizer_calls
        optimizer_calls += 1
        return real_optimizer(*args, **kwargs)

    monkeypatch.setattr("batteryhack.production_forecast.load_market_history", fake_history)
    monkeypatch.setattr(
        "batteryhack.production_forecast.optimize_battery_schedule",
        counting_optimizer,
    )

    result = build_price_taker_forecast(
        target,
        BatteryParams(
            power_mw=50,
            capacity_mwh=100,
            round_trip_efficiency=0.9,
            max_cycles_per_day=1.0,
        ),
        history_start=start,
        validation_days=2,
        model_candidates=("interval_profile", "ridge"),
    )

    assert result.registry.selected_model in {"interval_profile", "ridge"}
    assert result.registry.leakage_audit["live_safe"] is True
    assert len(result.forecast_frame) == 96
    assert len(result.schedule) == 96
    assert optimizer_calls == 1
    assert "storage_adjusted_forecast_eur_mwh" not in result.forecast_frame
    assert result.metrics["base_forecast_mae_eur_mwh"] >= 0
    assert result.metrics["price_taker_objective_net_revenue_eur"] is not None
