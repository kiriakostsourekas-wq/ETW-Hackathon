from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from batteryhack.results_validation import validate_research_outputs


def test_validation_passes_consistent_fixture(tmp_path: Path) -> None:
    _write_fixture(tmp_path)

    result = validate_research_outputs(tmp_path, ml_artifact_set="default")

    assert result.ok, result.errors
    assert result.details["best_model"] == "scarcity_ensemble"
    assert result.details["uk_baseline_total_pnl_eur"] == 300.0


def test_validation_warns_on_suspicious_low_paired_uk_baseline_days(tmp_path: Path) -> None:
    _write_fixture(tmp_path, paired_days=1)

    result = validate_research_outputs(tmp_path, ml_artifact_set="default")

    assert result.ok, result.errors
    assert any("paired_days=1" in warning for warning in result.warnings)
    assert any("Ignoring it" in warning for warning in result.warnings)


def test_validation_fails_headline_total_mismatch(tmp_path: Path) -> None:
    _write_fixture(tmp_path, headline_updates={"ml_total_pnl_eur": 999.0})

    result = validate_research_outputs(tmp_path)

    assert not result.ok
    assert any("ml_total_pnl_eur" in error for error in result.errors)


def test_validation_fails_when_baseline_methods_are_not_aggregated(tmp_path: Path) -> None:
    _write_fixture(
        tmp_path,
        headline_updates={
            "uk_baseline_total_pnl_eur": 100.0,
            "uk_baseline": {
                "strategy": "uk_naive_baseline",
                "model_or_method": "uk_naive_previous_day_persistence",
                "methods": ["uk_naive_previous_day_persistence"],
                "days": 1,
                "total_realized_net_revenue_eur": 100.0,
                "average_realized_net_revenue_eur_per_day": 100.0,
                "average_capture_ratio_vs_oracle": 0.3,
                "win_rate_vs_uk_baseline": None,
                "total_uplift_vs_uk_baseline_eur": 0.0,
            },
        },
    )

    result = validate_research_outputs(tmp_path)

    assert not result.ok
    assert any("uk_baseline_total_pnl_eur" in error for error in result.errors)
    assert any("model_or_method='all_methods'" in error for error in result.errors)


def test_validation_fails_date_window_mismatch(tmp_path: Path) -> None:
    _write_fixture(
        tmp_path,
        daily_dates=("2026-03-22", "2026-03-24"),
    )

    result = validate_research_outputs(tmp_path)

    assert not result.ok
    assert any("date_window" in error for error in result.errors)


def test_validation_fails_missing_required_artifact(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    (tmp_path / "ml_research_summary.csv").unlink()

    result = validate_research_outputs(tmp_path, ml_artifact_set="default")

    assert not result.ok
    assert any("Missing required artifact" in error for error in result.errors)


def test_validation_auto_selects_scarcity_artifact_family(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    _write_fixture(
        tmp_path,
        prefix="ml_research_scarcity",
        headline_updates={
            "best_model": "scarcity_ensemble",
            "ml_total_pnl_eur": 360.0,
            "uplift_eur": 60.0,
            "uplift_pct": 0.2,
        },
        models=[
            ("scarcity_ensemble", 360.0, 0.62),
            ("ridge", 330.0, 0.55),
        ],
        stability_winner=("scarcity_ensemble", 360.0),
        paired_primary_model="scarcity_ensemble",
    )

    result = validate_research_outputs(tmp_path)

    assert result.ok, result.errors
    assert result.details["ml_artifact_set"] == "scarcity"
    assert result.details["best_model"] == "scarcity_ensemble"


def test_validation_fails_if_official_headline_is_not_scarcity_ensemble(
    tmp_path: Path,
) -> None:
    _write_fixture(
        tmp_path,
        headline_updates={
            "best_model": "ridge",
            "ml_total_pnl_eur": 310.0,
            "uplift_eur": 10.0,
            "uplift_pct": 10.0 / 300.0,
        },
        models=[
            ("scarcity_ensemble", 330.0, 0.55),
            ("ridge", 310.0, 0.52),
        ],
    )

    result = validate_research_outputs(tmp_path, ml_artifact_set="default")

    assert not result.ok
    assert any("Official presentation headline model mismatch" in error for error in result.errors)


def test_validation_fails_if_conservative_scarcity_is_headline(tmp_path: Path) -> None:
    _write_fixture(
        tmp_path,
        headline_updates={
            "best_model": "scarcity_ensemble_conservative",
            "ml_total_pnl_eur": 340.0,
            "uplift_eur": 40.0,
            "uplift_pct": 40.0 / 300.0,
        },
        models=[
            ("scarcity_ensemble", 330.0, 0.55),
            ("scarcity_ensemble_conservative", 340.0, 0.56),
        ],
        paired_primary_model="scarcity_ensemble_conservative",
    )

    result = validate_research_outputs(tmp_path, ml_artifact_set="default")

    assert not result.ok
    assert any("must not be selected" in error for error in result.errors)


def test_validation_checks_future_market_impact_headline_when_present(
    tmp_path: Path,
) -> None:
    _write_fixture(tmp_path)
    _write_future_headline(tmp_path)

    result = validate_research_outputs(tmp_path, ml_artifact_set="default")

    assert result.ok, result.errors
    assert result.details["future_market_impact_model"] == "ml_scarcity_ensemble"
    assert result.details["future_market_impact_scenarios"] == [
        "aggressive",
        "base",
        "conservative",
    ]


def test_validation_fails_stale_future_market_impact_headline(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    _write_future_headline(
        tmp_path,
        rows=[
            _future_row("ml_ridge", "conservative", 2),
            _future_row("ml_ridge", "base", 2),
            _future_row("ml_ridge", "aggressive", 2),
        ],
    )

    result = validate_research_outputs(tmp_path, ml_artifact_set="default")

    assert not result.ok
    assert any("strategy_model=ml_scarcity_ensemble" in error for error in result.errors)


def test_validation_fails_future_market_impact_wrong_input_file(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    _write_future_headline(tmp_path, input_file="data/processed/ml_research_predictions.csv")

    result = validate_research_outputs(tmp_path, ml_artifact_set="default")

    assert not result.ok
    assert any("input_file mismatch" in error for error in result.errors)


def test_validation_fails_future_market_impact_bad_sample_days(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    _write_future_headline(
        tmp_path,
        rows=[
            _future_row("ml_scarcity_ensemble", "conservative", 2),
            _future_row("ml_scarcity_ensemble", "base", 1),
            _future_row("ml_scarcity_ensemble", "aggressive", 2),
        ],
    )

    result = validate_research_outputs(tmp_path, ml_artifact_set="default")

    assert not result.ok
    assert any("sample_days must equal" in error for error in result.errors)


def _write_fixture(
    directory: Path,
    paired_days: int = 2,
    headline_updates: dict[str, object] | None = None,
    daily_dates: tuple[str, str] = ("2026-03-22", "2026-03-23"),
    prefix: str = "ml_research",
    models: list[tuple[str, float, float]] | None = None,
    stability_winner: tuple[str, float] | None = None,
    paired_primary_model: str = "scarcity_ensemble",
) -> None:
    model_rows = models or [
        ("scarcity_ensemble", 330.0, 0.55),
        ("ridge", 310.0, 0.52),
    ]
    pd.DataFrame(
        [
            {
                "model": model,
                "days_evaluated": 2,
                "total_realized_net_revenue_eur": pnl,
                "capture_ratio_vs_oracle": capture,
            }
            for model, pnl, capture in model_rows
        ]
    ).to_csv(directory / f"{prefix}_summary.csv", index=False)

    winner = stability_winner or (model_rows[0][0], model_rows[0][1])
    pd.DataFrame(
        [
            {
                "criterion": "total_pnl",
                "winning_model": winner[0],
                "winning_value": winner[1],
            }
        ]
    ).to_csv(directory / f"{prefix}_model_stability.csv", index=False)

    pd.DataFrame(
        [
            {
                "primary_model": paired_primary_model,
                "comparison_model": "uk_naive_baseline",
                "paired_days": paired_days,
            },
            {
                "primary_model": paired_primary_model,
                "comparison_model": "extra_trees",
                "paired_days": 2,
            },
        ]
    ).to_csv(directory / f"{prefix}_paired_uplift.csv", index=False)

    comparison_rows = [
        _summary_row(f"ml_{model}", model, 2, pnl, capture, 0.5, 300.0)
        for model, pnl, capture in model_rows
    ]
    comparison_rows.extend(
        [
            _summary_row(
                "uk_naive_baseline",
                "uk_naive_previous_day_persistence",
                1,
                100.0,
                0.3,
                None,
                100.0,
            ),
            _summary_row(
                "uk_naive_baseline",
                "uk_naive_prior_7_day_interval_median",
                1,
                200.0,
                0.4,
                None,
                200.0,
            ),
        ]
    )
    pd.DataFrame(comparison_rows).to_csv(
        directory / "strategy_comparison_summary.csv",
        index=False,
    )

    pd.DataFrame(
        [
            {"delivery_date": daily_dates[0], "strategy": "ml_scarcity_ensemble"},
            {"delivery_date": daily_dates[1], "strategy": "ml_scarcity_ensemble"},
            {"delivery_date": daily_dates[0], "strategy": "uk_naive_baseline"},
            {"delivery_date": daily_dates[1], "strategy": "uk_naive_baseline"},
        ]
    ).to_csv(directory / "strategy_comparison_daily.csv", index=False)

    headline = {
        "date_window": {"start": "2026-03-22", "end": "2026-03-23"},
        "evaluated_days": 2,
        "best_model": "scarcity_ensemble",
        "uk_baseline_total_pnl_eur": 300.0,
        "ml_total_pnl_eur": 330.0,
        "uplift_eur": 30.0,
        "uplift_pct": 0.1,
        "win_rate_vs_uk_baseline": 0.5,
        "uk_baseline": {
            "strategy": "uk_naive_baseline",
            "model_or_method": "all_methods",
            "methods": [
                "uk_naive_previous_day_persistence",
                "uk_naive_prior_7_day_interval_median",
            ],
            "days": 2,
            "total_realized_net_revenue_eur": 300.0,
            "average_realized_net_revenue_eur_per_day": 150.0,
            "average_capture_ratio_vs_oracle": 0.35,
            "win_rate_vs_uk_baseline": None,
            "total_uplift_vs_uk_baseline_eur": 0.0,
        },
    }
    if headline_updates:
        headline.update(headline_updates)
    (directory / "strategy_comparison_headline.json").write_text(
        json.dumps(headline, indent=2)
    )


def _write_future_headline(
    directory: Path,
    rows: list[dict[str, object]] | None = None,
    input_file: str = "data/processed/strategy_comparison_intervals.csv",
) -> None:
    payload = {
        "generated_at": "2026-04-30T00:00:00Z",
        "input_file": input_file,
        "rows": rows
        or [
            _future_row("ml_scarcity_ensemble", "conservative", 2),
            _future_row("ml_scarcity_ensemble", "base", 2),
            _future_row("ml_scarcity_ensemble", "aggressive", 2),
            _future_row("uk_naive_baseline", "conservative", 2),
        ],
    }
    (directory / "future_market_impact_headline.json").write_text(
        json.dumps(payload, indent=2)
    )


def _future_row(strategy_model: str, scenario: str, sample_days: int) -> dict[str, object]:
    return {
        "strategy_model": strategy_model,
        "scenario": scenario,
        "fixed_schedule_degradation_pct": 10.0,
        "reoptimized_degradation_pct": 5.0,
        "reoptimization_recovery_eur": 1000.0,
        "interpretation_label": "test",
        "sample_days": sample_days,
    }


def _summary_row(
    strategy: str,
    model_or_method: str,
    days: int,
    total_pnl: float,
    capture: float,
    win_rate: float | None,
    baseline_total: float,
) -> dict[str, float | int | str | None]:
    return {
        "strategy": strategy,
        "model_or_method": model_or_method,
        "days": days,
        "matched_baseline_days": days,
        "total_realized_net_revenue_eur": total_pnl,
        "average_realized_net_revenue_eur_per_day": total_pnl / days,
        "average_capture_ratio_vs_oracle": capture,
        "win_rate_vs_uk_baseline": win_rate,
        "total_uplift_vs_uk_baseline_eur": total_pnl - baseline_total,
        "average_uplift_vs_uk_baseline_eur_per_day": (total_pnl - baseline_total) / days,
        "baseline_total_realized_net_revenue_eur": baseline_total,
    }
