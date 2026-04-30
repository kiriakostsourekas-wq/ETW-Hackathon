from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ML_ARTIFACT_SETS = {
    "default": {
        "ml_summary": "ml_research_summary.csv",
        "model_stability": "ml_research_model_stability.csv",
        "paired_uplift": "ml_research_paired_uplift.csv",
    },
    "scarcity": {
        "ml_summary": "ml_research_scarcity_summary.csv",
        "model_stability": "ml_research_scarcity_model_stability.csv",
        "paired_uplift": "ml_research_scarcity_paired_uplift.csv",
    },
}

REQUIRED_COMPARISON_ARTIFACTS = {
    "comparison_summary": "strategy_comparison_summary.csv",
    "headline": "strategy_comparison_headline.json",
}

OPTIONAL_ARTIFACTS = {
    "comparison_daily": "strategy_comparison_daily.csv",
}

UK_BASELINE_STRATEGY = "uk_naive_baseline"
OFFICIAL_HEADLINE_MODEL = "scarcity_ensemble"
EXPERIMENTAL_CONSERVATIVE_MODEL = "scarcity_ensemble_conservative"
OFFICIAL_FUTURE_STRATEGY_MODEL = f"ml_{OFFICIAL_HEADLINE_MODEL}"
FUTURE_MARKET_IMPACT_HEADLINE = "future_market_impact_headline.json"
FUTURE_MARKET_IMPACT_INPUT_FILE = "data/processed/strategy_comparison_intervals.csv"
REQUIRED_FUTURE_SCENARIOS = {"conservative", "base", "aggressive"}
DEFAULT_MIN_PAIRED_RATIO = 0.8
ABS_TOLERANCE_EUR = 1e-3
RATIO_TOLERANCE = 1e-9


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_research_outputs(
    processed_dir: Path,
    min_paired_ratio: float = DEFAULT_MIN_PAIRED_RATIO,
    ml_artifact_set: str = "auto",
) -> ValidationResult:
    result = ValidationResult()
    comparison_paths = _comparison_artifact_paths(processed_dir)
    missing = [name for name, path in comparison_paths.items() if not path.exists()]
    if missing:
        result.errors.extend(
            f"Missing required artifact: {REQUIRED_COMPARISON_ARTIFACTS[name]}"
            for name in missing
        )
        return result

    try:
        comparison_summary = pd.read_csv(comparison_paths["comparison_summary"])
        headline = json.loads(comparison_paths["headline"].read_text())
    except Exception as exc:
        result.errors.append(f"Could not load strategy comparison artifacts: {exc}")
        return result

    _validate_headline_keys(result, headline)
    if result.errors:
        return result

    selected_set, ml_paths = _select_ml_artifact_set(
        processed_dir,
        headline,
        ml_artifact_set,
        result,
    )
    if result.errors:
        return result
    result.details["ml_artifact_set"] = selected_set

    try:
        ml_summary = pd.read_csv(ml_paths["ml_summary"])
        model_stability = pd.read_csv(ml_paths["model_stability"])
        paired_uplift = pd.read_csv(ml_paths["paired_uplift"])
    except Exception as exc:
        result.errors.append(f"Could not load ML research artifacts: {exc}")
        return result

    comparison_daily_path = processed_dir / OPTIONAL_ARTIFACTS["comparison_daily"]
    comparison_daily = (
        pd.read_csv(comparison_daily_path) if comparison_daily_path.exists() else None
    )

    _validate_required_columns(
        result,
        ml_summary,
        {
            "model",
            "days_evaluated",
            "total_realized_net_revenue_eur",
            "capture_ratio_vs_oracle",
        },
        ml_paths["ml_summary"].name,
    )
    _validate_required_columns(
        result,
        model_stability,
        {"criterion", "winning_model", "winning_value"},
        ml_paths["model_stability"].name,
    )
    _validate_required_columns(
        result,
        paired_uplift,
        {"primary_model", "comparison_model", "paired_days"},
        ml_paths["paired_uplift"].name,
    )
    _validate_required_columns(
        result,
        comparison_summary,
        {
            "strategy",
            "model_or_method",
            "days",
            "matched_baseline_days",
            "total_realized_net_revenue_eur",
            "average_capture_ratio_vs_oracle",
            "win_rate_vs_uk_baseline",
            "total_uplift_vs_uk_baseline_eur",
            "baseline_total_realized_net_revenue_eur",
        },
        REQUIRED_COMPARISON_ARTIFACTS["comparison_summary"],
    )
    if result.errors:
        return result

    evaluated_days = int(headline["evaluated_days"])
    best_model = str(headline["best_model"])
    result.details["best_model"] = best_model
    result.details["evaluated_days"] = evaluated_days

    _validate_official_headline_model(result, best_model)
    _validate_date_window(result, headline, ml_summary, comparison_summary, comparison_daily)
    _validate_ml_summary(result, headline, ml_summary, model_stability)
    _validate_strategy_summary(result, headline, comparison_summary)
    _validate_paired_uplift(
        result,
        headline,
        paired_uplift,
        min_paired_ratio=min_paired_ratio,
    )
    _validate_future_market_impact_headline(result, processed_dir, evaluated_days)
    return result


def format_validation_report(result: ValidationResult) -> str:
    lines: list[str] = []
    status = "PASS" if result.ok else "FAIL"
    lines.append(f"Research artifact validation: {status}")
    if result.details:
        for key, value in result.details.items():
            lines.append(f"{key}: {value}")
    if result.errors:
        lines.append("\nErrors:")
        lines.extend(f"- {error}" for error in result.errors)
    if result.warnings:
        lines.append("\nWarnings:")
        lines.extend(f"- {warning}" for warning in result.warnings)
    if not result.errors and not result.warnings:
        lines.append("No inconsistencies found.")
    return "\n".join(lines)


def _comparison_artifact_paths(processed_dir: Path) -> dict[str, Path]:
    return {
        name: processed_dir / filename
        for name, filename in REQUIRED_COMPARISON_ARTIFACTS.items()
    }


def _ml_artifact_paths(processed_dir: Path, artifact_set: str) -> dict[str, Path]:
    return {
        name: processed_dir / filename
        for name, filename in ML_ARTIFACT_SETS[artifact_set].items()
    }


def _select_ml_artifact_set(
    processed_dir: Path,
    headline: dict[str, Any],
    requested: str,
    result: ValidationResult,
) -> tuple[str, dict[str, Path]]:
    if requested != "auto":
        if requested not in ML_ARTIFACT_SETS:
            result.errors.append(
                f"Unknown ML artifact set {requested!r}; choose auto, "
                f"{', '.join(sorted(ML_ARTIFACT_SETS))}"
            )
            return requested, {}
        paths = _ml_artifact_paths(processed_dir, requested)
        _append_missing_ml_artifacts(result, paths)
        return requested, paths

    best_model = str(headline["best_model"])
    candidates: list[tuple[str, dict[str, Path], pd.DataFrame]] = []
    for name in ML_ARTIFACT_SETS:
        paths = _ml_artifact_paths(processed_dir, name)
        if all(path.exists() for path in paths.values()):
            try:
                summary = pd.read_csv(paths["ml_summary"])
            except Exception:
                continue
            if "model" in summary.columns and best_model in set(summary["model"].astype(str)):
                candidates.append((name, paths, summary))

    if not candidates:
        result.errors.append(
            "No ML artifact set contains headline best_model="
            f"{best_model!r}. Checked: {', '.join(sorted(ML_ARTIFACT_SETS))}"
        )
        return "auto", {}

    if best_model.startswith("scarcity_"):
        for name, paths, _summary in candidates:
            if name == "scarcity":
                return name, paths
    return candidates[0][0], candidates[0][1]


def _append_missing_ml_artifacts(
    result: ValidationResult,
    paths: dict[str, Path],
) -> None:
    for path in paths.values():
        if not path.exists():
            result.errors.append(f"Missing required artifact: {path.name}")


def _validate_required_columns(
    result: ValidationResult,
    frame: pd.DataFrame,
    required: set[str],
    artifact_name: str,
) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        result.errors.append(f"{artifact_name} is missing required columns: {missing}")


def _validate_headline_keys(result: ValidationResult, headline: dict[str, Any]) -> None:
    required = {
        "date_window",
        "evaluated_days",
        "best_model",
        "uk_baseline_total_pnl_eur",
        "ml_total_pnl_eur",
        "uplift_eur",
        "uplift_pct",
        "win_rate_vs_uk_baseline",
        "uk_baseline",
    }
    missing = sorted(required - set(headline))
    if missing:
        result.errors.append(
            f"{REQUIRED_COMPARISON_ARTIFACTS['headline']} is missing keys: {missing}"
        )


def _validate_official_headline_model(result: ValidationResult, best_model: str) -> None:
    if best_model == EXPERIMENTAL_CONSERVATIVE_MODEL:
        result.errors.append(
            f"Experimental {EXPERIMENTAL_CONSERVATIVE_MODEL} must not be selected as "
            "the official presentation headline."
        )
        return
    if best_model != OFFICIAL_HEADLINE_MODEL:
        result.errors.append(
            "Official presentation headline model mismatch: "
            f"headline={best_model}, expected={OFFICIAL_HEADLINE_MODEL}"
        )


def _validate_date_window(
    result: ValidationResult,
    headline: dict[str, Any],
    ml_summary: pd.DataFrame,
    comparison_summary: pd.DataFrame,
    comparison_daily: pd.DataFrame | None,
) -> None:
    evaluated_days = int(headline["evaluated_days"])
    ml_days = pd.to_numeric(ml_summary["days_evaluated"], errors="coerce").dropna().unique()
    if len(ml_days) != 1 or int(ml_days[0]) != evaluated_days:
        result.errors.append(
            "Headline evaluated_days does not match ml_research_summary.csv "
            f"days_evaluated: headline={evaluated_days}, ml_summary={ml_days.tolist()}"
        )

    ml_comparison = comparison_summary[
        comparison_summary["strategy"].astype(str).str.startswith("ml_")
    ].copy()
    if not ml_comparison.empty:
        summary_days = pd.to_numeric(ml_comparison["days"], errors="coerce").dropna().unique()
        matched_days = (
            pd.to_numeric(ml_comparison["matched_baseline_days"], errors="coerce")
            .dropna()
            .unique()
        )
        if len(summary_days) != 1 or int(summary_days[0]) != evaluated_days:
            result.errors.append(
                "Headline evaluated_days does not match strategy comparison ML days: "
                f"headline={evaluated_days}, summary={summary_days.tolist()}"
            )
        if len(matched_days) != 1 or int(matched_days[0]) != evaluated_days:
            result.errors.append(
                "Headline evaluated_days does not match strategy comparison matched days: "
                f"headline={evaluated_days}, matched={matched_days.tolist()}"
            )

    baseline_rows = comparison_summary[comparison_summary["strategy"] == UK_BASELINE_STRATEGY]
    baseline_days = int(pd.to_numeric(baseline_rows["days"], errors="coerce").sum())
    if baseline_days != evaluated_days:
        result.errors.append(
            "UK baseline method rows in strategy_comparison_summary.csv do not add up "
            f"to headline evaluated_days: baseline_days={baseline_days}, "
            f"evaluated_days={evaluated_days}"
        )

    if comparison_daily is None:
        result.warnings.append(
            "strategy_comparison_daily.csv not found; date-window start/end could not be "
            "cross-checked."
        )
        return

    if "delivery_date" not in comparison_daily.columns:
        result.errors.append("strategy_comparison_daily.csv is missing delivery_date")
        return

    dates = sorted(pd.to_datetime(comparison_daily["delivery_date"]).dt.date.unique())
    if not dates:
        result.errors.append("strategy_comparison_daily.csv has no delivery_date values")
        return
    expected_window = {"start": dates[0].isoformat(), "end": dates[-1].isoformat()}
    if headline["date_window"] != expected_window:
        result.errors.append(
            "strategy_comparison_headline.json date_window does not match "
            f"strategy_comparison_daily.csv: headline={headline['date_window']}, "
            f"daily={expected_window}"
        )
    if len(dates) != evaluated_days:
        result.errors.append(
            "strategy_comparison_headline.json evaluated_days does not match "
            f"strategy_comparison_daily.csv unique delivery dates: "
            f"headline={evaluated_days}, daily={len(dates)}"
        )


def _validate_ml_summary(
    result: ValidationResult,
    headline: dict[str, Any],
    ml_summary: pd.DataFrame,
    model_stability: pd.DataFrame,
) -> None:
    ml_summary = ml_summary.copy()
    ml_summary["total_realized_net_revenue_eur"] = pd.to_numeric(
        ml_summary["total_realized_net_revenue_eur"],
        errors="coerce",
    )
    model_rows = ml_summary[ml_summary["model"].astype(str) == str(headline["best_model"])]
    if model_rows.empty:
        result.errors.append(
            f"ML summary has no row for headline best_model={headline['best_model']}"
        )
        return
    best = model_rows.sort_values(
        ["total_realized_net_revenue_eur"],
        ascending=[False],
    ).iloc[0]
    best_model = str(best["model"])
    best_pnl = float(best["total_realized_net_revenue_eur"])
    _assert_close(
        result,
        "Headline ml_total_pnl_eur",
        headline["ml_total_pnl_eur"],
        best_pnl,
        ABS_TOLERANCE_EUR,
    )

    total_pnl = model_stability[model_stability["criterion"] == "total_pnl"]
    if total_pnl.empty:
        result.errors.append("ml_research_model_stability.csv has no total_pnl row")
        return
    stability_row = total_pnl.iloc[0]
    stability_winner = str(stability_row["winning_model"])
    if stability_winner != best_model:
        result.warnings.append(
            "ML model stability total_pnl winner differs from the official headline model: "
            f"stability={stability_winner}, headline={best_model}. This is acceptable "
            "when the official comparison intentionally filters to a presentation model."
        )
    else:
        _assert_close(
            result,
            "ML model stability total_pnl winning_value",
            stability_row["winning_value"],
            best_pnl,
            ABS_TOLERANCE_EUR,
        )
    result.details["ml_total_pnl_eur"] = round(best_pnl, 6)


def _validate_strategy_summary(
    result: ValidationResult,
    headline: dict[str, Any],
    comparison_summary: pd.DataFrame,
) -> None:
    summary = comparison_summary.copy()
    summary["total_realized_net_revenue_eur"] = pd.to_numeric(
        summary["total_realized_net_revenue_eur"],
        errors="coerce",
    )
    baseline_rows = summary[summary["strategy"] == UK_BASELINE_STRATEGY].copy()
    if baseline_rows.empty:
        result.errors.append("strategy_comparison_summary.csv has no uk_naive_baseline rows")
        return

    baseline_total = float(baseline_rows["total_realized_net_revenue_eur"].sum())
    headline_baseline = headline.get("uk_baseline", {})
    _assert_close(
        result,
        "Headline uk_baseline_total_pnl_eur",
        headline["uk_baseline_total_pnl_eur"],
        baseline_total,
        ABS_TOLERANCE_EUR,
    )
    if isinstance(headline_baseline, dict):
        _assert_close(
            result,
            "Headline uk_baseline.total_realized_net_revenue_eur",
            headline_baseline.get("total_realized_net_revenue_eur"),
            baseline_total,
            ABS_TOLERANCE_EUR,
        )
    if len(baseline_rows) > 1:
        expected_methods = sorted(baseline_rows["model_or_method"].astype(str).unique())
        if not isinstance(headline_baseline, dict):
            result.errors.append("Headline uk_baseline object is missing or malformed")
        else:
            if headline_baseline.get("model_or_method") != "all_methods":
                result.errors.append(
                    "Headline uk_baseline must aggregate split baseline methods with "
                    "model_or_method='all_methods'"
                )
            if sorted(headline_baseline.get("methods", [])) != expected_methods:
                result.errors.append(
                    "Headline uk_baseline methods do not match split baseline rows: "
                    f"headline={headline_baseline.get('methods')}, expected={expected_methods}"
                )

    ml_rows = summary[summary["strategy"].astype(str).str.startswith("ml_")].copy()
    if ml_rows.empty:
        result.errors.append("strategy_comparison_summary.csv has no ML rows")
        return
    best_ml = ml_rows.sort_values(
        ["total_realized_net_revenue_eur", "strategy"],
        ascending=[False, True],
    ).iloc[0]
    if str(best_ml["model_or_method"]) != str(headline["best_model"]):
        result.errors.append(
            "strategy_comparison_summary.csv best ML model does not match headline: "
            f"summary={best_ml['model_or_method']}, headline={headline['best_model']}"
        )
    _assert_close(
        result,
        "Headline ml_total_pnl_eur against strategy comparison summary",
        headline["ml_total_pnl_eur"],
        best_ml["total_realized_net_revenue_eur"],
        ABS_TOLERANCE_EUR,
    )
    expected_uplift = float(best_ml["total_realized_net_revenue_eur"]) - baseline_total
    expected_pct = expected_uplift / abs(baseline_total) if abs(baseline_total) > 1e-9 else np.nan
    _assert_close(
        result,
        "Headline uplift_eur",
        headline["uplift_eur"],
        expected_uplift,
        ABS_TOLERANCE_EUR,
    )
    _assert_close(
        result,
        "Headline uplift_pct",
        headline["uplift_pct"],
        expected_pct,
        RATIO_TOLERANCE,
    )
    _assert_close(
        result,
        "Headline win_rate_vs_uk_baseline",
        headline["win_rate_vs_uk_baseline"],
        best_ml["win_rate_vs_uk_baseline"],
        RATIO_TOLERANCE,
    )
    result.details["uk_baseline_total_pnl_eur"] = round(baseline_total, 6)
    result.details["uplift_eur"] = round(expected_uplift, 6)


def _validate_paired_uplift(
    result: ValidationResult,
    headline: dict[str, Any],
    paired_uplift: pd.DataFrame,
    min_paired_ratio: float,
) -> None:
    best_model = str(headline["best_model"])
    evaluated_days = int(headline["evaluated_days"])
    direct = paired_uplift[
        (paired_uplift["primary_model"].astype(str) == best_model)
        & (paired_uplift["comparison_model"].astype(str) == UK_BASELINE_STRATEGY)
    ]
    reverse = paired_uplift[
        (paired_uplift["primary_model"].astype(str) == UK_BASELINE_STRATEGY)
        & (paired_uplift["comparison_model"].astype(str) == best_model)
    ]
    rows = pd.concat([direct, reverse], ignore_index=True)
    if rows.empty:
        result.warnings.append(
            "ML paired-uplift artifact has no paired row for "
            f"{best_model} vs {UK_BASELINE_STRATEGY}"
        )
        return
    paired_days = int(pd.to_numeric(rows.iloc[0]["paired_days"], errors="coerce"))
    minimum_days = int(np.ceil(evaluated_days * min_paired_ratio))
    if paired_days < minimum_days:
        result.warnings.append(
            "ML paired-uplift artifact has a "
            f"{best_model} vs {UK_BASELINE_STRATEGY} row with only "
            f"paired_days={paired_days} versus evaluated_days={evaluated_days}. "
            "Ignoring it for the headline UK comparison; use "
            "strategy_comparison_headline.json instead."
        )
    result.details["paired_uk_baseline_days"] = paired_days


def _validate_future_market_impact_headline(
    result: ValidationResult,
    processed_dir: Path,
    evaluated_days: int,
) -> None:
    path = processed_dir / FUTURE_MARKET_IMPACT_HEADLINE
    if not path.exists():
        return

    try:
        headline = json.loads(path.read_text())
    except Exception as exc:
        result.errors.append(f"Could not load {FUTURE_MARKET_IMPACT_HEADLINE}: {exc}")
        return

    input_file = str(headline.get("input_file", ""))
    if input_file != FUTURE_MARKET_IMPACT_INPUT_FILE:
        result.errors.append(
            f"{FUTURE_MARKET_IMPACT_HEADLINE} input_file mismatch: "
            f"actual={input_file}, expected={FUTURE_MARKET_IMPACT_INPUT_FILE}"
        )

    rows = headline.get("rows")
    if not isinstance(rows, list) or not rows:
        result.errors.append(f"{FUTURE_MARKET_IMPACT_HEADLINE} has no rows")
        return

    strategy_rows = [
        row
        for row in rows
        if isinstance(row, dict)
        and str(row.get("strategy_model")) == OFFICIAL_FUTURE_STRATEGY_MODEL
    ]
    if not strategy_rows:
        available = sorted(
            {
                str(row.get("strategy_model"))
                for row in rows
                if isinstance(row, dict) and row.get("strategy_model")
            }
        )
        result.errors.append(
            f"{FUTURE_MARKET_IMPACT_HEADLINE} has no rows for "
            f"strategy_model={OFFICIAL_FUTURE_STRATEGY_MODEL}; available={available}"
        )
        return

    scenarios = {
        str(row.get("scenario"))
        for row in strategy_rows
        if row.get("scenario") is not None
    }
    missing_scenarios = sorted(REQUIRED_FUTURE_SCENARIOS - scenarios)
    if missing_scenarios:
        result.errors.append(
            f"{FUTURE_MARKET_IMPACT_HEADLINE} is missing scenarios for "
            f"{OFFICIAL_FUTURE_STRATEGY_MODEL}: {missing_scenarios}"
        )

    bad_sample_days = []
    for row in strategy_rows:
        if str(row.get("scenario")) not in REQUIRED_FUTURE_SCENARIOS:
            continue
        sample_days = _to_float(row.get("sample_days"))
        if sample_days is None or int(sample_days) != evaluated_days:
            bad_sample_days.append(
                {
                    "scenario": row.get("scenario"),
                    "sample_days": row.get("sample_days"),
                }
            )
    if bad_sample_days:
        result.errors.append(
            f"{FUTURE_MARKET_IMPACT_HEADLINE} sample_days must equal "
            f"evaluated_days={evaluated_days} for {OFFICIAL_FUTURE_STRATEGY_MODEL}: "
            f"{bad_sample_days}"
        )

    result.details["future_market_impact_model"] = OFFICIAL_FUTURE_STRATEGY_MODEL
    result.details["future_market_impact_scenarios"] = sorted(
        REQUIRED_FUTURE_SCENARIOS & scenarios
    )


def _assert_close(
    result: ValidationResult,
    label: str,
    actual: Any,
    expected: Any,
    tolerance: float,
) -> None:
    actual_number = _to_float(actual)
    expected_number = _to_float(expected)
    if actual_number is None or expected_number is None:
        result.errors.append(f"{label} cannot be compared: actual={actual}, expected={expected}")
        return
    if abs(actual_number - expected_number) > tolerance:
        result.errors.append(
            f"{label} mismatch: actual={actual_number}, expected={expected_number}"
        )


def _to_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None
