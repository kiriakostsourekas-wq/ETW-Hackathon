import json
from datetime import date
from types import SimpleNamespace

from batteryhack import synthetic
from batteryhack.api_server import DEFAULT_ASSET, build_dashboard_payload
from batteryhack.data_sources import MarketBundle
from batteryhack.forecasting import forecast_quality_metrics
from batteryhack.optimizer import optimize_battery_schedule
from batteryhack.production_forecast import ForecastModelRegistry


def test_dashboard_payload_contract(monkeypatch, tmp_path):
    delivery_date = date(2026, 4, 22)
    market = synthetic.synthetic_market_day(delivery_date)

    def fake_loader(_delivery_date):
        return MarketBundle(
            frame=market,
            sources={"DAM prices": "Synthetic test fixture"},
            warnings=[],
        )

    monkeypatch.setattr("batteryhack.api_server.load_market_bundle", fake_loader)
    monkeypatch.setattr("batteryhack.api_server.PROCESSED_DATA_DIR", tmp_path)

    payload = build_dashboard_payload(delivery_date, DEFAULT_ASSET, include_forecast=False)

    assert payload["delivery_date"] == "2026-04-22"
    assert payload["asset"]["duration_hours"] == 2.39
    assert len(payload["series"]) == 96
    assert len(payload["kpis"]) == 4
    assert payload["metrics"]["discharged_mwh"] >= 0
    assert payload["metrics"]["charged_mwh"] >= 0
    assert "dam_price_eur_mwh" in payload["series"][0]
    assert payload["evidence"]["available"] is False
    assert "strategy_comparison_headline.json" in payload["evidence"]["missing_artifacts"]


def test_dashboard_payload_includes_processed_evidence(monkeypatch, tmp_path):
    delivery_date = date(2026, 4, 22)
    market = synthetic.synthetic_market_day(delivery_date)

    def fake_loader(_delivery_date):
        return MarketBundle(
            frame=market,
            sources={"DAM prices": "Synthetic test fixture"},
            warnings=[],
        )

    (tmp_path / "strategy_comparison_headline.json").write_text(
        json.dumps(
            {
                "evaluated_days": 38,
                "best_model": "scarcity_ensemble",
                "best_ml_strategy": "ml_scarcity_ensemble",
                "ml_total_pnl_eur": 2878632.17,
                "uk_baseline_total_pnl_eur": 2571165.35,
                "uplift_eur": 65.0,
                "uplift_pct": 0.1196,
                "win_rate_vs_uk_baseline": 0.7368,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "strategy_comparison_summary.csv").write_text(
        "\n".join(
            [
                "strategy,model_or_method,days,total_realized_net_revenue_eur",
                "ml_ridge,ridge,38,2878632.17",
                "uk_naive_baseline,uk_naive_previous_day_persistence,37,2513067.41",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "strategy_comparison_daily.csv").write_text(
        "\n".join(
            [
                "delivery_date,strategy,model_or_method,realized_net_revenue_eur",
                "2026-03-22,ml_scarcity_ensemble,scarcity_ensemble,100",
                "2026-03-22,uk_naive_baseline,uk_naive_previous_day_persistence,70",
                "2026-03-22,uk_naive_baseline,uk_naive_same_day_shape,5",
                "2026-03-23,ml_scarcity_ensemble,scarcity_ensemble,120",
                "2026-03-23,uk_naive_baseline,uk_naive_previous_day_persistence,80",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "ml_research_model_stability.csv").write_text(
        "\n".join(
            [
                "criterion,winning_model,runner_up_model,margin_vs_runner_up",
                "total_pnl,ridge,extra_trees,7966.10",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "ml_research_paired_uplift.csv").write_text(
        "\n".join(
            [
                "primary_model,comparison_model,paired_days,total_pnl_uplift_eur,primary_win_days,comparison_win_days",
                "ridge,extra_trees,38,7966.10,14,24",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "future_market_impact_headline.json").write_text(
        json.dumps(
            {
                "notice": "Strategic spread-compression stress test only; not a Greek price forecast.",
                "rows": [
                    {
                        "strategy_model": "ml_ridge",
                        "scenario": "base",
                        "fixed_schedule_degradation_pct": 38.4,
                        "reoptimized_degradation_pct": 19.8,
                        "reoptimization_recovery_eur": 535458.87,
                        "interpretation_label": "redispatch partially offsets compression",
                        "sample_days": 38,
                    },
                    {
                        "strategy_model": "ml_scarcity_ensemble",
                        "scenario": "base",
                        "fixed_schedule_degradation_pct": 38.3,
                        "reoptimized_degradation_pct": 22.3,
                        "reoptimization_recovery_eur": 476148.98,
                        "interpretation_label": "redispatch partially offsets compression",
                        "sample_days": 38,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("batteryhack.api_server.load_market_bundle", fake_loader)
    monkeypatch.setattr("batteryhack.api_server.PROCESSED_DATA_DIR", tmp_path)

    payload = build_dashboard_payload(delivery_date, DEFAULT_ASSET, include_forecast=False)
    evidence = payload["evidence"]

    assert evidence["available"] is True
    assert evidence["partial"] is False
    assert evidence["missing_artifacts"] == []
    assert evidence["strategy_comparison"]["headline"]["best_model"] == "scarcity_ensemble"
    assert len(evidence["strategy_comparison"]["summary"]) == 2
    cumulative_pnl = evidence["strategy_comparison"]["cumulative_pnl"]
    assert len(cumulative_pnl) == 2
    assert {
        "delivery_date",
        "ml_daily_pnl_eur",
        "baseline_daily_pnl_eur",
        "ml_cumulative_pnl_eur",
        "baseline_cumulative_pnl_eur",
        "daily_uplift_eur",
        "cumulative_uplift_eur",
    }.issubset(cumulative_pnl[0])
    assert cumulative_pnl[0]["baseline_daily_pnl_eur"] == 75
    assert cumulative_pnl[-1]["ml_cumulative_pnl_eur"] == 220
    assert cumulative_pnl[-1]["baseline_cumulative_pnl_eur"] == 155
    assert cumulative_pnl[-1]["cumulative_uplift_eur"] == evidence["strategy_comparison"]["headline"]["uplift_eur"]
    assert evidence["model_stability"][0]["winning_model"] == "ridge"
    assert evidence["paired_uplift"][0]["primary_win_days"] == 14
    assert evidence["future_market_impact"]["notice"].endswith("not a Greek price forecast.")
    assert evidence["future_market_impact"]["strategy_model"] == "ml_scarcity_ensemble"
    assert evidence["future_market_impact"]["scenarios"][0]["scenario"] == "base"


def test_dashboard_payload_includes_forecast_contract(monkeypatch, tmp_path):
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
    base_schedule = optimize_battery_schedule(
        forecast_frame,
        DEFAULT_ASSET,
        price_col="forecast_price_eur_mwh",
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
        forecast_frame=forecast_frame,
        schedule=base_schedule,
        model_performance=market.head(0),
        daily_model_performance=market.head(0),
        metrics={
            "base_forecast_mae_eur_mwh": quality["mae_eur_mwh"],
            "base_forecast_rmse_eur_mwh": quality["rmse_eur_mwh"],
            "base_top_quartile_accuracy": quality["top_quartile_accuracy"],
            "base_bottom_quartile_accuracy": quality["bottom_quartile_accuracy"],
            "base_spread_direction_accuracy": quality["spread_direction_accuracy"],
            "price_taker_objective_net_revenue_eur": 1000.0,
            "price_taker_realized_net_revenue_eur": 900.0,
            "price_taker_capture_ratio_vs_oracle": 0.8,
        },
        assumptions={"market_impact_status": "offline experiment only"},
    )

    monkeypatch.setattr("batteryhack.api_server.load_market_bundle", fake_loader)
    monkeypatch.setattr("batteryhack.api_server.PROCESSED_DATA_DIR", tmp_path)
    monkeypatch.setattr(
        "batteryhack.api_server.build_price_taker_forecast",
        lambda **_: fake_production,
    )

    payload = build_dashboard_payload(delivery_date, DEFAULT_ASSET)

    assert payload["forecasting"]["available"] is True
    assert payload["forecasting"]["registry"]["selected_model"] == "ridge"
    assert "forecast_price_eur_mwh" in payload["series"][0]
    assert "storage_adjusted_forecast_eur_mwh" not in payload["series"][0]
    assert "storage_charge_mw" not in payload["series"][0]
    assert "price_taker_objective_net_revenue_eur" in payload["forecasting"]["metrics"]
    assert len(payload["kpis"]) == 4
