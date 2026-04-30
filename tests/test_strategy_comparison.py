from __future__ import annotations

from datetime import date, timedelta
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from batteryhack.optimizer import BatteryParams
from batteryhack.strategy_comparison import (
    DAILY_OUTPUT_SCHEMA,
    HEADLINE_OUTPUT_KEYS,
    INTERVAL_OUTPUT_SCHEMA,
    SUMMARY_OUTPUT_SCHEMA,
    build_headline_frame,
    build_headline_report,
    build_strategy_comparison,
    run_uk_naive_baseline_for_comparison,
)
from batteryhack.synthetic import synthetic_market_day


def _ml_daily() -> pd.DataFrame:
    rows = []
    for delivery_date, ridge_pnl, trees_pnl in [
        ("2026-03-22", 150.0, 90.0),
        ("2026-03-23", 180.0, 220.0),
        ("2026-03-24", 999.0, 999.0),
    ]:
        for model, pnl in [("ridge", ridge_pnl), ("extra_trees", trees_pnl)]:
            rows.append(
                {
                    "delivery_date": delivery_date,
                    "model": model,
                    "mae_eur_mwh": 10.0 if model == "ridge" else 12.0,
                    "rmse_eur_mwh": 14.0 if model == "ridge" else 16.0,
                    "spread_direction_accuracy": 0.7,
                    "realized_net_revenue_eur": pnl,
                    "oracle_net_revenue_eur": 300.0,
                    "capture_ratio_vs_oracle": pnl / 300.0,
                    "realized_charged_mwh": 20.0,
                    "realized_discharged_mwh": 18.0,
                    "realized_equivalent_cycles": 0.9,
                    "realized_captured_spread_eur_mwh": 40.0,
                }
            )
    return pd.DataFrame(rows)


def _baseline_daily() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "delivery_date": "2026-03-22",
                "baseline_method": "uk_naive_previous_day_persistence",
                "baseline_forecast_mae_eur_mwh": 20.0,
                "baseline_forecast_rmse_eur_mwh": 25.0,
                "baseline_spread_direction_accuracy": 0.55,
                "baseline_realized_net_revenue_eur": 100.0,
                "oracle_net_revenue_eur": 300.0,
                "baseline_capture_ratio_vs_oracle": 1 / 3,
                "baseline_charged_mwh": 19.0,
                "baseline_discharged_mwh": 17.0,
                "baseline_equivalent_cycles": 0.85,
                "baseline_captured_spread_eur_mwh": 35.0,
            },
            {
                "delivery_date": "2026-03-23",
                "baseline_method": "uk_naive_previous_day_persistence",
                "baseline_forecast_mae_eur_mwh": 21.0,
                "baseline_forecast_rmse_eur_mwh": 26.0,
                "baseline_spread_direction_accuracy": 0.57,
                "baseline_realized_net_revenue_eur": 200.0,
                "oracle_net_revenue_eur": 300.0,
                "baseline_capture_ratio_vs_oracle": 2 / 3,
                "baseline_charged_mwh": 20.0,
                "baseline_discharged_mwh": 18.0,
                "baseline_equivalent_cycles": 0.9,
                "baseline_captured_spread_eur_mwh": 36.0,
            },
        ]
    )


def test_comparison_daily_uses_same_dates_and_columns() -> None:
    result = build_strategy_comparison(_ml_daily(), _baseline_daily())

    assert result.daily.columns.tolist() == DAILY_OUTPUT_SCHEMA
    assert result.daily["delivery_date"].unique().tolist() == ["2026-03-22", "2026-03-23"]
    assert set(result.daily["strategy"]) == {
        "ml_extra_trees",
        "ml_ridge",
        "uk_naive_baseline",
    }
    assert len(result.daily) == 6


def test_summary_calculates_paired_uplift_and_win_rate() -> None:
    result = build_strategy_comparison(_ml_daily(), _baseline_daily())

    assert result.summary.columns.tolist() == SUMMARY_OUTPUT_SCHEMA
    ridge = result.summary[result.summary["strategy"] == "ml_ridge"].iloc[0]
    assert ridge["matched_baseline_days"] == 2
    assert ridge["total_realized_net_revenue_eur"] == 330.0
    assert ridge["baseline_total_realized_net_revenue_eur"] == 300.0
    assert ridge["total_uplift_vs_uk_baseline_eur"] == 30.0
    assert ridge["average_uplift_vs_uk_baseline_eur_per_day"] == 15.0
    assert ridge["win_rate_vs_uk_baseline"] == 0.5

    baseline = result.summary[result.summary["strategy"] == "uk_naive_baseline"].iloc[0]
    assert baseline["total_uplift_vs_uk_baseline_eur"] == 0.0
    assert np.isnan(baseline["win_rate_vs_uk_baseline"])


def test_headline_report_selects_best_ml_rows_and_uplift() -> None:
    result = build_strategy_comparison(_ml_daily(), _baseline_daily())
    params = BatteryParams(power_mw=10, capacity_mwh=20, max_cycles_per_day=1.0)

    headline = build_headline_report(result.daily, result.summary, battery_params=params)

    assert list(headline.keys()) == HEADLINE_OUTPUT_KEYS
    assert headline["date_window"] == {"start": "2026-03-22", "end": "2026-03-23"}
    assert headline["evaluated_days"] == 2
    assert headline["best_model"] == "ridge"
    assert headline["best_ml_strategy"] == "ml_ridge"
    assert headline["uk_baseline_total_pnl_eur"] == 300.0
    assert headline["ml_total_pnl_eur"] == 330.0
    assert headline["uplift_eur"] == 30.0
    assert headline["uplift_pct"] == 0.1
    assert headline["win_rate_vs_uk_baseline"] == 0.5
    assert headline["average_capture_ratio_vs_oracle"] == 0.55
    assert headline["best_ml_by_forecast_mae_eur_mwh"]["model_or_method"] == "ridge"
    assert headline["battery_assumptions"]["power_mw"] == 10
    assert headline["battery_assumptions"]["capacity_mwh"] == 20


def test_headline_aggregates_baseline_split_across_methods() -> None:
    baseline = _baseline_daily()
    baseline.loc[1, "baseline_method"] = "uk_naive_prior_7_day_interval_median"
    result = build_strategy_comparison(_ml_daily(), baseline)

    baseline_summary = result.summary[result.summary["strategy"] == "uk_naive_baseline"]
    assert set(baseline_summary["model_or_method"]) == {
        "uk_naive_previous_day_persistence",
        "uk_naive_prior_7_day_interval_median",
    }

    headline = build_headline_report(result.daily, result.summary)

    assert headline["best_model"] == "ridge"
    assert headline["ml_total_pnl_eur"] == 330.0
    assert headline["uk_baseline_total_pnl_eur"] == 300.0
    assert headline["uplift_eur"] == 30.0
    assert headline["uplift_pct"] == 0.1
    assert headline["uk_baseline"]["model_or_method"] == "all_methods"
    assert headline["uk_baseline"]["methods"] == [
        "uk_naive_previous_day_persistence",
        "uk_naive_prior_7_day_interval_median",
    ]


def test_headline_frame_flattens_json_payload_for_csv() -> None:
    result = build_strategy_comparison(_ml_daily(), _baseline_daily())
    headline = build_headline_report(result.daily, result.summary)

    frame = build_headline_frame(headline)

    assert len(frame) == 1
    row = frame.iloc[0]
    assert row["start_date"] == "2026-03-22"
    assert row["end_date"] == "2026-03-23"
    assert row["best_model"] == "ridge"
    assert row["uplift_eur"] == 30.0
    assert row["best_mae_model"] == "ridge"
    assert pd.isna(row["battery_power_mw"])


def test_interval_output_normalizes_ml_predictions_and_baseline_dispatch() -> None:
    ml_predictions = pd.DataFrame(
        [
            {
                "delivery_date": "2026-03-22",
                "timestamp": "2026-03-22 00:00:00",
                "interval": 1,
                "model": "ridge",
                "actual_price_eur_mwh": 80.0,
                "forecast_price_eur_mwh": 75.0,
                "charge_mw": 0.0,
                "discharge_mw": 5.0,
                "net_power_mw": 5.0,
                "soc_pct_end": 45.0,
            },
            {
                "delivery_date": "2026-03-24",
                "timestamp": "2026-03-24 00:00:00",
                "interval": 1,
                "model": "ridge",
                "actual_price_eur_mwh": 80.0,
                "forecast_price_eur_mwh": 75.0,
                "charge_mw": 0.0,
                "discharge_mw": 5.0,
                "net_power_mw": 5.0,
                "soc_pct_end": 45.0,
            },
        ]
    )
    baseline_intervals = pd.DataFrame(
        [
            {
                "delivery_date": "2026-03-22",
                "timestamp": "2026-03-22 00:00:00",
                "interval": 1,
                "model_or_method": "uk_naive_previous_day_persistence",
                "actual_price_eur_mwh": 80.0,
                "forecast_price_eur_mwh": 70.0,
                "charge_mw": 1.0,
                "discharge_mw": 0.0,
                "net_power_mw": -1.0,
                "soc_pct_end": 51.0,
            }
        ]
    )

    result = build_strategy_comparison(
        _ml_daily(),
        _baseline_daily(),
        ml_predictions=ml_predictions,
        baseline_intervals=baseline_intervals,
    )

    assert result.intervals.columns.tolist() == INTERVAL_OUTPUT_SCHEMA
    assert result.intervals["delivery_date"].unique().tolist() == ["2026-03-22"]
    assert set(result.intervals["strategy"]) == {"ml_ridge", "uk_naive_baseline"}


def test_can_run_uk_naive_baseline_for_comparison_from_synthetic_history() -> None:
    frames = []
    start = date(2026, 4, 1)
    for offset in range(3):
        delivery_date = start + timedelta(days=offset)
        frame = synthetic_market_day(delivery_date)
        frame["data_quality"] = "public price data"
        frame["delivery_date"] = delivery_date
        frames.append(frame)
    history = pd.concat(frames, ignore_index=True)

    daily, intervals = run_uk_naive_baseline_for_comparison(
        history,
        date(2026, 4, 2),
        date(2026, 4, 3),
        BatteryParams(power_mw=10, capacity_mwh=20, max_cycles_per_day=1.0),
        include_intervals=True,
    )

    assert daily.columns.tolist() == DAILY_OUTPUT_SCHEMA
    assert intervals.columns.tolist() == INTERVAL_OUTPUT_SCHEMA
    assert daily["strategy"].eq("uk_naive_baseline").all()
    assert len(intervals) == 192


def test_cli_model_filter_accepts_model_or_method_column() -> None:
    frame = pd.DataFrame(
        [
            {"model_or_method": "scarcity_ensemble", "value": 1},
            {"model_or_method": "ridge", "value": 2},
        ]
    )
    filter_models = _load_cli_filter_models()

    filtered = filter_models(frame, {"scarcity_ensemble"}, "test_frame")

    assert filtered["model_or_method"].tolist() == ["scarcity_ensemble"]


def test_cli_model_filter_fails_when_requested_model_absent() -> None:
    frame = pd.DataFrame([{"model": "ridge", "value": 2}])
    filter_models = _load_cli_filter_models()

    with pytest.raises(ValueError, match="no rows for requested models"):
        filter_models(frame, {"scarcity_ensemble"}, "test_frame")


def _load_cli_filter_models():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_strategy_comparison.py"
    spec = importlib.util.spec_from_file_location("run_strategy_comparison", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._filter_models
