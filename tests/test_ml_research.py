from __future__ import annotations

import importlib.util
import os
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")

from batteryhack.ml_research import (
    DEFAULT_RESEARCH_MODEL_CANDIDATES,
    build_daily_winners,
    build_model_selection_stability,
    build_paired_uplift_summary,
    forecast_with_research_model,
    run_feature_ablation_backtest,
    run_ml_research_backtest,
)
from batteryhack.optimizer import BatteryParams
from batteryhack.synthetic import synthetic_market_day

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_ml_research.py"
_SCRIPT_SPEC = importlib.util.spec_from_file_location("run_ml_research_script", _SCRIPT_PATH)
assert _SCRIPT_SPEC is not None and _SCRIPT_SPEC.loader is not None
_RUN_ML_RESEARCH_SCRIPT = importlib.util.module_from_spec(_SCRIPT_SPEC)
_SCRIPT_SPEC.loader.exec_module(_RUN_ML_RESEARCH_SCRIPT)
_daily_with_explicit_uk_baseline = _RUN_ML_RESEARCH_SCRIPT._daily_with_explicit_uk_baseline
_paired_comparison_models = _RUN_ML_RESEARCH_SCRIPT._paired_comparison_models
_select_primary_model = _RUN_ML_RESEARCH_SCRIPT._select_primary_model


def _history(days: int = 9) -> pd.DataFrame:
    start = date(2026, 3, 1)
    frames = []
    for offset in range(days):
        delivery_date = start + timedelta(days=offset)
        frame = synthetic_market_day(delivery_date)
        frame["data_quality"] = "public price data"
        frame["delivery_date"] = delivery_date
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def _params() -> BatteryParams:
    return BatteryParams(
        power_mw=10,
        capacity_mwh=20,
        round_trip_efficiency=0.9,
        degradation_cost_eur_mwh=4,
        max_cycles_per_day=1.0,
        enforce_single_mode=False,
    )


def test_research_harness_runs_required_candidate_families() -> None:
    result = run_ml_research_backtest(
        _history(8),
        date(2026, 3, 7),
        date(2026, 3, 7),
        battery_params=_params(),
        min_train_days=5,
        model_candidates=DEFAULT_RESEARCH_MODEL_CANDIDATES,
    )

    assert set(result.summary["model"]) == set(DEFAULT_RESEARCH_MODEL_CANDIDATES)
    assert set(result.daily["model"]) == set(DEFAULT_RESEARCH_MODEL_CANDIDATES)
    assert len(result.predictions) == 96 * len(DEFAULT_RESEARCH_MODEL_CANDIDATES)
    assert result.summary["mae_eur_mwh"].notna().all()
    assert result.summary["capture_ratio_vs_oracle"].notna().all()


def test_research_backtest_trains_only_on_prior_dates() -> None:
    result = run_ml_research_backtest(
        _history(7),
        date(2026, 3, 5),
        date(2026, 3, 6),
        battery_params=_params(),
        min_train_days=3,
        model_candidates=("interval_profile", "ridge"),
    )

    assert len(result.daily) == 4
    delivery_dates = pd.to_datetime(result.daily["delivery_date"])
    training_end = pd.to_datetime(result.daily["training_end"])
    assert (training_end < delivery_dates).all()
    assert result.daily.groupby("delivery_date")["training_days"].first().tolist() == [4, 5]


def test_research_backtest_drops_synthetic_targets_and_training_by_default() -> None:
    history = _history(8)
    synthetic_day = date(2026, 3, 5)
    history.loc[history["timestamp"].dt.date == synthetic_day, "data_quality"] = (
        "synthetic price fallback"
    )

    result = run_ml_research_backtest(
        history,
        date(2026, 3, 5),
        date(2026, 3, 7),
        battery_params=_params(),
        min_train_days=3,
        model_candidates=("ridge",),
    )

    assert result.daily["delivery_date"].tolist() == ["2026-03-06", "2026-03-07"]
    assert "synthetic target prices" in result.skipped_days["reason"].tolist()
    assert result.daily.groupby("delivery_date")["training_days"].first().tolist() == [4, 5]


def test_research_outputs_dispatch_and_quartile_metrics() -> None:
    result = run_ml_research_backtest(
        _history(6),
        date(2026, 3, 5),
        date(2026, 3, 5),
        battery_params=_params(),
        min_train_days=3,
        model_candidates=("interval_profile", "extra_trees"),
    )

    required_daily_columns = {
        "mae_eur_mwh",
        "rmse_eur_mwh",
        "spread_direction_accuracy",
        "top_quartile_accuracy",
        "bottom_quartile_accuracy",
        "forecast_objective_net_revenue_eur",
        "realized_net_revenue_eur",
        "oracle_net_revenue_eur",
        "capture_ratio_vs_oracle",
    }
    assert required_daily_columns.issubset(result.daily.columns)
    assert result.daily[list(required_daily_columns)].notna().all().all()
    assert {"charge_mw", "discharge_mw", "soc_pct_end"}.issubset(result.predictions.columns)


def test_credibility_diagnostics_are_paired_by_delivery_date() -> None:
    result = run_ml_research_backtest(
        _history(7),
        date(2026, 3, 5),
        date(2026, 3, 6),
        battery_params=_params(),
        min_train_days=3,
        model_candidates=("interval_profile", "ridge", "extra_trees"),
    )

    winners = build_daily_winners(result.daily)
    stability = build_model_selection_stability(result.summary, result.daily)
    uplift = build_paired_uplift_summary(
        result.daily,
        primary_model="ridge",
        comparison_models=("extra_trees", "interval_profile"),
    )

    assert len(winners) == 2
    assert {"winning_model", "win_margin_eur"}.issubset(winners.columns)
    assert {
        "total_pnl",
        "mean_daily_pnl",
        "median_daily_pnl",
        "mae",
        "top_quartile_accuracy",
        "bottom_quartile_accuracy",
        "capture_ratio",
    }.issubset(set(stability["criterion"]))
    assert uplift["paired_days"].tolist() == [2, 2]
    assert {"mean_daily_pnl_uplift_eur", "median_daily_pnl_uplift_eur"}.issubset(
        uplift.columns
    )


def test_feature_ablation_smoke_runs_named_feature_sets() -> None:
    ablation = run_feature_ablation_backtest(
        _history(6),
        date(2026, 3, 5),
        date(2026, 3, 5),
        battery_params=_params(),
        min_train_days=3,
        model_name="ridge",
        feature_sets=("calendar_only", "load_res_net_load", "weather_only", "all_live_safe"),
    )

    assert set(ablation["feature_set"]) == {
        "calendar_only",
        "load_res_net_load",
        "weather_only",
        "all_live_safe",
    }
    assert ablation["mae_eur_mwh"].notna().all()
    assert ablation["capture_ratio_vs_oracle"].notna().all()


def test_scarcity_ensemble_outputs_disagreement_and_conservative_dispatch() -> None:
    result = run_ml_research_backtest(
        _history(8),
        date(2026, 3, 7),
        date(2026, 3, 7),
        battery_params=_params(),
        min_train_days=5,
        model_candidates=("scarcity_ensemble", "scarcity_ensemble_conservative"),
    )

    assert set(result.daily["model"]) == {
        "scarcity_ensemble",
        "scarcity_ensemble_conservative",
    }
    assert result.daily["mean_model_disagreement_eur_mwh"].notna().all()
    assert result.daily["scarcity_weights"].str.contains("ridge=").all()
    assert "model_disagreement_eur_mwh" in result.predictions.columns
    assert "raw_ensemble_forecast_price_eur_mwh" in result.predictions.columns
    assert result.predictions["model_disagreement_eur_mwh"].notna().all()
    assert set(result.daily["dispatch_mode"]) == {
        "standard",
        "conservative_spread_shrink",
    }


def test_scarcity_weights_ignore_target_day_actual_prices() -> None:
    history = _history(8)
    target_date = date(2026, 3, 7)
    target = history[history["timestamp"].dt.date == target_date].copy()
    shocked_target = target.copy()
    shocked_target["dam_price_eur_mwh"] = shocked_target["dam_price_eur_mwh"] + 10000.0

    normal = forecast_with_research_model(
        history,
        target,
        "scarcity_ensemble",
        battery_params=_params(),
    )
    shocked = forecast_with_research_model(
        history,
        shocked_target,
        "scarcity_ensemble",
        battery_params=_params(),
    )

    assert normal.diagnostics["scarcity_weights"] == shocked.diagnostics["scarcity_weights"]
    assert normal.forecast.round(8).equals(shocked.forecast.round(8))
    validation_dates = str(normal.diagnostics["validation_dates"]).split(",")
    assert validation_dates
    assert all(pd.Timestamp(day).date() < target_date for day in validation_dates)


def test_cli_pairing_defaults_to_run_winner_and_requires_explicit_full_uk_path(tmp_path) -> None:
    daily = pd.DataFrame(
        {
            "delivery_date": ["2026-03-01", "2026-03-01", "2026-03-02", "2026-03-02"],
            "model": ["ridge", "scarcity_ensemble", "ridge", "scarcity_ensemble"],
            "realized_net_revenue_eur": [10.0, 20.0, 10.0, 25.0],
            "capture_ratio_vs_oracle": [0.4, 0.8, 0.4, 0.9],
        }
    )
    summary = pd.DataFrame(
        {
            "model": ["ridge", "scarcity_ensemble"],
            "total_realized_net_revenue_eur": [20.0, 45.0],
        }
    )

    primary = _select_primary_model(summary, daily, requested=None)

    assert primary == "scarcity_ensemble"
    assert _paired_comparison_models(daily, primary, include_uk_baseline=False) == ("ridge",)
    assert len(_daily_with_explicit_uk_baseline(daily, None)) == len(daily)

    one_day_uk = tmp_path / "one_day_uk.csv"
    pd.DataFrame(
        {
            "delivery_date": ["2026-03-01"],
            "realized_net_revenue_eur": [5.0],
            "capture_ratio_vs_oracle": [0.2],
        }
    ).to_csv(one_day_uk, index=False)

    try:
        _daily_with_explicit_uk_baseline(daily, str(one_day_uk))
    except ValueError as exc:
        assert "must cover every evaluated ML target date" in str(exc)
    else:
        raise AssertionError("Expected incomplete UK baseline to be rejected")
