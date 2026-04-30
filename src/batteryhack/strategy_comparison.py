from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

import numpy as np
import pandas as pd

from .baseline import (
    BASELINE_PRICE_COL,
    UK_NAIVE_BASELINE_NAME,
    run_uk_naive_baseline_backtest,
    run_uk_naive_self_schedule_baseline,
)
from .optimizer import BatteryParams
from .simulation import daterange


DAILY_OUTPUT_SCHEMA = [
    "delivery_date",
    "strategy",
    "model_or_method",
    "forecast_mae_eur_mwh",
    "forecast_rmse_eur_mwh",
    "spread_direction_accuracy",
    "realized_net_revenue_eur",
    "oracle_net_revenue_eur",
    "capture_ratio_vs_oracle",
    "realized_charged_mwh",
    "realized_discharged_mwh",
    "realized_equivalent_cycles",
    "realized_captured_spread_eur_mwh",
]

INTERVAL_OUTPUT_SCHEMA = [
    "delivery_date",
    "timestamp",
    "interval",
    "strategy",
    "model_or_method",
    "actual_price_eur_mwh",
    "forecast_price_eur_mwh",
    "charge_mw",
    "discharge_mw",
    "net_power_mw",
    "soc_pct_end",
]

SUMMARY_OUTPUT_SCHEMA = [
    "strategy",
    "model_or_method",
    "days",
    "matched_baseline_days",
    "total_realized_net_revenue_eur",
    "average_realized_net_revenue_eur_per_day",
    "average_capture_ratio_vs_oracle",
    "win_rate_vs_uk_baseline",
    "total_uplift_vs_uk_baseline_eur",
    "average_uplift_vs_uk_baseline_eur_per_day",
    "baseline_total_realized_net_revenue_eur",
]

HEADLINE_OUTPUT_KEYS = [
    "date_window",
    "evaluated_days",
    "best_model",
    "best_ml_strategy",
    "best_ml_by_total_realized_net_revenue_eur",
    "best_ml_by_average_capture_ratio_vs_oracle",
    "best_ml_by_forecast_mae_eur_mwh",
    "uk_baseline",
    "uk_baseline_total_pnl_eur",
    "ml_total_pnl_eur",
    "uplift_eur",
    "uplift_pct",
    "win_rate_vs_uk_baseline",
    "average_capture_ratio_vs_oracle",
    "battery_assumptions",
]


@dataclass(frozen=True)
class StrategyComparisonResult:
    daily: pd.DataFrame
    intervals: pd.DataFrame
    summary: pd.DataFrame


def build_strategy_comparison(
    ml_daily: pd.DataFrame,
    baseline_daily: pd.DataFrame,
    ml_predictions: pd.DataFrame | None = None,
    baseline_intervals: pd.DataFrame | None = None,
) -> StrategyComparisonResult:
    """Normalize ML and UK-baseline rows to one same-date comparison result."""
    ml = normalize_ml_daily(ml_daily)
    baseline = normalize_baseline_daily(baseline_daily)
    if ml.empty:
        raise ValueError("ml_daily has no comparable rows")
    if baseline.empty:
        raise ValueError("baseline_daily has no comparable rows")
    if baseline["delivery_date"].duplicated().any():
        duplicates = sorted(baseline.loc[baseline["delivery_date"].duplicated(), "delivery_date"])
        raise ValueError(f"baseline_daily must have one row per delivery_date: {duplicates}")

    common_dates = sorted(set(ml["delivery_date"]) & set(baseline["delivery_date"]))
    if not common_dates:
        raise ValueError("ML and baseline rows have no shared delivery_date values")

    ml = ml[ml["delivery_date"].isin(common_dates)].copy()
    baseline = baseline[baseline["delivery_date"].isin(common_dates)].copy()
    daily = (
        pd.concat([ml, baseline], ignore_index=True)
        .loc[:, DAILY_OUTPUT_SCHEMA]
        .sort_values(["delivery_date", "strategy", "model_or_method"])
        .reset_index(drop=True)
    )
    intervals = build_strategy_comparison_intervals(
        ml_predictions=ml_predictions,
        baseline_intervals=baseline_intervals,
        delivery_dates=common_dates,
    )
    summary = summarize_strategy_comparison(daily)
    return StrategyComparisonResult(daily=daily, intervals=intervals, summary=summary)


def run_uk_naive_baseline_for_comparison(
    history: pd.DataFrame,
    start_date: date,
    end_date: date,
    battery_params: BatteryParams,
    drop_synthetic_targets: bool = True,
    include_intervals: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the UK naive benchmark and return normalized daily and optional interval rows."""
    daily_raw = run_uk_naive_baseline_backtest(
        history,
        start_date,
        end_date,
        battery_params,
        drop_synthetic_targets=drop_synthetic_targets,
    )
    intervals_raw = (
        build_uk_naive_baseline_intervals(
            history,
            _dates_from_daily(daily_raw),
            battery_params,
            drop_synthetic_targets=drop_synthetic_targets,
        )
        if include_intervals and not daily_raw.empty
        else pd.DataFrame(columns=INTERVAL_OUTPUT_SCHEMA)
    )
    return normalize_baseline_daily(daily_raw), normalize_baseline_intervals(intervals_raw)


def build_uk_naive_baseline_intervals(
    history: pd.DataFrame,
    target_dates: Iterable[date],
    battery_params: BatteryParams,
    drop_synthetic_targets: bool = True,
) -> pd.DataFrame:
    """Build interval-level UK naive forecast and dispatch rows for selected dates."""
    if history.empty:
        return pd.DataFrame(columns=INTERVAL_OUTPUT_SCHEMA)

    frame = history.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"]).dt.tz_localize(None)
    rows: list[pd.DataFrame] = []
    for target_date in target_dates:
        target = frame[frame["timestamp"].dt.date == target_date].copy().reset_index(drop=True)
        if target.empty:
            continue
        if (
            drop_synthetic_targets
            and "data_quality" in target
            and str(target["data_quality"].iloc[0]) != "public price data"
        ):
            continue

        dispatch = run_uk_naive_self_schedule_baseline(frame, target, battery_params)
        schedule = dispatch.schedule.copy()
        output = schedule[
            [
                "timestamp",
                "interval",
                BASELINE_PRICE_COL,
                "charge_mw",
                "discharge_mw",
                "net_power_mw",
                "soc_pct_end",
            ]
        ].merge(
            target[["timestamp", "dam_price_eur_mwh"]],
            on="timestamp",
            how="left",
        )
        output.insert(0, "delivery_date", target_date.isoformat())
        output["strategy"] = UK_NAIVE_BASELINE_NAME
        output["model_or_method"] = dispatch.forecast.method
        output = output.rename(
            columns={
                "dam_price_eur_mwh": "actual_price_eur_mwh",
                BASELINE_PRICE_COL: "forecast_price_eur_mwh",
            }
        )
        rows.append(output[INTERVAL_OUTPUT_SCHEMA])

    if not rows:
        return pd.DataFrame(columns=INTERVAL_OUTPUT_SCHEMA)
    return pd.concat(rows, ignore_index=True)


def normalize_ml_daily(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize daily ML output into the comparison daily schema."""
    if frame is None or frame.empty:
        return pd.DataFrame(columns=DAILY_OUTPUT_SCHEMA)
    _require_columns(frame, {"delivery_date", "model"}, "ml_daily")

    model = frame["model"].astype(str)
    output = pd.DataFrame(
        {
            "delivery_date": _iso_dates(frame["delivery_date"]),
            "strategy": "ml_" + model,
            "model_or_method": model,
            "forecast_mae_eur_mwh": _coalesce_numeric(
                frame,
                ["forecast_mae_eur_mwh", "mae_eur_mwh"],
                "ml_daily",
            ),
            "forecast_rmse_eur_mwh": _coalesce_numeric(
                frame,
                ["forecast_rmse_eur_mwh", "rmse_eur_mwh"],
                "ml_daily",
            ),
            "spread_direction_accuracy": _coalesce_numeric(
                frame,
                ["spread_direction_accuracy", "forecast_spread_direction_accuracy"],
                "ml_daily",
            ),
            "realized_net_revenue_eur": _coalesce_numeric(
                frame,
                ["realized_net_revenue_eur"],
                "ml_daily",
            ),
            "oracle_net_revenue_eur": _coalesce_numeric(
                frame,
                ["oracle_net_revenue_eur"],
                "ml_daily",
            ),
            "capture_ratio_vs_oracle": _coalesce_numeric(
                frame,
                ["capture_ratio_vs_oracle"],
                "ml_daily",
            ),
            "realized_charged_mwh": _coalesce_numeric(
                frame,
                ["realized_charged_mwh"],
                "ml_daily",
            ),
            "realized_discharged_mwh": _coalesce_numeric(
                frame,
                ["realized_discharged_mwh"],
                "ml_daily",
            ),
            "realized_equivalent_cycles": _coalesce_numeric(
                frame,
                ["realized_equivalent_cycles"],
                "ml_daily",
            ),
            "realized_captured_spread_eur_mwh": _coalesce_numeric(
                frame,
                ["realized_captured_spread_eur_mwh"],
                "ml_daily",
            ),
        }
    )
    return output[DAILY_OUTPUT_SCHEMA]


def normalize_baseline_daily(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize UK naive baseline daily output into the comparison daily schema."""
    if frame is None or frame.empty:
        return pd.DataFrame(columns=DAILY_OUTPUT_SCHEMA)
    _require_columns(frame, {"delivery_date"}, "baseline_daily")

    output = pd.DataFrame(
        {
            "delivery_date": _iso_dates(frame["delivery_date"]),
            "strategy": UK_NAIVE_BASELINE_NAME,
            "model_or_method": _coalesce_text(
                frame,
                ["model_or_method", "baseline_method", "method"],
                UK_NAIVE_BASELINE_NAME,
            ),
            "forecast_mae_eur_mwh": _coalesce_numeric(
                frame,
                ["forecast_mae_eur_mwh", "baseline_forecast_mae_eur_mwh"],
                "baseline_daily",
            ),
            "forecast_rmse_eur_mwh": _coalesce_numeric(
                frame,
                ["forecast_rmse_eur_mwh", "baseline_forecast_rmse_eur_mwh"],
                "baseline_daily",
            ),
            "spread_direction_accuracy": _coalesce_numeric(
                frame,
                [
                    "spread_direction_accuracy",
                    "forecast_spread_direction_accuracy",
                    "baseline_spread_direction_accuracy",
                ],
                "baseline_daily",
            ),
            "realized_net_revenue_eur": _coalesce_numeric(
                frame,
                ["realized_net_revenue_eur", "baseline_realized_net_revenue_eur"],
                "baseline_daily",
            ),
            "oracle_net_revenue_eur": _coalesce_numeric(
                frame,
                ["oracle_net_revenue_eur"],
                "baseline_daily",
            ),
            "capture_ratio_vs_oracle": _coalesce_numeric(
                frame,
                ["capture_ratio_vs_oracle", "baseline_capture_ratio_vs_oracle"],
                "baseline_daily",
            ),
            "realized_charged_mwh": _coalesce_numeric(
                frame,
                ["realized_charged_mwh", "baseline_charged_mwh"],
                "baseline_daily",
            ),
            "realized_discharged_mwh": _coalesce_numeric(
                frame,
                ["realized_discharged_mwh", "baseline_discharged_mwh"],
                "baseline_daily",
            ),
            "realized_equivalent_cycles": _coalesce_numeric(
                frame,
                ["realized_equivalent_cycles", "baseline_equivalent_cycles"],
                "baseline_daily",
            ),
            "realized_captured_spread_eur_mwh": _coalesce_numeric(
                frame,
                [
                    "realized_captured_spread_eur_mwh",
                    "baseline_captured_spread_eur_mwh",
                ],
                "baseline_daily",
            ),
        }
    )
    return output[DAILY_OUTPUT_SCHEMA]


def build_strategy_comparison_intervals(
    ml_predictions: pd.DataFrame | None,
    baseline_intervals: pd.DataFrame | None,
    delivery_dates: Iterable[str],
) -> pd.DataFrame:
    interval_parts = [
        normalize_ml_predictions(ml_predictions),
        normalize_baseline_intervals(baseline_intervals),
    ]
    interval_parts = [frame for frame in interval_parts if not frame.empty]
    if not interval_parts:
        return pd.DataFrame(columns=INTERVAL_OUTPUT_SCHEMA)

    common_dates = set(delivery_dates)
    intervals = pd.concat(interval_parts, ignore_index=True)
    intervals = intervals[intervals["delivery_date"].isin(common_dates)].copy()
    if intervals.empty:
        return pd.DataFrame(columns=INTERVAL_OUTPUT_SCHEMA)
    return (
        intervals[INTERVAL_OUTPUT_SCHEMA]
        .sort_values(["delivery_date", "strategy", "model_or_method", "timestamp", "interval"])
        .reset_index(drop=True)
    )


def normalize_ml_predictions(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=INTERVAL_OUTPUT_SCHEMA)
    _require_columns(
        frame,
        {
            "delivery_date",
            "timestamp",
            "interval",
            "model",
            "actual_price_eur_mwh",
            "forecast_price_eur_mwh",
            "charge_mw",
            "discharge_mw",
            "net_power_mw",
            "soc_pct_end",
        },
        "ml_predictions",
    )
    model = frame["model"].astype(str)
    output = pd.DataFrame(
        {
            "delivery_date": _iso_dates(frame["delivery_date"]),
            "timestamp": pd.to_datetime(frame["timestamp"]),
            "interval": pd.to_numeric(frame["interval"], errors="coerce").astype("Int64"),
            "strategy": "ml_" + model,
            "model_or_method": model,
            "actual_price_eur_mwh": pd.to_numeric(
                frame["actual_price_eur_mwh"],
                errors="coerce",
            ),
            "forecast_price_eur_mwh": pd.to_numeric(
                frame["forecast_price_eur_mwh"],
                errors="coerce",
            ),
            "charge_mw": pd.to_numeric(frame["charge_mw"], errors="coerce"),
            "discharge_mw": pd.to_numeric(frame["discharge_mw"], errors="coerce"),
            "net_power_mw": pd.to_numeric(frame["net_power_mw"], errors="coerce"),
            "soc_pct_end": pd.to_numeric(frame["soc_pct_end"], errors="coerce"),
        }
    )
    return output[INTERVAL_OUTPUT_SCHEMA]


def normalize_baseline_intervals(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=INTERVAL_OUTPUT_SCHEMA)
    _require_columns(
        frame,
        {
            "delivery_date",
            "timestamp",
            "interval",
            "charge_mw",
            "discharge_mw",
            "net_power_mw",
            "soc_pct_end",
        },
        "baseline_intervals",
    )
    output = pd.DataFrame(
        {
            "delivery_date": _iso_dates(frame["delivery_date"]),
            "timestamp": pd.to_datetime(frame["timestamp"]),
            "interval": pd.to_numeric(frame["interval"], errors="coerce").astype("Int64"),
            "strategy": UK_NAIVE_BASELINE_NAME,
            "model_or_method": _coalesce_text(
                frame,
                ["model_or_method", "baseline_method", "method"],
                UK_NAIVE_BASELINE_NAME,
            ),
            "actual_price_eur_mwh": _coalesce_numeric(
                frame,
                ["actual_price_eur_mwh", "dam_price_eur_mwh"],
                "baseline_intervals",
            ),
            "forecast_price_eur_mwh": _coalesce_numeric(
                frame,
                ["forecast_price_eur_mwh", BASELINE_PRICE_COL],
                "baseline_intervals",
            ),
            "charge_mw": pd.to_numeric(frame["charge_mw"], errors="coerce"),
            "discharge_mw": pd.to_numeric(frame["discharge_mw"], errors="coerce"),
            "net_power_mw": pd.to_numeric(frame["net_power_mw"], errors="coerce"),
            "soc_pct_end": pd.to_numeric(frame["soc_pct_end"], errors="coerce"),
        }
    )
    return output[INTERVAL_OUTPUT_SCHEMA]


def summarize_strategy_comparison(daily: pd.DataFrame) -> pd.DataFrame:
    if daily.empty:
        return pd.DataFrame(columns=SUMMARY_OUTPUT_SCHEMA)

    _require_columns(daily, set(DAILY_OUTPUT_SCHEMA), "daily")
    baseline = daily[daily["strategy"] == UK_NAIVE_BASELINE_NAME][
        ["delivery_date", "realized_net_revenue_eur"]
    ].rename(columns={"realized_net_revenue_eur": "baseline_realized_net_revenue_eur"})
    if baseline.empty:
        raise ValueError("daily comparison rows must include uk_naive_baseline")

    rows: list[dict[str, float | int | str]] = []
    grouped = daily.groupby(["strategy", "model_or_method"], sort=False)
    for (strategy, model_or_method), strategy_daily in grouped:
        merged = strategy_daily.merge(baseline, on="delivery_date", how="inner")
        uplift = (
            merged["realized_net_revenue_eur"]
            - merged["baseline_realized_net_revenue_eur"]
        )
        is_baseline = strategy == UK_NAIVE_BASELINE_NAME
        matched_days = int(merged["delivery_date"].nunique())
        rows.append(
            {
                "strategy": str(strategy),
                "model_or_method": str(model_or_method),
                "days": int(strategy_daily["delivery_date"].nunique()),
                "matched_baseline_days": matched_days,
                "total_realized_net_revenue_eur": float(
                    strategy_daily["realized_net_revenue_eur"].sum()
                ),
                "average_realized_net_revenue_eur_per_day": float(
                    strategy_daily["realized_net_revenue_eur"].mean()
                ),
                "average_capture_ratio_vs_oracle": float(
                    strategy_daily["capture_ratio_vs_oracle"].mean()
                ),
                "win_rate_vs_uk_baseline": (
                    np.nan if is_baseline or matched_days == 0 else float((uplift > 0).mean())
                ),
                "total_uplift_vs_uk_baseline_eur": (
                    0.0 if is_baseline else float(uplift.sum())
                ),
                "average_uplift_vs_uk_baseline_eur_per_day": (
                    0.0 if is_baseline else float(uplift.mean())
                ),
                "baseline_total_realized_net_revenue_eur": float(
                    merged["baseline_realized_net_revenue_eur"].sum()
                ),
            }
        )

    return pd.DataFrame(rows, columns=SUMMARY_OUTPUT_SCHEMA).sort_values(
        ["strategy", "model_or_method"],
    ).reset_index(drop=True)


def build_headline_report(
    daily: pd.DataFrame,
    summary: pd.DataFrame | None = None,
    battery_params: BatteryParams | None = None,
) -> dict[str, object]:
    """Build a presentation-ready headline from normalized comparison rows."""
    if daily.empty:
        raise ValueError("daily comparison rows are empty")
    _require_columns(daily, set(DAILY_OUTPUT_SCHEMA), "daily")

    normalized_summary = (
        summarize_strategy_comparison(daily)
        if summary is None or summary.empty
        else summary.copy()
    )
    _require_columns(normalized_summary, set(SUMMARY_OUTPUT_SCHEMA), "summary")

    ml_summary = normalized_summary[
        normalized_summary["strategy"].astype(str).str.startswith("ml_")
    ].copy()
    if ml_summary.empty:
        raise ValueError("summary has no ML strategy rows")

    baseline_daily = daily[daily["strategy"] == UK_NAIVE_BASELINE_NAME].copy()
    if baseline_daily.empty:
        raise ValueError("daily comparison rows have no uk_naive_baseline row")
    baseline_payload = _baseline_aggregate_payload(baseline_daily)
    best_pnl = _best_summary_row(
        ml_summary,
        "total_realized_net_revenue_eur",
        ascending=False,
    )
    best_capture = _best_summary_row(
        ml_summary,
        "average_capture_ratio_vs_oracle",
        ascending=False,
    )
    best_mae = _best_daily_average_row(
        daily[daily["strategy"].astype(str).str.startswith("ml_")],
        "forecast_mae_eur_mwh",
        ascending=True,
    )

    dates = sorted(pd.to_datetime(daily["delivery_date"]).dt.date.unique())
    ml_total_pnl = _float_or_none(best_pnl["total_realized_net_revenue_eur"])
    baseline_total_pnl = _float_or_none(baseline_payload["total_realized_net_revenue_eur"])
    uplift_eur = (
        None
        if ml_total_pnl is None or baseline_total_pnl is None
        else ml_total_pnl - baseline_total_pnl
    )
    uplift_pct = (
        None
        if uplift_eur is None or baseline_total_pnl is None or abs(baseline_total_pnl) <= 1e-9
        else uplift_eur / abs(baseline_total_pnl)
    )

    report = {
        "date_window": {
            "start": dates[0].isoformat(),
            "end": dates[-1].isoformat(),
        },
        "evaluated_days": int(len(dates)),
        "best_model": str(best_pnl["model_or_method"]),
        "best_ml_strategy": str(best_pnl["strategy"]),
        "best_ml_by_total_realized_net_revenue_eur": _summary_row_payload(best_pnl),
        "best_ml_by_average_capture_ratio_vs_oracle": _summary_row_payload(best_capture),
        "best_ml_by_forecast_mae_eur_mwh": _daily_average_payload(best_mae),
        "uk_baseline": baseline_payload,
        "uk_baseline_total_pnl_eur": baseline_total_pnl,
        "ml_total_pnl_eur": ml_total_pnl,
        "uplift_eur": uplift_eur,
        "uplift_pct": uplift_pct,
        "win_rate_vs_uk_baseline": _float_or_none(best_pnl["win_rate_vs_uk_baseline"]),
        "average_capture_ratio_vs_oracle": _float_or_none(
            best_pnl["average_capture_ratio_vs_oracle"]
        ),
        "battery_assumptions": (
            battery_params_to_dict(battery_params) if battery_params is not None else None
        ),
    }
    return {key: report[key] for key in HEADLINE_OUTPUT_KEYS}


def build_headline_frame(headline: dict[str, object]) -> pd.DataFrame:
    """Flatten the compact headline JSON into a one-row CSV-friendly table."""
    best_mae = headline["best_ml_by_forecast_mae_eur_mwh"]
    if not isinstance(best_mae, dict):
        best_mae = {}
    battery = headline["battery_assumptions"]
    if not isinstance(battery, dict):
        battery = {}
    date_window = headline["date_window"]
    if not isinstance(date_window, dict):
        date_window = {}

    return pd.DataFrame(
        [
            {
                "start_date": date_window.get("start"),
                "end_date": date_window.get("end"),
                "evaluated_days": headline.get("evaluated_days"),
                "best_model": headline.get("best_model"),
                "best_ml_strategy": headline.get("best_ml_strategy"),
                "uk_baseline_total_pnl_eur": headline.get("uk_baseline_total_pnl_eur"),
                "ml_total_pnl_eur": headline.get("ml_total_pnl_eur"),
                "uplift_eur": headline.get("uplift_eur"),
                "uplift_pct": headline.get("uplift_pct"),
                "win_rate_vs_uk_baseline": headline.get("win_rate_vs_uk_baseline"),
                "average_capture_ratio_vs_oracle": headline.get(
                    "average_capture_ratio_vs_oracle"
                ),
                "best_mae_model": best_mae.get("model_or_method"),
                "best_mae_eur_mwh": best_mae.get("forecast_mae_eur_mwh"),
                "battery_power_mw": battery.get("power_mw"),
                "battery_capacity_mwh": battery.get("capacity_mwh"),
                "battery_round_trip_efficiency": battery.get("round_trip_efficiency"),
                "battery_max_cycles_per_day": battery.get("max_cycles_per_day"),
            }
        ]
    )


def battery_params_to_dict(params: BatteryParams) -> dict[str, float | bool | None]:
    return {
        "power_mw": params.power_mw,
        "capacity_mwh": params.capacity_mwh,
        "round_trip_efficiency": params.round_trip_efficiency,
        "min_soc_pct": params.min_soc_pct,
        "max_soc_pct": params.max_soc_pct,
        "initial_soc_pct": params.initial_soc_pct,
        "terminal_soc_pct": params.terminal_soc_pct,
        "degradation_cost_eur_mwh": params.degradation_cost_eur_mwh,
        "max_cycles_per_day": params.max_cycles_per_day,
        "enforce_single_mode": params.enforce_single_mode,
    }


def _require_columns(frame: pd.DataFrame, required: set[str], label: str) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{label} is missing required columns: {missing}")


def _best_summary_row(frame: pd.DataFrame, column: str, ascending: bool) -> pd.Series:
    usable = frame.dropna(subset=[column]).copy()
    if usable.empty:
        raise ValueError(f"No ML summary rows have {column}")
    return usable.sort_values(
        [column, "total_realized_net_revenue_eur", "strategy", "model_or_method"],
        ascending=[ascending, False, True, True],
    ).iloc[0]


def _best_daily_average_row(frame: pd.DataFrame, column: str, ascending: bool) -> pd.Series:
    usable = frame.dropna(subset=[column]).copy()
    if usable.empty:
        raise ValueError(f"No ML daily rows have {column}")
    grouped = (
        usable.groupby(["strategy", "model_or_method"], as_index=False)
        .agg(
            forecast_mae_eur_mwh=("forecast_mae_eur_mwh", "mean"),
            forecast_rmse_eur_mwh=("forecast_rmse_eur_mwh", "mean"),
            spread_direction_accuracy=("spread_direction_accuracy", "mean"),
            realized_net_revenue_eur=("realized_net_revenue_eur", "sum"),
            capture_ratio_vs_oracle=("capture_ratio_vs_oracle", "mean"),
            days=("delivery_date", "nunique"),
        )
    )
    return grouped.sort_values(
        [column, "realized_net_revenue_eur", "strategy", "model_or_method"],
        ascending=[ascending, False, True, True],
    ).iloc[0]


def _summary_row_payload(row: pd.Series) -> dict[str, object]:
    return {
        "strategy": str(row["strategy"]),
        "model_or_method": str(row["model_or_method"]),
        "days": int(row["days"]),
        "total_realized_net_revenue_eur": _float_or_none(
            row["total_realized_net_revenue_eur"]
        ),
        "average_realized_net_revenue_eur_per_day": _float_or_none(
            row["average_realized_net_revenue_eur_per_day"]
        ),
        "average_capture_ratio_vs_oracle": _float_or_none(
            row["average_capture_ratio_vs_oracle"]
        ),
        "win_rate_vs_uk_baseline": _float_or_none(row["win_rate_vs_uk_baseline"]),
        "total_uplift_vs_uk_baseline_eur": _float_or_none(
            row["total_uplift_vs_uk_baseline_eur"]
        ),
    }


def _baseline_aggregate_payload(frame: pd.DataFrame) -> dict[str, object]:
    methods = sorted(frame["model_or_method"].dropna().astype(str).unique())
    method_label = "unknown" if not methods else ("all_methods" if len(methods) > 1 else methods[0])
    return {
        "strategy": UK_NAIVE_BASELINE_NAME,
        "model_or_method": method_label,
        "methods": methods,
        "days": int(frame["delivery_date"].nunique()),
        "total_realized_net_revenue_eur": _float_or_none(
            frame["realized_net_revenue_eur"].sum()
        ),
        "average_realized_net_revenue_eur_per_day": _float_or_none(
            frame["realized_net_revenue_eur"].mean()
        ),
        "average_capture_ratio_vs_oracle": _float_or_none(
            frame["capture_ratio_vs_oracle"].mean()
        ),
        "win_rate_vs_uk_baseline": None,
        "total_uplift_vs_uk_baseline_eur": 0.0,
    }


def _daily_average_payload(row: pd.Series) -> dict[str, object]:
    return {
        "strategy": str(row["strategy"]),
        "model_or_method": str(row["model_or_method"]),
        "days": int(row["days"]),
        "forecast_mae_eur_mwh": _float_or_none(row["forecast_mae_eur_mwh"]),
        "forecast_rmse_eur_mwh": _float_or_none(row["forecast_rmse_eur_mwh"]),
        "spread_direction_accuracy": _float_or_none(row["spread_direction_accuracy"]),
        "total_realized_net_revenue_eur": _float_or_none(row["realized_net_revenue_eur"]),
        "average_capture_ratio_vs_oracle": _float_or_none(row["capture_ratio_vs_oracle"]),
    }


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _coalesce_numeric(frame: pd.DataFrame, candidates: list[str], label: str) -> pd.Series:
    for column in candidates:
        if column in frame.columns:
            return pd.to_numeric(frame[column], errors="coerce")
    raise ValueError(f"{label} is missing one of columns: {candidates}")


def _coalesce_text(frame: pd.DataFrame, candidates: list[str], default: str) -> pd.Series:
    for column in candidates:
        if column in frame.columns:
            return frame[column].fillna(default).astype(str)
    return pd.Series([default] * len(frame), index=frame.index, dtype="object")


def _iso_dates(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values).dt.date.astype(str)


def _dates_from_daily(frame: pd.DataFrame) -> list[date]:
    if frame.empty or "delivery_date" not in frame.columns:
        return []
    return sorted(pd.to_datetime(frame["delivery_date"]).dt.date.unique())


def delivery_window(frame: pd.DataFrame) -> tuple[date, date]:
    _require_columns(frame, {"delivery_date"}, "daily")
    dates = sorted(pd.to_datetime(frame["delivery_date"]).dt.date.unique())
    if not dates:
        raise ValueError("daily input has no delivery_date values")
    return dates[0], dates[-1]


def filter_delivery_dates(
    frame: pd.DataFrame,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    if frame.empty or "delivery_date" not in frame.columns:
        return frame.copy()
    dates = pd.to_datetime(frame["delivery_date"]).dt.date
    return frame[(dates >= start_date) & (dates <= end_date)].copy()


def delivery_dates_between(start_date: date, end_date: date) -> list[date]:
    return list(daterange(start_date, end_date))
