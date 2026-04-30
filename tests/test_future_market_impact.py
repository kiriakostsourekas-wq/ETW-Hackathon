from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd

from batteryhack.future_market_impact import (
    FutureBessScenario,
    apply_future_price_scenario,
    build_future_headline_artifact,
    get_future_bess_scenarios,
    interpretation_label_for_future_impact,
    normalize_future_market_input,
    write_future_headline_json,
    simulate_future_market_impact,
)
from batteryhack.optimizer import BatteryParams
from batteryhack.synthetic import day_index


def _scenario(
    *,
    spread_compression_pct: float = 0.0,
    responsive_fleet_share: float = 0.0,
) -> FutureBessScenario:
    return FutureBessScenario(
        name="test",
        target_year=2031,
        installed_power_mw=100.0,
        installed_energy_mwh=400.0,
        spread_compression_pct=spread_compression_pct,
        responsive_fleet_share=responsive_fleet_share,
        market_depth_mw_per_eur_mwh=100.0,
        max_fleet_shift_eur_mwh=20.0,
        source_fields=("source capacity",),
        inference_fields=("test inference",),
    )


def test_spread_compression_is_deterministic_and_centered_on_median() -> None:
    market = day_index(date(2026, 4, 22)).head(4)
    market["dam_price_eur_mwh"] = [20.0, 60.0, 100.0, 140.0]
    scenario = _scenario(spread_compression_pct=0.25)

    projected = apply_future_price_scenario(market, scenario)

    assert projected["future_price_eur_mwh"].round(6).tolist() == [35.0, 65.0, 95.0, 125.0]
    assert projected["future_price_eur_mwh"].max() - projected["future_price_eur_mwh"].min() == 90.0


def test_fleet_response_raises_low_prices_and_suppresses_high_prices() -> None:
    market = day_index(date(2026, 4, 22)).head(4)
    market["dam_price_eur_mwh"] = [0.0, 10.0, 100.0, 110.0]
    scenario = _scenario(responsive_fleet_share=1.0)

    projected = apply_future_price_scenario(market, scenario)

    low = projected.loc[projected["base_price_eur_mwh"] == 0.0].iloc[0]
    high = projected.loc[projected["base_price_eur_mwh"] == 110.0].iloc[0]
    assert low["future_price_eur_mwh"] > low["base_price_eur_mwh"]
    assert low["storage_response_mode"] == "fleet_charging"
    assert high["future_price_eur_mwh"] < high["base_price_eur_mwh"]
    assert high["storage_response_mode"] == "fleet_discharging"


def test_interval_simulation_reports_pnl_degradation_and_reoptimization() -> None:
    market = day_index(date(2026, 4, 22))
    market["dam_price_eur_mwh"] = np.r_[np.full(48, 20.0), np.full(48, 140.0)]
    params = BatteryParams(
        power_mw=10.0,
        capacity_mwh=20.0,
        round_trip_efficiency=1.0,
        min_soc_pct=0.0,
        max_soc_pct=100.0,
        initial_soc_pct=0.0,
        terminal_soc_pct=0.0,
        degradation_cost_eur_mwh=0.0,
        max_cycles_per_day=1.0,
    )
    scenario = _scenario(spread_compression_pct=0.5)

    result = simulate_future_market_impact(
        market,
        scenarios=(scenario,),
        battery_params=params,
    )
    summary = result.scenario_summary.iloc[0]

    assert summary["base_schedule_net_revenue_eur"] > 0
    assert summary["fixed_schedule_pnl_degradation_pct"] == 50.0
    assert summary["reoptimized_pnl_degradation_pct"] == 50.0
    assert summary["method"] == "interval_price_reoptimized"
    assert not result.interval_impacts.empty


def test_backtest_summary_proxy_is_marked_as_proxy() -> None:
    backtest = pd.DataFrame(
        {
            "delivery_date": ["2026-04-22"],
            "net_revenue_eur": [1000.0],
            "captured_spread_eur_mwh": [80.0],
        }
    )
    scenario = _scenario(spread_compression_pct=0.25)

    result = simulate_future_market_impact(backtest, scenarios=(scenario,))
    summary = result.scenario_summary.iloc[0]

    assert result.interval_impacts.empty
    assert summary["method"] == "backtest_summary_proxy"
    assert summary["fixed_schedule_future_net_revenue_eur"] == 750.0
    assert summary["fixed_schedule_pnl_degradation_pct"] == 25.0


def test_ml_prediction_schema_uses_actual_price_and_groups_by_model() -> None:
    timestamps = pd.date_range("2026-04-22", periods=4, freq="15min")
    rows = []
    for model in ("ridge", "extra_trees"):
        for interval, timestamp, price in zip(
            range(1, 5),
            timestamps,
            [20.0, 20.0, 140.0, 140.0],
            strict=True,
        ):
            rows.append(
                {
                    "delivery_date": "2026-04-22",
                    "model": model,
                    "timestamp": timestamp,
                    "interval": interval,
                    "actual_price_eur_mwh": price,
                    "forecast_price_eur_mwh": price,
                    "charge_mw": 10.0 if interval <= 2 else 0.0,
                    "discharge_mw": 10.0 if interval >= 3 else 0.0,
                }
            )
    predictions = pd.DataFrame(rows)
    params = BatteryParams(
        power_mw=10.0,
        capacity_mwh=10.0,
        round_trip_efficiency=1.0,
        min_soc_pct=0.0,
        max_soc_pct=100.0,
        initial_soc_pct=0.0,
        terminal_soc_pct=0.0,
        degradation_cost_eur_mwh=0.0,
    )

    result = simulate_future_market_impact(
        predictions,
        scenarios=(_scenario(spread_compression_pct=0.25),),
        battery_params=params,
    )

    assert sorted(result.scenario_summary["input_strategy"].unique()) == [
        "extra_trees",
        "ridge",
    ]
    assert len(result.scenario_summary) == 2
    assert set(result.interval_impacts["input_strategy"]) == {"ridge", "extra_trees"}
    assert result.scenario_summary["fixed_schedule_pnl_degradation_pct"].eq(25.0).all()


def test_normalizer_builds_timestamp_from_delivery_date_and_interval() -> None:
    frame = pd.DataFrame(
        {
            "delivery_date": ["2026-04-22", "2026-04-22"],
            "interval": [1, 2],
            "actual_price_eur_mwh": [40.0, 60.0],
        }
    )

    normalized = normalize_future_market_input(frame)

    assert normalized["timestamp"].dt.strftime("%H:%M").tolist() == ["00:00", "00:15"]
    assert normalized["dam_price_eur_mwh"].tolist() == [40.0, 60.0]
    assert normalized["_input_strategy"].tolist() == ["input", "input"]


def test_default_scenarios_keep_source_and_inference_fields_separate() -> None:
    scenarios = get_future_bess_scenarios()

    assert [scenario.name for scenario in scenarios] == [
        "conservative",
        "base",
        "aggressive",
    ]
    assert all(scenario.source_fields for scenario in scenarios)
    assert all(scenario.inference_fields for scenario in scenarios)


def test_future_headline_labels_use_deterministic_thresholds() -> None:
    assert (
        interpretation_label_for_future_impact(12.0, 12.0, 0.0)
        == "spread compression risk"
    )
    assert (
        interpretation_label_for_future_impact(35.0, 10.0, 500.0)
        == "redispatch partially offsets compression"
    )
    assert (
        interpretation_label_for_future_impact(16.0, -2.0, 750.0)
        == "redispatch improves this sample day"
    )
    assert (
        interpretation_label_for_future_impact(60.0, 20.0, 1000.0)
        == "severe compression stress"
    )
    assert (
        interpretation_label_for_future_impact(30.0, 35.0, -100.0)
        == "severe compression stress"
    )


def test_future_headline_artifact_aggregates_by_strategy_and_scenario() -> None:
    summary = pd.DataFrame(
        {
            "delivery_date": ["2026-04-22", "2026-04-23"],
            "input_strategy": ["ridge", "ridge"],
            "scenario": ["base", "base"],
            "base_schedule_net_revenue_eur": [1000.0, 500.0],
            "fixed_schedule_future_net_revenue_eur": [700.0, 350.0],
            "reoptimized_future_net_revenue_eur": [900.0, 450.0],
        }
    )

    artifact = build_future_headline_artifact(
        summary,
        input_path="data/processed/ml_research_predictions.csv",
        generated_at="2026-04-30T00:00:00Z",
    )

    assert artifact["input_file"] == "data/processed/ml_research_predictions.csv"
    assert artifact["notice"] == (
        "Strategic spread-compression stress test only; not a Greek price forecast."
    )
    assert len(artifact["rows"]) == 1
    row = artifact["rows"][0]
    assert row == {
        "strategy_model": "ridge",
        "scenario": "base",
        "fixed_schedule_degradation_pct": 30.0,
        "reoptimized_degradation_pct": 10.0,
        "reoptimization_recovery_eur": 300.0,
        "interpretation_label": "redispatch partially offsets compression",
        "sample_days": 2,
    }


def test_future_headline_json_generation_writes_clean_json(tmp_path) -> None:
    summary = pd.DataFrame(
        {
            "delivery_date": ["2026-04-22"],
            "input_strategy": ["input"],
            "scenario": ["aggressive"],
            "base_schedule_net_revenue_eur": [1000.0],
            "fixed_schedule_future_net_revenue_eur": [350.0],
            "reoptimized_future_net_revenue_eur": [600.0],
        }
    )
    output_path = tmp_path / "future_market_impact_headline.json"

    artifact = write_future_headline_json(
        summary,
        output_path,
        input_path="data/processed/price_taker_forecast.csv",
        generated_at="2026-04-30T00:00:00Z",
    )

    loaded = json.loads(output_path.read_text(encoding="utf-8"))
    assert artifact["rows"][0]["interpretation_label"] == "severe compression stress"
    assert loaded["input_file"] == "data/processed/price_taker_forecast.csv"
    assert loaded["preferred_input_file"] == (
        "data/processed/strategy_comparison_intervals.csv"
    )
