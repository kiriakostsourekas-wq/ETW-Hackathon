from datetime import date
from types import SimpleNamespace

from batteryhack import synthetic
from batteryhack.api_server import DEFAULT_ASSET, build_dashboard_payload
from batteryhack.data_sources import MarketBundle
from batteryhack.forecasting import forecast_quality_metrics
from batteryhack.optimizer import optimize_battery_schedule
from batteryhack.production_forecast import ForecastModelRegistry


def test_dashboard_payload_contract(monkeypatch):
    delivery_date = date(2026, 4, 22)
    market = synthetic.synthetic_market_day(delivery_date)

    def fake_loader(_delivery_date):
        return MarketBundle(
            frame=market,
            sources={"DAM prices": "Synthetic test fixture"},
            warnings=[],
        )

    monkeypatch.setattr("batteryhack.api_server.load_market_bundle", fake_loader)

    payload = build_dashboard_payload(delivery_date, DEFAULT_ASSET, include_forecast=False)

    assert payload["delivery_date"] == "2026-04-22"
    assert payload["asset"]["duration_hours"] == 2.39
    assert len(payload["series"]) == 96
    assert len(payload["kpis"]) == 4
    assert payload["metrics"]["discharged_mwh"] >= 0
    assert payload["metrics"]["charged_mwh"] >= 0
    assert "dam_price_eur_mwh" in payload["series"][0]


def test_dashboard_payload_includes_forecast_contract(monkeypatch):
    delivery_date = date(2026, 4, 22)
    market = synthetic.synthetic_market_day(delivery_date)

    def fake_loader(_delivery_date):
        return MarketBundle(
            frame=market,
            sources={"DAM prices": "Synthetic test fixture"},
            warnings=[],
        )

    forecast_frame = market.copy()
    forecast_frame["forecast_price_eur_mwh"] = forecast_frame["dam_price_eur_mwh"] * 0.98
    forecast_frame["forecast_low_eur_mwh"] = forecast_frame["forecast_price_eur_mwh"] - 10
    forecast_frame["forecast_high_eur_mwh"] = forecast_frame["forecast_price_eur_mwh"] + 10
    adjusted_frame = forecast_frame.copy()
    adjusted_frame["storage_adjusted_forecast_eur_mwh"] = (
        adjusted_frame["forecast_price_eur_mwh"] * 0.97
    )
    adjusted_frame["storage_price_adjustment_eur_mwh"] = (
        adjusted_frame["storage_adjusted_forecast_eur_mwh"]
        - adjusted_frame["forecast_price_eur_mwh"]
    )
    base_schedule = optimize_battery_schedule(
        forecast_frame,
        DEFAULT_ASSET,
        price_col="forecast_price_eur_mwh",
    ).schedule
    storage_schedule = optimize_battery_schedule(
        adjusted_frame,
        DEFAULT_ASSET,
        price_col="storage_adjusted_forecast_eur_mwh",
    ).schedule
    quality = forecast_quality_metrics(
        market["dam_price_eur_mwh"],
        forecast_frame["forecast_price_eur_mwh"],
    )
    fake_registry = ForecastModelRegistry(
        selected_model="ridge",
        target_date="2026-04-22",
        training_start="2026-04-01",
        training_end="2026-04-21",
        validation_start="2026-04-19",
        validation_end="2026-04-21",
        training_rows=21 * 96,
        feature_columns=("load_forecast_mw", "res_forecast_mw"),
        candidate_models=("ridge",),
        selected_metrics={"model": "ridge", **quality},
        leakage_audit={"live_safe": True},
        source_summary={"days": 22, "public_price_days": 22, "synthetic_price_days": 0},
    )

    fake_production = SimpleNamespace(
        registry=fake_registry,
        base_forecast_frame=forecast_frame,
        base_schedule=base_schedule,
        storage_adjusted_frame=adjusted_frame,
        storage_schedule=storage_schedule,
        model_performance=market.head(0),
        daily_model_performance=market.head(0),
        metrics={
            "base_forecast_mae_eur_mwh": quality["mae_eur_mwh"],
            "base_forecast_rmse_eur_mwh": quality["rmse_eur_mwh"],
            "base_top_quartile_accuracy": quality["top_quartile_accuracy"],
            "base_bottom_quartile_accuracy": quality["bottom_quartile_accuracy"],
            "base_spread_direction_accuracy": quality["spread_direction_accuracy"],
            "storage_aware_objective_net_revenue_eur": 1000.0,
            "storage_aware_capture_ratio_vs_oracle": 0.8,
            "impact_spread_compression_pct": 4.0,
            "impact_average_spread_compression_eur_mwh": 5.5,
        },
        assumptions={"impact_scenario": "Storage-aware medium impact"},
    )

    monkeypatch.setattr("batteryhack.api_server.load_market_bundle", fake_loader)
    monkeypatch.setattr(
        "batteryhack.api_server.build_storage_aware_forecast",
        lambda **_: fake_production,
    )

    payload = build_dashboard_payload(delivery_date, DEFAULT_ASSET)

    assert payload["forecasting"]["available"] is True
    assert payload["forecasting"]["registry"]["selected_model"] == "ridge"
    assert "forecast_price_eur_mwh" in payload["series"][0]
    assert "storage_adjusted_forecast_eur_mwh" in payload["series"][0]
    assert len(payload["kpis"]) == 4
